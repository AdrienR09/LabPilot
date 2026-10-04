"""The NKT SuperK, against a stand-in for pylablib's Interbus layer.

Three things here would be plausible-looking bugs rather than errors, so
they get their own tests:

- **Emission is `3`, not `1`.** NKT's register 0x30 takes 3 for on and 0
  for off. A boolean written straight through would be a laser that does
  not come on, or — worse on a different register — one that does
  something else.
- **The right module.** A rack carries the laser plus whatever filters are
  fitted, all on one Interbus. Taking the first module that answers points
  the adapter at an acousto-optic filter and then writes an emission
  register it does not have.
- **Emission is not touched by connecting or disconnecting.** A Class 4
  laser whose output is tied to a software connection goes dark because a
  window was closed, in the middle of a measurement that took an hour to
  stabilise.

The register table itself is not retested: it is pylablib's, scale factors
and all, and this adapter addresses registers by name precisely so there
is one place for those numbers to live.
"""

from __future__ import annotations

from typing import Any

import pytest

from labpilot.core.errors import DeviceError, LimitError
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.NKT.superk import (
    EMISSION_OFF,
    EMISSION_ON,
    SuperKAdapter,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- Stand-ins --------------------------------------------------------------


class _Module:
    """pylablib's `IInterbusModule`, as far as this adapter uses it.

    Registers are addressed by name and the scale factors are pylablib's,
    so this holds already-scaled values — `power` in percent, not in
    tenths.
    """

    def __init__(self, **registers: Any) -> None:
        self.registers: dict[str, Any] = {
            "serial": "SN-SUPERK-1",
            "emission": EMISSION_OFF,
            "power": 40.0,
            "current": 55.0,
            "pulse_picker_ratio": 1,
            "temperature_inlet": 21.3,
            **registers,
        }
        self.status = ["emission"] if self.registers["emission"] else []
        self.writes: list[tuple[str, Any]] = []

    def get_register(self, name: str) -> Any:
        return self.registers[name]

    def set_register(self, name: str, value: Any) -> Any:
        self.writes.append((name, value))
        self.registers[name] = value
        if name == "emission":
            self.status = ["emission"] if value == EMISSION_ON else []
        return value

    def get_status(self) -> list[str]:
        return list(self.status)


class _Filter:
    """A SELECT or VARIA: on the same bus, not the laser."""

    dtype = 0x67

    def get_register(self, name: str) -> Any:  # pragma: no cover - never reached
        raise AssertionError("the filter must not be addressed as the laser")


class _Bus:
    def __init__(self, modules: dict[int, Any]) -> None:
        self.m = modules
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def interbus(monkeypatch):
    """A fake `pylablib.devices.NKT.interbus` whose module class the
    adapter can `isinstance`-check, which is how the laser is found."""
    import types

    laser = _Module()

    class SuperKExtremeInterbusModule(_Module):
        pass

    laser.__class__ = SuperKExtremeInterbusModule
    laser.dest = 15

    state = types.SimpleNamespace(
        laser=laser,
        modules={15: laser},
        opened=[],
        bus=None,
        fail=None,
    )

    def InterbusSystem(conn, modules="auto"):  # noqa: N802 - pylablib's spelling
        state.opened.append((conn, modules))
        if state.fail:
            raise OSError(state.fail)
        state.bus = _Bus(state.modules)
        return state.bus

    module = types.SimpleNamespace(
        InterbusSystem=InterbusSystem,
        SuperKExtremeInterbusModule=SuperKExtremeInterbusModule,
    )
    monkeypatch.setattr(SuperKAdapter, "_import", lambda self: module)
    return state


async def _connected(interbus, **kwargs) -> SuperKAdapter:
    adapter = SuperKAdapter(port="COM4", **kwargs)
    await adapter.connect()
    return adapter


# --- Describing itself ------------------------------------------------------


def test_it_is_registered_and_catalogued():
    assert "nkt_superk" in adapter_registry.list()
    assert any(m.adapter_key == "nkt_superk" for m in INSTRUMENT_CATALOG)


def test_it_describes_itself_without_pylablib():
    schema = SuperKAdapter.describe()
    assert schema is not None and schema.kind == "source"


def test_emission_is_not_a_boolean_on_the_wire():
    """NKT's convention, and the one value in the protocol worth naming."""
    assert (EMISSION_ON, EMISSION_OFF) == (3, 0)


# --- Connecting -------------------------------------------------------------


async def test_a_port_is_required_and_the_message_says_why(interbus):
    adapter = SuperKAdapter()
    with pytest.raises(DeviceError, match="serial port"):
        await adapter.connect()


async def test_connecting_opens_the_bus_at_nkts_baudrate(interbus):
    adapter = await _connected(interbus)
    try:
        assert interbus.opened == [(("COM4", 115200), "auto")]
    finally:
        await adapter.disconnect()


async def test_an_explicit_address_is_asked_for_directly(interbus):
    adapter = await _connected(interbus, address=15)
    try:
        assert interbus.opened[-1][1] == [15]
    finally:
        await adapter.disconnect()


async def test_the_laser_is_found_by_type_not_by_being_first(interbus):
    """On a rack with a SELECT, the first module that answers is an
    acousto-optic filter, and writing an emission register to it is both
    useless and alarming."""
    interbus.modules = {17: _Filter(), 15: interbus.laser}
    adapter = await _connected(interbus)
    try:
        assert (await adapter.read())["module_address"] == 15
    finally:
        await adapter.disconnect()


async def test_a_bus_with_no_laser_on_it_says_what_it_did_find(interbus):
    interbus.modules = {17: _Filter()}
    adapter = SuperKAdapter(port="COM4")
    with pytest.raises(DeviceError, match="No SuperK main module"):
        await adapter.connect()


async def test_a_failure_after_opening_closes_the_bus_again(interbus):
    interbus.modules = {17: _Filter()}
    adapter = SuperKAdapter(port="COM4")
    with pytest.raises(DeviceError):
        await adapter.connect()
    assert interbus.bus.closed == 1


# --- Emission, and what touches it ------------------------------------------


async def test_connecting_does_not_switch_the_laser_on(interbus):
    adapter = await _connected(interbus)
    try:
        assert interbus.laser.writes == []
        assert not (await adapter.read())["emitting"]
    finally:
        await adapter.disconnect()


async def test_disconnecting_leaves_emission_alone_by_default(interbus):
    """The default, and the one worth a test: a laser whose output is tied
    to a software connection goes dark when a window closes."""
    adapter = await _connected(interbus)
    await adapter.write({"emission": True})
    interbus.laser.writes.clear()

    await adapter.disconnect()
    assert interbus.laser.writes == []
    assert interbus.laser.registers["emission"] == EMISSION_ON


async def test_a_lab_can_choose_the_other_policy(interbus):
    adapter = await _connected(interbus, stop_emission_on_disconnect=True)
    await adapter.write({"emission": True})
    interbus.laser.writes.clear()

    await adapter.disconnect()
    assert interbus.laser.writes == [("emission", EMISSION_OFF)]


async def test_switching_emission_sends_nkts_value(interbus):
    adapter = await _connected(interbus)
    try:
        await adapter.write({"emission": True})
        assert interbus.laser.writes[-1] == ("emission", EMISSION_ON)
        await adapter.write({"emission": False})
        assert interbus.laser.writes[-1] == ("emission", EMISSION_OFF)
    finally:
        await adapter.disconnect()


async def test_emitting_is_read_from_the_status_bits(interbus):
    """Not from the emission register: this is whether light is coming
    out, not what was last asked for — an open interlock makes those two
    disagree."""
    adapter = await _connected(interbus)
    try:
        interbus.laser.registers["emission"] = EMISSION_ON
        interbus.laser.status = []          # commanded on, interlock open
        assert not (await adapter.read())["emitting"]
    finally:
        await adapter.disconnect()


async def test_an_open_interlock_is_reported(interbus):
    adapter = await _connected(interbus)
    try:
        interbus.laser.status = ["interlock_off"]
        reading = await adapter.read()
        assert reading["interlock_ok"] is False
        assert "interlock_off" in reading["status"]
    finally:
        await adapter.disconnect()


async def test_the_actions_are_the_abort_path(interbus):
    """`emission_off` has to be safe when it is already off."""
    adapter = await _connected(interbus)
    try:
        await adapter.emission_off()
        await adapter.emission_off()
        await adapter.emission_on()
        assert interbus.laser.registers["emission"] == EMISSION_ON
    finally:
        await adapter.disconnect()


# --- The setpoints ----------------------------------------------------------


async def test_the_power_setpoint_is_a_percentage(interbus):
    adapter = await _connected(interbus)
    try:
        await adapter.write({"power_percent": 62.5})
        assert interbus.laser.writes[-1] == ("power", 62.5)
        assert (await adapter.read())["power"] == pytest.approx(62.5)
    finally:
        await adapter.disconnect()


async def test_a_setpoint_over_a_hundred_percent_is_refused(interbus):
    adapter = await _connected(interbus)
    try:
        with pytest.raises(LimitError):
            adapter.validate_write({"power_percent": 150.0})
    finally:
        await adapter.disconnect()


async def test_the_pulse_picker_cannot_be_set_below_one(interbus):
    """Zero is not "every pulse"; it is a ratio with no meaning."""
    adapter = await _connected(interbus)
    try:
        await adapter.set_pulse_picker_ratio(0)
        assert interbus.laser.writes[-1] == ("pulse_picker_ratio", 1)
    finally:
        await adapter.disconnect()


async def test_the_inlet_temperature_is_reported(interbus):
    """Rising inlet temperature means check the chiller, and it is the
    one number that predicts a shutdown."""
    adapter = await _connected(interbus)
    try:
        assert (await adapter.read())["inlet_temperature"] == pytest.approx(21.3)
    finally:
        await adapter.disconnect()


async def test_reading_a_disconnected_laser_is_refused(interbus):
    adapter = await _connected(interbus)
    await adapter.disconnect()
    with pytest.raises(DeviceError, match="not connected"):
        adapter._read_sync()
