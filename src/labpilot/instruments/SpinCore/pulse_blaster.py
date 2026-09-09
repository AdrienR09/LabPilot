"""SpinCore PulseBlaster ESR-PRO — a digital-only sequencer.

Up to 24 TTL channels driven from a compiled instruction list, through
SpinCore's `spinapi` ctypes wrapper over the vendor shared library.
`pip install spinapi` plus the vendor driver (an optional extra).

## No analog output at all

Which is the point of supporting it. A PulseBlaster rig gates an external
microwave source with a TTL line rather than synthesising the drive, and
`RigProfile(analog_mw=False)` describes exactly that — the same Rabi,
Ramsey, Hahn echo and T1 sequence files play here unchanged, with the
microwave channel becoming a gate instead of a `Sin`.

An analog `Shape` in a sequence is therefore a real error here, not a
rounding: this device cannot express it, and saying so at upload beats
producing a plausible measurement with no microwave in it.

## Two constraints that bite

- **A 5-clock minimum instruction.** At the ESR-PRO's 500 MHz core clock
  that is 10 ns, and an instruction below it is refused rather than
  padded — padding would silently lengthen a pi pulse.
- **The channel count depends on the board.** Declared as activation
  configs, which is the whole reason that concept exists: a sequence using
  channel 20 fits a 24-channel board and not a 12-channel one, and this is
  where that is caught.

## Importing without the SDK

`spinapi` is imported inside `_connect_sync`, so the adapter registers,
`describe()` answers and the catalogue lists it on a machine that has
never had a board in it. Failure happens at connect, naming the package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.pulse.sampling import SamplingError, expand
from labpilot.core.pulse.shapes import Shape
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.pulser_mixin import (
    PulserMixin,
    SequenceReport,
    pulser_constraints,
    quantise_elements,
)

if TYPE_CHECKING:
    from labpilot.core.pulse.sequence import ChannelMap, PulseSequence

__all__ = ["PulseBlasterAdapter"]

#: Instructions must be at least this many core-clock cycles. SpinCore's
#: own documented floor, and the one every PulseBlaster user meets first.
MIN_CYCLES = 5


class PulseBlasterAdapter(PulserMixin, AdapterBase):
    """SpinCore PulseBlaster ESR-PRO."""

    def __init__(
        self,
        board: int = 0,
        clock_mhz: float = 500.0,
        channels: int = 24,
        name: str = "pulse_blaster",
    ) -> None:
        super().__init__()
        self._board = int(board)
        self._clock_mhz = float(clock_mhz)
        self._channels = int(channels)
        self._name = name
        self._api: Any = None
        self._program: list[tuple[int, int]] = []
        self._report: SequenceReport | None = None
        self._running = False

    @property
    def resolution(self) -> float:
        """One core-clock cycle, in seconds."""
        return 1.0 / (self._clock_mhz * 1e6)

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="generic",
            parameters=(
                Parameter("running", dtype="bool", role=ParamRole.STATUS),
                Parameter("instructions", dtype="i8", role=ParamRole.STATUS),
                Parameter("readouts", dtype="i8", role=ParamRole.STATUS),
                Parameter("sequence_duration", unit="s", role=ParamRole.STATUS),
                Parameter(
                    "clock_mhz", unit="MHz", role=ParamRole.SETTING,
                    settable=False, readable=True,
                ),
                Parameter("board", dtype="i8", role=ParamRole.SETTING,
                          settable=False, readable=True),
            ),
            tags=[
                "SpinCore", "Pulser", "PulseBlaster", "Digital", "TTL",
                "ODMR", "Pulsed",
            ],
            actions=["pulser_on", "pulser_off"],
        )

    def pulser_constraints(self):
        """Digital only, with a real minimum instruction length.

        `analog_channels` is empty, which is what makes an analog shape
        fail the activation check rather than being silently dropped.
        """
        return pulser_constraints(
            sample_rate=self._clock_mhz * 1e6,
            digital_channels=tuple(f"d_ch{i}" for i in range(self._channels)),
            min_element=MIN_CYCLES * self.resolution,
            element_step=self.resolution,
        )

    def _connect_sync(self) -> None:
        try:
            import spinapi
        except ImportError as error:
            raise ImportError(
                "The PulseBlaster driver needs the vendor package: "
                "pip install spinapi (and SpinCore's shared library)"
            ) from error

        self._api = spinapi
        spinapi.pb_select_board(self._board)
        if spinapi.pb_init() != 0:
            raise ConnectionError(
                f"PulseBlaster board {self._board}: {spinapi.pb_get_error()}"
            )
        spinapi.pb_core_clock(self._clock_mhz)

    def _disconnect_sync(self) -> None:
        if self._api is not None:
            self._api.pb_stop()
            self._api.pb_close()
        self._api = None
        self._running = False

    def _read_sync(self) -> dict[str, Any]:
        report = self._report
        return {
            "running": self._running,
            "instructions": report.instructions if report else 0,
            "readouts": report.readouts if report else 0,
            "sequence_duration": report.duration if report else 0.0,
            "clock_mhz": self._clock_mhz,
            "board": self._board,
        }

    async def upload_sequence(
        self, sequence: PulseSequence, channels: ChannelMap
    ) -> SequenceReport:
        sequence.validate()
        constraints = self.pulser_constraints()

        # Before the activation check, deliberately: an analog shape on a
        # board with no analog output would otherwise surface as "these
        # channels cannot be active together", which is true and unhelpful.
        analog = sorted(
            channel
            for block in sequence.blocks
            for element in block.elements
            for channel, value in element.channels.items()
            if isinstance(value, Shape)
        )
        if analog:
            raise SamplingError(
                f"Sequence {sequence.name!r} drives {', '.join(analog)} with an "
                f"analog shape; a PulseBlaster has no analog output. Author it "
                f"with RigProfile(analog_mw=False) so the microwave channel "
                f"gates an external source instead."
            )

        activation = constraints.check(sequence, channels)
        intervals = list(expand(sequence))
        quantised = quantise_elements(
            intervals, constraints, minimum=MIN_CYCLES * self.resolution
        )
        self._program = self._compile(intervals, channels)

        self._report = SequenceReport(
            name=sequence.name,
            channels={symbolic: channels[symbolic] for symbolic in sequence.channels},
            points=sequence.points,
            readouts=sequence.readouts(),
            duration=sequence.duration,
            quantised=quantised,
            instructions=len(intervals),
            activation=activation,
        )
        return self._report

    def _compile(
        self, intervals: list[Any], channels: ChannelMap
    ) -> list[tuple[int, int]]:
        """`(channel_mask, duration_ns)` per element — spinapi's own form."""
        index = {f"d_ch{i}": i for i in range(self._channels)}
        program: list[tuple[int, int]] = []
        for interval in intervals:
            mask = 0
            for symbolic, value in interval.channels.items():
                physical = channels[symbolic]
                if value is True and physical in index:
                    mask |= 1 << index[physical]
            program.append((mask, round(interval.duration * 1e9)))
        return program

    async def pulser_on(self) -> None:
        if not self._program:
            raise RuntimeError(
                f"{self._name} has no sequence loaded — call upload_sequence first"
            )
        api = self._require_api()
        api.pb_start_programming(api.PULSE_PROGRAM)
        first = None
        for position, (mask, duration_ns) in enumerate(self._program):
            # The last instruction branches back to the first, so the
            # sequence free-runs until pulser_off — which is what
            # averaging over sweeps needs.
            last = position == len(self._program) - 1
            instruction = api.BRANCH if last else api.CONTINUE
            target = first if last else 0
            handle = api.pb_inst_pbonly(
                mask, instruction, target or 0, duration_ns * api.ns
            )
            if first is None:
                first = handle
        api.pb_stop_programming()
        api.pb_reset()
        api.pb_start()
        self._running = True

    async def pulser_off(self) -> None:
        # Safe when nothing is playing: an abort calls this and cannot
        # know how far the run got.
        if self._api is not None:
            self._api.pb_stop()
        self._running = False

    def _require_api(self) -> Any:
        if self._api is None:
            raise RuntimeError(f"{self._name} is not connected")
        return self._api


adapter_registry.register("spincore_pulse_blaster", PulseBlasterAdapter)
