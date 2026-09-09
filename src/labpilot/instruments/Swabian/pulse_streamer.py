"""Swabian Instruments Pulse Streamer 8/2 — a digital sequencer.

Eight digital channels at 1 ns resolution plus two analog outputs, driven
over the network. `pip install pulsestreamer` (an optional extra).

## Instructions, never samples

The device's own API takes `(duration_ns, digital_mask, a0, a1)` tuples,
so this driver walks `expand()` and emits one tuple per element. It never
builds an array, which is the whole reason `upload_sequence` takes the
abstract sequence.

Qudi's driver for this same device has to go the other way — its pulser
interface is `write_waveform(analog_samples, digital_samples)`, so the
logic layer hands it five million booleans for a 5 ms idle and the driver
compresses them back into one instruction. Its source notes that
`waveform_length` is ill-defined here for exactly that reason.

## The analog channels are not an AWG

They hold a constant voltage for the duration of an element — a level, not
a waveform. So an analog `Shape` is honoured only where it is effectively
constant (`DC`), and a `Sin` on this device would need an external
microwave source gated by a digital line. That is the usual NV rig anyway:
`RigProfile(analog_mw=False)` describes it, and the same sequence file
then plays here unchanged.

## Importing without the SDK

The vendor package is imported inside `_connect_sync`, not at module
level, so the adapter registers, `describe()` answers, and the catalogue
lists it on a machine that has never seen a Pulse Streamer. Failure
happens at connect, where it can name the missing package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.pulse.sampling import expand
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

__all__ = ["PulseStreamerAdapter"]

#: 1 ns, the device's own timing resolution.
RESOLUTION = 1e-9


class PulseStreamerAdapter(PulserMixin, AdapterBase):
    """Swabian Pulse Streamer 8/2."""

    def __init__(
        self, resource: str = "192.168.1.100", name: str = "pulse_streamer"
    ) -> None:
        super().__init__()
        self._resource = resource
        self._name = name
        self._device: Any = None
        self._sequence: Any = None
        self._report: SequenceReport | None = None
        self._running = False

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
                    "address", dtype="str", role=ParamRole.SETTING,
                    settable=False, readable=True,
                ),
            ),
            tags=[
                "Swabian", "Pulser", "PulseStreamer", "Digital", "TTL",
                "ODMR", "Pulsed",
            ],
            actions=["pulser_on", "pulser_off"],
        )

    def pulser_constraints(self):
        """1 ns timing grid, no sample memory.

        Its memory holds instructions (~10^6 of them), so there is no
        `waveform_length` to advertise — see `pulser_mixin`'s
        `quantise_elements` for where this device's rounding really
        happens.
        """
        return pulser_constraints(
            sample_rate=1.0 / RESOLUTION,
            digital_channels=tuple(f"d_ch{i}" for i in range(8)),
            analog_channels=("a_ch0", "a_ch1"),
            min_element=RESOLUTION,
            element_step=RESOLUTION,
        )

    def _connect_sync(self) -> None:
        try:
            from pulsestreamer import PulseStreamer
        except ImportError as error:
            raise ImportError(
                "The Pulse Streamer driver needs the vendor package: "
                "pip install pulsestreamer"
            ) from error
        self._device = PulseStreamer(self._resource)

    def _disconnect_sync(self) -> None:
        if self._device is not None:
            self._device.constant()  # every channel to its idle level
        self._device = None
        self._running = False

    def _read_sync(self) -> dict[str, Any]:
        report = self._report
        return {
            "running": bool(self._device.isStreaming()) if self._device else False,
            "instructions": report.instructions if report else 0,
            "readouts": report.readouts if report else 0,
            "sequence_duration": report.duration if report else 0.0,
            "address": self._resource,
        }

    async def upload_sequence(
        self, sequence: PulseSequence, channels: ChannelMap
    ) -> SequenceReport:
        sequence.validate()
        constraints = self.pulser_constraints()
        activation = constraints.check(sequence, channels)

        intervals = list(expand(sequence))
        quantised = quantise_elements(intervals, constraints, minimum=RESOLUTION)
        self._sequence = self._compile(intervals, channels)

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

    def _compile(self, intervals: list[Any], channels: ChannelMap) -> list[tuple]:
        """`(duration_ns, digital_mask, a0, a1)` per element.

        The device's own instruction format, built directly from the
        abstract sequence — no intermediate array exists at any point.
        """
        digital_index = {f"d_ch{i}": i for i in range(8)}
        analog_index = {"a_ch0": 0, "a_ch1": 1}

        program: list[tuple] = []
        for interval in intervals:
            mask = 0
            analog = [0.0, 0.0]
            for symbolic, value in interval.channels.items():
                physical = channels[symbolic]
                if physical in digital_index:
                    if value is True:
                        mask |= 1 << digital_index[physical]
                elif physical in analog_index and isinstance(value, Shape):
                    # A level, not a waveform — see the module docstring.
                    analog[analog_index[physical]] = float(
                        getattr(value, "voltage", getattr(value, "amplitude", 0.0))
                    )
            program.append(
                (round(interval.duration / RESOLUTION), mask, *analog)
            )
        return program

    async def pulser_on(self) -> None:
        from pulsestreamer import TriggerRearm, TriggerStart

        if self._sequence is None:
            raise RuntimeError(
                f"{self._name} has no sequence loaded — call upload_sequence first"
            )
        device = self._require_device()
        # Free-running: the sequence repeats until pulser_off, which is
        # what averaging over sweeps needs. A rig that gates on an
        # external trigger sets this differently.
        device.setTrigger(start=TriggerStart.IMMEDIATE, rearm=TriggerRearm.MANUAL)
        device.stream(self._build_stream(), n_runs=-1)
        self._running = True

    async def pulser_off(self) -> None:
        # Safe when nothing is playing: an abort calls this and cannot
        # know how far the run got.
        if self._device is not None:
            self._device.forceFinal()
            self._device.constant()
        self._running = False

    def _build_stream(self) -> Any:
        from pulsestreamer import Sequence

        stream = Sequence()
        for index in range(8):
            pattern = [
                (duration, 1 if mask >> index & 1 else 0)
                for duration, mask, _a0, _a1 in self._sequence
            ]
            stream.setDigital(index, pattern)
        for index in range(2):
            stream.setAnalog(
                index,
                [(entry[0], entry[2 + index]) for entry in self._sequence],
            )
        return stream

    def _require_device(self) -> Any:
        if self._device is None:
            raise RuntimeError(f"{self._name} is not connected")
        return self._device


adapter_registry.register("swabian_pulse_streamer", PulseStreamerAdapter)
