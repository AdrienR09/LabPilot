"""The Siglent SSG microwave source, against a fake SCPI instrument.

Tested through a real socket rather than a stubbed transport, because the
transport is new too and the interesting failures are in it: a query whose
answer never arrives, an instrument that turns out to be the oscilloscope
on the next shelf, a MIN/MAX query answered with something that is not a
range.

`_FakeSSG` implements the SCPI subset this adapter uses. It is not a
substitute for the hardware — nothing here proves the real instrument
accepts `:FREQ 2.87e9Hz` — and `labpilot probe siglent_ssg` is still the
thing that settles that. What these tests do prove is that every path
through the adapter is exercised and that its schema's limits come from
whatever the instrument said.
"""

from __future__ import annotations

import socket
import threading

import pytest

from labpilot.core.errors import DeviceError
from labpilot.instruments._scpi import ScpiTransport
from labpilot.instruments.Siglenttechnologies.microwave_source import (
    MODELS,
    SiglentSSGAdapter,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeSSG:
    """A socket speaking just enough SCPI, on a thread, on a free port."""

    identity = "Siglent Technologies,SSG3021X,SSG3XCAX1234,1.01.01.25"

    def __init__(self, *, ranges: bool = True, silent: bool = False) -> None:
        self.ranges = ranges
        self.silent = silent
        self.frequency = 1.0e9
        self.power = -30.0
        self.output = False
        self.sent: list[str] = []
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self._listener.settimeout(0.02)
        while not self._stop.is_set():
            try:
                client, _ = self._listener.accept()
            except (TimeoutError, OSError):
                continue
            with client:
                self._talk(client)

    def _talk(self, client: socket.socket) -> None:
        client.settimeout(0.02)
        buffer = b""
        while not self._stop.is_set():
            try:
                chunk = client.recv(4096)
            except (TimeoutError, OSError):
                continue
            if not chunk:
                return
            buffer += chunk
            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")
                answer = self._answer(line.decode().strip())
                if answer is not None and not self.silent:
                    client.sendall(f"{answer}\n".encode())

    def _answer(self, command: str) -> str | None:
        self.sent.append(command)
        if command == "*IDN?":
            return self.identity
        if command == "*OPC?":
            return "1"
        if command == ":FREQ?":
            return f"{self.frequency:.6E}"
        if command == ":POW?":
            return f"{self.power:.2f}"
        if command == ":OUTP?":
            return "1" if self.output else "0"
        if command in (":FREQ? MIN", ":FREQ? MAX", ":POW? MIN", ":POW? MAX"):
            if not self.ranges:
                # What a unit that does not understand the query does: it
                # answers the bare form instead of raising.
                return f"{self.frequency:.6E}" if "FREQ" in command else f"{self.power:.2f}"
            table = {
                ":FREQ? MIN": "9.000000E+03", ":FREQ? MAX": "2.100000E+09",
                ":POW? MIN": "-110.00", ":POW? MAX": "13.00",
            }
            return table[command]
        if command.startswith(":FREQ "):
            self.frequency = float(command.removeprefix(":FREQ ").removesuffix("Hz"))
            return None
        if command.startswith(":POW "):
            self.power = float(command.removeprefix(":POW ").removesuffix("dBm"))
            return None
        if command.startswith(":OUTP "):
            self.output = command.endswith("ON")
            return None
        return None

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._listener.close()


@pytest.fixture
def instrument():
    fake = _FakeSSG()
    yield fake
    fake.close()


async def _connected(fake: _FakeSSG, **overrides) -> SiglentSSGAdapter:
    adapter = SiglentSSGAdapter(host="127.0.0.1", port=fake.port, timeout=1.0, **overrides)
    await adapter.connect()
    return adapter


# --- The transport ---------------------------------------------------------


def test_a_transport_needs_an_address():
    with pytest.raises(ValueError, match="host= or resource="):
        ScpiTransport()


def test_nothing_listening_says_where_to_look():
    transport = ScpiTransport(host="127.0.0.1", port=1, timeout=0.5, device="x")
    with pytest.raises(DeviceError, match="No SCPI instrument answered"):
        transport.open()


def test_a_command_before_connecting_is_refused():
    from labpilot.core.errors import NotConnectedError

    transport = ScpiTransport(host="127.0.0.1", port=9, timeout=0.5)
    with pytest.raises(NotConnectedError):
        transport.write(":FREQ?")


def test_an_unanswered_query_names_the_command(instrument):
    """An empty answer parsed as a float fails several frames from the
    cause, so the timeout stops at the command instead."""
    instrument.silent = True
    transport = ScpiTransport(host="127.0.0.1", port=instrument.port, timeout=0.3)
    transport.open()
    try:
        with pytest.raises(DeviceError, match=r"\*IDN\? went unanswered"):
            transport.query("*IDN?")
    finally:
        transport.close()


def test_closing_twice_is_harmless(instrument):
    transport = ScpiTransport(host="127.0.0.1", port=instrument.port, timeout=0.5)
    transport.open()
    transport.close()
    transport.close()
    assert not transport.connected


def test_a_non_numeric_answer_is_a_named_error(instrument):
    transport = ScpiTransport(host="127.0.0.1", port=instrument.port, timeout=0.5)
    transport.open()
    try:
        with pytest.raises(DeviceError, match="not a number"):
            transport.query_float("*IDN?")
    finally:
        transport.close()


# --- Identification --------------------------------------------------------


async def test_connecting_identifies_the_instrument(instrument):
    adapter = await _connected(instrument)
    try:
        reading = await adapter.read()
        assert reading["model"] == "SSG3021X"
        assert reading["serial_number"] == "SSG3XCAX1234"
    finally:
        await adapter.disconnect()


async def test_the_wrong_instrument_at_that_address_is_refused(instrument):
    """A scope and a generator on one bench are easy to swap, and a
    generator that silently accepted `:FREQ` on a scope would be worse."""
    instrument.identity = "Siglent Technologies,SDS1072CML,SDS1EBAC,1.0"
    adapter = SiglentSSGAdapter(host="127.0.0.1", port=instrument.port, timeout=1.0)
    with pytest.raises(DeviceError, match="not an SSG signal generator"):
        await adapter.connect()


async def test_a_non_siglent_answer_is_refused(instrument):
    instrument.identity = "Rohde&Schwarz,SMB100A,1234,3.1"
    adapter = SiglentSSGAdapter(host="127.0.0.1", port=instrument.port, timeout=1.0)
    with pytest.raises(DeviceError, match="not a Siglent instrument"):
        await adapter.connect()


async def test_a_failed_identification_leaves_nothing_half_open(instrument):
    """A half-identified instrument would carry placeholder limits that
    `validate_write` then enforces as if they were real."""
    instrument.identity = "Nobody,Nothing"
    adapter = SiglentSSGAdapter(host="127.0.0.1", port=instrument.port, timeout=1.0)
    with pytest.raises(DeviceError):
        await adapter.connect()
    assert adapter._scpi is None
    assert not adapter.connected


# --- Limits ----------------------------------------------------------------


async def test_the_limits_come_from_the_instrument(instrument):
    adapter = await _connected(instrument)
    try:
        frequency = adapter.schema.require("cw_frequency")
        assert frequency.limits == (9e3, 2.1e9)
        assert "from the instrument" in frequency.description
    finally:
        await adapter.disconnect()


async def test_an_instrument_that_cannot_be_asked_falls_back_to_the_table(instrument):
    """A few units answer `:FREQ? MAX` with the current setpoint rather
    than erroring. Trusting that would pin the schema's limits to wherever
    the dial happened to be — here, 1 GHz."""
    instrument.ranges = False
    adapter = await _connected(instrument)
    try:
        frequency = adapter.schema.require("cw_frequency")
        assert frequency.limits == MODELS["SSG3021X"][0]
        assert "published specs" in frequency.description
    finally:
        await adapter.disconnect()


async def test_an_unknown_model_gets_a_wide_range_not_a_guess(instrument):
    """Refusing a legitimate setpoint is the failure that sends someone
    looking for a hardware fault, so an unrecognised model is given room."""
    instrument.ranges = False
    instrument.identity = "Siglent Technologies,SSG9999X,SN1,1.0"
    adapter = await _connected(instrument)
    try:
        _, high = adapter.schema.require("cw_frequency").limits
        assert high >= 20e9
    finally:
        await adapter.disconnect()


async def test_a_setpoint_outside_the_reported_range_is_refused(instrument):
    """The whole point of asking the instrument: the numbers that refuse a
    write are the numbers it supplied."""
    from labpilot.core.errors import LimitError

    adapter = await _connected(instrument)
    try:
        # An SSG3021X stops at 2.1 GHz, so it cannot reach the NV
        # zero-field splitting at 2.87 GHz at all — and this is where that
        # is found out, by the instrument's own number.
        with pytest.raises(LimitError, match="2100000000"):
            adapter.validate_write({"cw_frequency": 2.87e9})
        assert adapter.validate_write({"cw_frequency": 2.0e9})
    finally:
        await adapter.disconnect()


# --- Driving it ------------------------------------------------------------


async def test_setting_the_frequency_reaches_the_instrument(instrument):
    adapter = await _connected(instrument)
    try:
        await adapter.write({"cw_frequency": 2.0e9})
        assert instrument.frequency == pytest.approx(2.0e9)
        assert (await adapter.read())["frequency"] == pytest.approx(2.0e9)
    finally:
        await adapter.disconnect()


async def test_setting_the_level_reaches_the_instrument(instrument):
    adapter = await _connected(instrument)
    try:
        await adapter.write({"cw_power": -12.5})
        assert instrument.power == pytest.approx(-12.5)
    finally:
        await adapter.disconnect()


async def test_the_output_can_be_switched_as_a_setting_or_an_action(instrument):
    """Settable as well as an action so a plan's `hold` can park it on —
    a sweep against a source whose output is off measures nothing."""
    adapter = await _connected(instrument)
    try:
        await adapter.write({"output_enabled": True})
        assert instrument.output is True
        await adapter.off()
        assert instrument.output is False
        await adapter.cw_on()
        assert instrument.output is True
    finally:
        await adapter.disconnect()


async def test_a_software_sweep_steps_through_its_points(instrument):
    adapter = await _connected(instrument)
    try:
        await adapter.write(
            {"scan_start": 2.0e9, "scan_stop": 2.1e9, "scan_points": 3}
        )
        await adapter.scan_on()
        assert instrument.output is True
        assert instrument.frequency == pytest.approx(2.0e9)
        assert (await adapter.read())["mode"] == "scan"

        await adapter.trigger_next()
        assert instrument.frequency == pytest.approx(2.05e9)
        await adapter.trigger_next()
        assert instrument.frequency == pytest.approx(2.1e9)
    finally:
        await adapter.disconnect()


async def test_a_sweep_wraps_at_the_end_as_the_mock_source_does(instrument):
    adapter = await _connected(instrument)
    try:
        await adapter.write({"scan_start": 2.0e9, "scan_stop": 2.1e9, "scan_points": 2})
        await adapter.scan_on()
        await adapter.trigger_next()
        await adapter.trigger_next()
        assert (await adapter.read())["scan_index"] == 0
        assert instrument.frequency == pytest.approx(2.0e9)
    finally:
        await adapter.disconnect()


async def test_a_single_point_sweep_does_not_divide_by_zero(instrument):
    adapter = await _connected(instrument)
    try:
        adapter.scan_points = 1
        await adapter.reset_scan()
        assert instrument.frequency == pytest.approx(adapter.scan_start)
    finally:
        await adapter.disconnect()


async def test_odmr_sweep_can_find_what_to_step_and_what_to_park(instrument):
    """`odmr_sweep` resolves the swept and held parameters by tag, not by
    name, so these two tags are what make the template work unmodified."""
    from labpilot.core.device.parameter import FREQUENCY, POWER

    adapter = await _connected(instrument)
    try:
        schema = adapter.schema
        assert schema.frequency is not None and schema.frequency.name == "cw_frequency"
        assert schema.power is not None and schema.power.name == "cw_power"
        assert FREQUENCY in schema.frequency.tags
        assert POWER in schema.power.tags
    finally:
        await adapter.disconnect()


async def test_a_setpoint_waits_for_the_instrument_to_have_acted(instrument):
    """A bare SCPI write is fire-and-forget, so a sweep would measure at
    the previous point's frequency. `*OPC?` returns only once the command
    has completed."""
    adapter = await _connected(instrument)
    try:
        instrument.sent.clear()
        await adapter.write({"cw_frequency": 2.0e9})
        assert instrument.sent == [":FREQ 2000000000.000000Hz", "*OPC?"]
    finally:
        await adapter.disconnect()


async def test_synchronising_can_be_turned_off_for_throughput(instrument):
    adapter = await _connected(instrument, synchronise=False)
    try:
        instrument.sent.clear()
        await adapter.write({"cw_frequency": 2.0e9})
        assert "*OPC?" not in instrument.sent
    finally:
        await adapter.disconnect()


async def test_disconnecting_releases_the_socket(instrument):
    adapter = await _connected(instrument)
    await adapter.disconnect()
    assert adapter._scpi is None
    with pytest.raises(DeviceError, match="not connected"):
        adapter._read_sync()
