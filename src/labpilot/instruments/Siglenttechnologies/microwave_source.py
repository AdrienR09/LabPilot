"""Siglent SSG-series RF/microwave signal generator.

The microwave source for ODMR. Siglent is already represented in the
catalogue four times — `SDS1000XHD`, `SDS1072CML`, `SPD1168X`,
`SPD1305X` — and every one of those is an oscilloscope or a bench power
supply. There was no signal generator, which is what blocked
`odmr_sweep` on real hardware.

## It reaches the instrument over a plain socket

SCPI on TCP port 5025 is the IEEE-standard raw-socket interface, and the
SSG listens on it. That means **the IP address on the instrument's own
LAN screen is the entire configuration** — nothing to install, no VISA
runtime, no GPIB card. A `resource=` string still works, through pyvisa,
for a unit reached over USBTMC instead; see `instruments/_scpi.py`.

## It asks the instrument what it can do

A hand-entered frequency range is how a schema comes to disagree with
its hardware, and the SSG family spans 2.1 GHz to 6 GHz and more across
models that differ only in a digit. So on connect this adapter asks:
`:FREQ? MIN`, `:FREQ? MAX`, `:POW? MIN`, `:POW? MAX`. What comes back
becomes the schema's limits, which is what `validate_write` then
enforces — so an out-of-range setpoint is refused by numbers the
instrument itself supplied.

`MODELS` below is only the fallback, for a unit that does not answer
those queries. It is transcribed from published specifications and has
not been checked against hardware; `labpilot probe siglent_ssg
--param host=...` is how it gets checked, and the limits the instrument
reports win over the table every time.

## The sweep is stepped in software, deliberately

The SSG has an internal sweep generator. This adapter does not use it.
`reset_scan()` and `trigger_next()` step the CW frequency one setpoint at
a time, which is what `odmr_sweep` needs: that plan sets a frequency,
reads the detector, and sets the next. Driving the instrument's own
sweep instead would need its trigger wiring and its list memory, and
would put the stepping on the instrument's clock rather than the host's.

**What that costs, stated plainly:** each step is a host round trip, so
the dwell time per point is not hardware-deterministic. For CW ODMR,
where the counter gate is far longer than a socket write, that does not
matter. For a pulsed sequence where the microwave step must land inside
a gate, it does — and that case belongs to the pulser, which has the
timing, not to this source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from labpilot.core.device.parameter import FREQUENCY, POWER, Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import DeviceError
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments._scpi import SCPI_PORT, ScpiTransport

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["MODELS", "SiglentSSGAdapter"]

#: Published specifications, as a fallback only — see the module docstring.
#: Frequency in Hz, level in dBm. A model not listed here gets `_WIDEST`
#: and says so, which is better than a confident wrong number.
MODELS: Mapping[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "SSG3021X": ((9e3, 2.1e9), (-110.0, 13.0)),
    "SSG3032X": ((9e3, 3.2e9), (-110.0, 13.0)),
    "SSG5040X": ((9e3, 4.0e9), (-110.0, 13.0)),
    "SSG5060X": ((9e3, 6.0e9), (-110.0, 13.0)),
}

#: What an unrecognised model is given until it is probed. Wide enough not
#: to refuse a legitimate setpoint, which is the failure that would send
#: someone looking for a hardware fault.
_WIDEST = ((9e3, 20e9), (-130.0, 25.0))

#: A frequency range narrower than this means the MIN/MAX query was not
#: understood and answered with something else — a few instruments return
#: the current setpoint rather than an error. Trusting that would pin the
#: schema's limits to wherever the dial happened to be.
_MIN_CREDIBLE_SPAN = 1e6


class SiglentSSGAdapter(AdapterBase):
    """A Siglent SSG signal generator, CW plus a software-stepped sweep."""

    def __init__(
        self,
        host: str = "",
        port: int = SCPI_PORT,
        resource: str = "",
        timeout: float = 5.0,
        synchronise: bool = True,
        name: str = "siglent_ssg",
    ) -> None:
        super().__init__()
        self.host = host
        self.port = int(port)
        self.resource = resource
        self.timeout = float(timeout)
        self.synchronise = bool(synchronise)
        self._name = name

        self._scpi: ScpiTransport | None = None
        self._model = ""
        self._serial = ""
        self._firmware = ""
        self._limits_from_hardware = False
        self._frequency_limits, self._power_limits = _WIDEST

        # Sweep state, held here because the instrument's own sweep is not
        # the one being used.
        self.scan_start = 2.82e9
        self.scan_stop = 2.92e9
        self.scan_points = 101
        self._scan_index = 0
        self._scanning = False

    # --- Schema -----------------------------------------------------------

    @property
    def schema(self) -> DeviceSchema:
        low, high = self._frequency_limits
        floor, ceiling = self._power_limits
        source = "the instrument" if self._limits_from_hardware else "published specs"
        return DeviceSchema(
            name=self._name,
            kind="source",
            parameters=(
                Parameter(
                    "cw_frequency", unit="Hz", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(low, high),
                    tags=frozenset({FREQUENCY}),
                    description=f"Carrier frequency. Range from {source}.",
                ),
                Parameter(
                    "cw_power", unit="dBm", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(floor, ceiling),
                    tags=frozenset({POWER}),
                    description=f"Output level. Range from {source}.",
                ),
                Parameter(
                    "output_enabled", dtype="bool", role=ParamRole.SETTING,
                    settable=True, readable=False,
                    description=(
                        "RF output on or off. Settable as well as an action, so "
                        "a plan can park it on before a sweep."
                    ),
                ),
                Parameter("frequency", unit="Hz", role=ParamRole.STATUS),
                Parameter("power", unit="dBm", role=ParamRole.STATUS),
                Parameter("output_on", dtype="bool", role=ParamRole.STATUS),
                Parameter("mode", dtype="str", role=ParamRole.STATUS),
                Parameter("scan_index", dtype="i8", role=ParamRole.STATUS),
                Parameter("scan_total_points", dtype="i8", role=ParamRole.STATUS),
                Parameter("model", dtype="str", role=ParamRole.STATUS),
                Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                Parameter(
                    "scan_start", unit="Hz", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(low, high),
                ),
                Parameter(
                    "scan_stop", unit="Hz", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(low, high),
                ),
                Parameter(
                    "scan_points", dtype="i8", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(2, 100001),
                ),
            ),
            tags=["Siglent", "SSG", "Microwave", "RF", "SignalGenerator", "ODMR", "SCPI"],
            actions=["cw_on", "scan_on", "off", "reset_scan", "trigger_next"],
        )

    # --- Lifecycle --------------------------------------------------------

    def _connect_sync(self) -> None:
        self._scpi = ScpiTransport(
            host=self.host, port=self.port, resource=self.resource,
            timeout=self.timeout, device=self._name,
        )
        self._scpi.open()
        try:
            self._identify()
            self._learn_limits()
        except Exception:
            # A half-identified instrument is worse than none: the schema
            # would carry placeholder limits that `validate_write` then
            # enforces as if they were real.
            self._scpi.close()
            self._scpi = None
            raise

    def _identify(self) -> None:
        answer = self._wire.query("*IDN?")
        fields = [field.strip() for field in answer.split(",")]
        if len(fields) < 2 or "siglent" not in fields[0].lower():
            raise DeviceError(
                f"*IDN? answered {answer!r}, which is not a Siglent instrument. "
                f"Check the address.",
                device=self._name,
            )
        model = fields[1].upper()
        # Siglent's other catalogued instruments are an SDS oscilloscope and
        # an SPD power supply, and a bench often has two of them on one
        # subnet. `:FREQ` sent to a scope is accepted-looking nonsense, so
        # the model is checked and not only the manufacturer.
        if not model.startswith("SSG"):
            raise DeviceError(
                f"{self.host or self.resource} is a Siglent {model}, not an SSG "
                f"signal generator — an SDS is an oscilloscope and an SPD a "
                f"power supply. Check the address.",
                device=self._name,
            )
        self._model = model
        self._serial = fields[2] if len(fields) > 2 else ""
        self._firmware = fields[3] if len(fields) > 3 else ""

    def _learn_limits(self) -> None:
        """Ask the instrument its own ranges; fall back to the table.

        Both queries have to succeed *and* be credible — see
        `_MIN_CREDIBLE_SPAN`.
        """
        frequency = self._queried_range(":FREQ? MIN", ":FREQ? MAX", _MIN_CREDIBLE_SPAN)
        power = self._queried_range(":POW? MIN", ":POW? MAX", 1.0)
        if frequency and power:
            self._frequency_limits, self._power_limits = frequency, power
            self._limits_from_hardware = True
            return
        self._frequency_limits, self._power_limits = MODELS.get(self._model, _WIDEST)
        self._limits_from_hardware = False

    def _queried_range(
        self, low_command: str, high_command: str, least_span: float
    ) -> tuple[float, float] | None:
        try:
            low = self._wire.query_float(low_command)
            high = self._wire.query_float(high_command)
        except DeviceError:
            return None
        return (low, high) if high - low >= least_span else None

    def _disconnect_sync(self) -> None:
        if self._scpi is not None:
            self._scpi.close()
            self._scpi = None

    @property
    def _wire(self) -> ScpiTransport:
        if self._scpi is None:
            raise DeviceError(
                f"{self._name} is not connected", device=self._name
            )
        return self._scpi

    # --- Reading ----------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        return {
            "frequency": self._wire.query_float(":FREQ?"),
            "power": self._wire.query_float(":POW?"),
            "output_on": self._wire.query_bool(":OUTP?"),
            "mode": "scan" if self._scanning else "cw",
            "scan_index": self._scan_index,
            "scan_total_points": int(self.scan_points),
            "model": self._model,
            "serial_number": self._serial,
        }

    # --- Setters, which is how a ScanPlan drives this ---------------------

    async def set_cw_frequency(self, value: float) -> None:
        await self._to_thread(self._command, f":FREQ {float(value):.6f}Hz")

    async def set_cw_power(self, value: float) -> None:
        await self._to_thread(self._command, f":POW {float(value):.3f}dBm")

    async def set_output_enabled(self, value: bool) -> None:
        await self._to_thread(self._command, f":OUTP {'ON' if value else 'OFF'}")

    def _command(self, command: str) -> None:
        """Send one setpoint, and by default wait for it to have landed.

        A bare SCPI write is fire-and-forget: the socket accepts it and
        the call returns, whether or not the instrument has acted. In a
        sweep that is the difference between measuring at the frequency
        the axis says and measuring at the previous one — the plan sets a
        point and reads the counter immediately, because this source is
        written through `cw_frequency` and reports through `frequency`, so
        `move_and_settle` correctly does not apply to it
        (`core/run/plans.py::_command`).

        `*OPC?` is the standard answer: it returns only once the preceding
        command has completed. It costs one round trip per point, which on
        a LAN is far below any ODMR dwell time. `synchronise=False` drops
        it for a sweep where throughput matters more than a known
        settling point.
        """
        self._wire.write(command)
        if self.synchronise:
            self._wire.query("*OPC?")

    async def set_scan_start(self, value: float) -> None:
        self.scan_start = float(value)

    async def set_scan_stop(self, value: float) -> None:
        self.scan_stop = float(value)

    async def set_scan_points(self, value: int) -> None:
        self.scan_points = int(value)

    # --- Actions ----------------------------------------------------------

    async def cw_on(self) -> None:
        """Output on, at whatever frequency and level are already set."""
        self._scanning = False
        await self.set_output_enabled(True)

    async def off(self) -> None:
        self._scanning = False
        await self.set_output_enabled(False)

    async def scan_on(self) -> None:
        """Begin a software-stepped sweep at its first point, output on."""
        self._scanning = True
        await self.reset_scan()
        await self.set_output_enabled(True)

    async def reset_scan(self) -> None:
        self._scan_index = 0
        await self.set_cw_frequency(self._scan_frequency(0))

    async def trigger_next(self) -> None:
        """Advance one point, wrapping at the end as the mock source does."""
        self._scan_index = (self._scan_index + 1) % max(int(self.scan_points), 1)
        await self.set_cw_frequency(self._scan_frequency(self._scan_index))

    def _scan_frequency(self, index: int) -> float:
        points = max(int(self.scan_points), 1)
        if points == 1:
            return float(self.scan_start)
        step = (float(self.scan_stop) - float(self.scan_start)) / (points - 1)
        return float(self.scan_start) + step * index


adapter_registry.register("siglent_ssg", SiglentSSGAdapter)
