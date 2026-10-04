"""NKT Photonics SuperK — the supercontinuum white-light source.

A SuperK Fianium or Extreme, over NKT's Interbus protocol on a serial
port. The Fianium and the Extreme share the same main-module interface,
which is why one adapter covers both.

## The register map is not retyped here

NKT's Interbus is a register protocol: emission is register `0x30`, the
power setpoint `0x37` in units of 0.1%, the inlet temperature `0x11` in
units of 0.1 degrees. pylablib's `SuperKExtremeInterbusModule` already
encodes that table with its scale factors, so this adapter addresses
registers **by name** and never by number. Retyping the numbers would add
a second place for them to be wrong, and the scale factors are exactly the
kind of detail that turns 60% into 600% silently.

`InterbusSystem(conn, modules="auto")` enumerates what is on the bus and
checks each module's type byte, so pointing this at a rack with a SuperK
plus a SELECT or a VARIA finds the laser rather than the first address
that answers. Only the laser's main module is adapted here; a VARIA or
SELECT filter is a separate module on the same bus and would be a separate
adapter against the same transport.

## It will not switch your laser on or off behind your back

Emission is changed only when something asks for it. Specifically:

- connecting does **not** enable emission, which should not need saying;
- disconnecting does **not** disable it either, by default, which does.
  A Class 4 laser whose emission is tied to a software connection is a
  laser that goes dark because a window was closed or a backend was
  restarted — in the middle of a measurement that may have taken an hour
  to stabilise. The key switch and the hardware interlock are the safety
  system; this adapter is not.

`stop_emission_on_disconnect=True` chooses the other policy for a lab that
wants it, and it is a real choice rather than an oversight either way.

**The watchdog is deliberately not exposed.** The SuperK can be told to
shut down unless the host keeps talking to it, which is a genuine safety
feature — and enabling it means promising that something will keep
servicing it. This adapter cannot make a promise about its own process
staying alive, and a half-kept one is worse than none: the laser would
switch off mid-run. Set it from NKT's own software, where the promise is
theirs.

Driven through pylablib's NKT Interbus layer (GPL v3 — see the licensing
notes), imported inside `_connect_sync`, so this adapter registers,
describes itself and is probeable without it. **Not run against
hardware** — `labpilot probe nkt_superk --param port=COM4` is what settles
the module address and which registers this unit answers.
"""

from __future__ import annotations

import contextlib
from typing import Any

from labpilot.core.device.parameter import POWER, Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import DeviceError
from labpilot.instruments._base import AdapterBase, adapter_registry

__all__ = ["EMISSION_OFF", "EMISSION_ON", "SuperKAdapter"]

#: NKT's own convention for register 0x30. Not a boolean: writing 1 is not
#: "on", and this is the one value in the protocol worth naming.
EMISSION_ON = 3
EMISSION_OFF = 0

#: The SuperK main module's Interbus type byte, which is how the right
#: module is picked out of a rack rather than by trusting an address.
SUPERK_TYPE = 0x60

#: NKT's default. The bus is multi-drop, so every module on it shares one.
DEFAULT_BAUDRATE = 115200


class SuperKAdapter(AdapterBase):
    """A SuperK Fianium or Extreme main module.

    Args:
        port: The serial port the Interbus is on (`COM4`, `/dev/ttyUSB0`).
        baudrate: NKT's default is 115200 and applies to the whole bus.
        address: The module's Interbus address, or 0 to find the laser by
            its type byte — which is the robust choice on a rack with a
            SELECT or VARIA on the same bus.
        stop_emission_on_disconnect: Whether closing the connection also
            stops the laser. Default no; see the module docstring, because
            both answers are defensible and the default is a choice.
    """

    def __init__(
        self,
        port: str = "",
        baudrate: int = DEFAULT_BAUDRATE,
        address: int = 0,
        stop_emission_on_disconnect: bool = False,
        name: str = "nkt_superk",
    ) -> None:
        super().__init__()
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.address = int(address)
        self.stop_on_disconnect = bool(stop_emission_on_disconnect)
        self._name = name

        self._bus: Any = None
        self._laser: Any = None
        self._serial = ""
        self._module_address = 0

    # --- What it is --------------------------------------------------------

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            parameters=(
                Parameter(
                    "emission", dtype="bool", settable=True, readable=False,
                    role=ParamRole.SETTING,
                    description=(
                        "Laser emission. Writing True sends NKT's value 3, "
                        "not 1 — see EMISSION_ON."
                    ),
                ),
                Parameter(
                    "power_percent", unit="%", settable=True, readable=False,
                    role=ParamRole.SETTING, limits=(0.0, 100.0),
                    tags=frozenset({POWER}),
                    description="Output power, as a percentage of maximum",
                ),
                Parameter(
                    "current_percent", unit="%", settable=True, readable=False,
                    role=ParamRole.SETTING, limits=(0.0, 100.0),
                    description=(
                        "Pump current, as a percentage. The alternative "
                        "setpoint to power; which one the laser follows is "
                        "its operating mode."
                    ),
                ),
                Parameter(
                    "pulse_picker_ratio", dtype="i8", settable=True,
                    readable=False, role=ParamRole.SETTING, limits=(1, None),
                    description=(
                        "Divides the repetition rate: 1 fires every pulse, "
                        "10 one in ten."
                    ),
                ),
                Parameter(
                    "emitting", dtype="bool", role=ParamRole.STATUS,
                    description="Whether light is actually coming out",
                ),
                Parameter(
                    "interlock_ok", dtype="bool", role=ParamRole.STATUS,
                    description="False means the interlock loop is open",
                ),
                Parameter("power", unit="%", role=ParamRole.STATUS),
                Parameter("current", unit="%", role=ParamRole.STATUS),
                Parameter("pulse_picker", dtype="i8", role=ParamRole.STATUS),
                Parameter(
                    "inlet_temperature", unit="degC", role=ParamRole.STATUS,
                    description="Cooling water in. Rising means check the chiller.",
                ),
                Parameter(
                    "status", dtype="str", role=ParamRole.STATUS,
                    description="The module's own status bits, decoded",
                ),
                Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                Parameter("module_address", dtype="i8", role=ParamRole.STATUS),
            ),
            actions=["emission_on", "emission_off"],
            tags=[
                "NKT Photonics", "SuperK", "Fianium", "Extreme", "laser",
                "supercontinuum", "white-light", "source",
            ],
        )

    # --- Connection --------------------------------------------------------

    def _import(self) -> Any:
        try:
            from pylablib.devices.NKT import interbus
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise ImportError(
                "Talking to a SuperK needs pylablib's NKT Interbus support: "
                "pip install 'labpilot[pylablib]'. Describing one needs "
                "nothing."
            ) from exc
        return interbus

    def _connect_sync(self) -> None:
        if not self.port:
            raise DeviceError(
                "A SuperK is reached over a serial port; pass port=COM4 (or "
                "/dev/ttyUSB0). The Interbus is multi-drop, so one port "
                "carries the whole rack.",
                device=self._name,
            )
        interbus = self._import()
        self._bus = interbus.InterbusSystem(
            (self.port, self.baudrate),
            modules=[self.address] if self.address else "auto",
        )
        try:
            self._laser = self._find_laser(interbus)
            self._serial = str(self._laser.get_register("serial") or "")
        except Exception:
            self._bus.close()
            self._bus = None
            raise

    def _find_laser(self, interbus: Any) -> Any:
        """The SuperK main module, picked out by its type byte.

        A rack holds the laser plus whatever filters are fitted, all on one
        bus. Taking the first module that answers would, on a rig with a
        SELECT, point this adapter at an acousto-optic filter and then
        write an emission register it does not have.
        """
        modules = dict(getattr(self._bus, "m", {}) or {})
        for key, module in modules.items():
            if isinstance(module, interbus.SuperKExtremeInterbusModule):
                self._module_address = key if isinstance(key, int) else getattr(
                    module, "dest", 0
                )
                return module
        found = ", ".join(
            f"0x{getattr(m, 'dtype', 0):02X}" for m in modules.values()
        ) or "nothing"
        raise DeviceError(
            f"No SuperK main module (type 0x{SUPERK_TYPE:02X}) on the Interbus "
            f"at {self.port}; found {found}. A SELECT or VARIA answers on the "
            f"same bus and is a different module.",
            device=self._name,
        )

    def _disconnect_sync(self) -> None:
        # Emission is left exactly as it is unless the lab asked otherwise —
        # see the module docstring. The ordering matters: stop the laser
        # before dropping the bus, or the request never leaves.
        if self._laser is not None and self.stop_on_disconnect:
            with contextlib.suppress(Exception):
                self._laser.set_register("emission", EMISSION_OFF)
        if self._bus is not None:
            with contextlib.suppress(Exception):
                self._bus.close()
        self._bus = self._laser = None

    def _require(self) -> Any:
        if self._laser is None:
            raise DeviceError(f"{self._name} is not connected", device=self._name)
        return self._laser

    # --- Reading ----------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        laser = self._require()
        status = list(laser.get_status())
        return {
            # From the status bits rather than the emission register: this
            # is whether light is coming out, not what was last asked for.
            "emitting": "emission" in status,
            "interlock_ok": "interlock_off" not in status,
            "power": float(laser.get_register("power")),
            "current": float(laser.get_register("current")),
            "pulse_picker": int(laser.get_register("pulse_picker_ratio")),
            "inlet_temperature": float(laser.get_register("temperature_inlet")),
            "status": ", ".join(status),
            "serial_number": self._serial,
            "module_address": int(self._module_address),
        }

    # --- Settings ----------------------------------------------------------

    async def set_emission(self, value: bool) -> None:
        await self._to_thread(
            lambda: self._require().set_register(
                "emission", EMISSION_ON if value else EMISSION_OFF
            )
        )

    async def set_power_percent(self, value: float) -> None:
        await self._to_thread(
            lambda: self._require().set_register("power", float(value))
        )

    async def set_current_percent(self, value: float) -> None:
        await self._to_thread(
            lambda: self._require().set_register("current", float(value))
        )

    async def set_pulse_picker_ratio(self, value: int) -> None:
        await self._to_thread(
            lambda: self._require().set_register(
                "pulse_picker_ratio", max(int(value), 1)
            )
        )

    # --- Actions ------------------------------------------------------------

    async def emission_on(self) -> None:
        """Start emission. Nothing else in this adapter does this."""
        await self.set_emission(True)

    async def emission_off(self) -> None:
        """Stop emission. Safe to call when it is already off, which is
        what makes it usable from an abort path."""
        await self.set_emission(False)


adapter_registry.register("nkt_superk", SuperKAdapter)
