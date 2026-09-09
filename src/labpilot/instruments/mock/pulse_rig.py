"""A simulated pulsed-ODMR rig: a pulser and a gated counter.

Together these are enough to run Rabi, Ramsey, Hahn echo and T1 end to
end with no hardware — which is what lets the measurement plan, the
extraction and the fits be verified rather than hoped at.

## The pulser is deliberately awkward

`MockPulser` has 8 ns granularity, a minimum element length, a finite
memory and real activation configs. A mock with none of those is worse
than no mock: it makes every sequence upload cleanly and then a
PulseBlaster refuses the same file in the lab. Qudi's own note is that
`activation_config` — which channels may be enabled together — is the
constraint people omit, so this one enforces it.

It never samples. `upload_sequence` walks `expand()` and counts
instructions, which is what a Swabian PulseStreamer and a SpinCore
PulseBlaster genuinely do; a 20-point T1 is 120 instructions here and
17.5 million booleans if anyone were to sample it.

## The counter simulates NV physics

`MockGatedCounter` produces a real readout transient — bright at the start
of the laser window, decaying to a steady state — modulated per readout by
the spin state the sequence prepared. So the counts fall off the same way
real ones do, extraction has an actual edge to find, and a Rabi fit
recovers the injected pi-pulse length.

Counts are Poisson, accumulated over sweeps, and sweeps accrue at the rate
the sequence's own duration implies — the same "paced by real elapsed time
against the configured rate" convention `mock/hardware_scan.py` uses.

## Why the two share a module-level bench

The counter needs to know how many readouts the sequence has and what it
swept, and on a real rig it learns that through a cable: the pulser raises
the gate line and the counter counts the edges. There is no cable here, so
the pulser records what it loaded and the counter reads it — `_BENCH`
below. It stands in for the wiring, and it is the one thing in this file
that has no counterpart in real hardware.
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta
from labpilot.core.device.constraints import Constraints, Quantised, ScalarConstraint
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.pulse.sampling import expand
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.gated_counter_mixin import (
    BIN_WIDTH,
    GATES,
    RECORD_LENGTH,
    GateConfig,
    GatedCounterMixin,
)
from labpilot.instruments.pulser_mixin import (
    PulserMixin,
    SequenceReport,
    pulser_constraints,
    quantise_elements,
)

if TYPE_CHECKING:
    from labpilot.core.pulse.sequence import ChannelMap, PulseSequence

__all__ = ["MockGatedCounter", "MockPulser"]


class _Bench:
    """What the two mocks would learn from each other through a cable.

    One process-wide instance, because a mock rig is one bench. A test
    that wants isolation calls `clear()`.
    """

    def __init__(self) -> None:
        self.sequence: PulseSequence | None = None
        self.playing = False

    def clear(self) -> None:
        self.sequence = None
        self.playing = False


_BENCH = _Bench()


# --- The pulser -------------------------------------------------------------


class MockPulser(PulserMixin, AdapterBase):
    """A simulated 8-channel digital sequencer with 2 analog outputs.

    `kind="generic"`: the interesting contract is
    `upload_sequence`/`pulser_on`/`pulser_off`, not read and write — the
    same call `mock_ni_scanner` already makes. What makes it a pulser
    rather than a nondescript generic device is the composed `pulser`
    capability, which is on the schema and therefore on the wire.
    """

    #: 8 ns, so a 20 ns pi/2 pulse is a real quantisation event rather
    #: than a rounding curiosity.
    GRANULARITY = 8

    def __init__(
        self, name: str = "mock_pulser", digital_channels: int = 8,
        analog_channels: int = 2,
    ) -> None:
        super().__init__()
        self._name = name
        self._digital = tuple(f"d_ch{i + 1}" for i in range(digital_channels))
        self._analog = tuple(f"a_ch{i + 1}" for i in range(analog_channels))
        self._running = False
        self._report: SequenceReport | None = None

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="generic",
            parameters=(
                Parameter("running", dtype="bool", role=ParamRole.STATUS),
                Parameter("instructions", dtype="i8", role=ParamRole.STATUS),
                Parameter("readouts", dtype="i8", role=ParamRole.STATUS),
                Parameter(
                    "sequence_duration", unit="s", role=ParamRole.STATUS,
                    description="Played length of the loaded sequence",
                ),
                Parameter(
                    "sample_rate", unit="Hz", role=ParamRole.SETTING,
                    settable=False, readable=True,
                ),
            ),
            tags=[
                "Mock", "Pulser", "PulseSequencer", "TTL", "Digital",
                "PulseStreamer", "PulseBlaster", "ODMR", "Pulsed",
            ],
            actions=["pulser_on", "pulser_off"],
        )

    def pulser_constraints(self):
        """8 ns timing granularity, not 8 ns of memory granularity.

        This device holds instructions, not samples, so its quantisation
        is per *element*: every interval snaps to a multiple of 8 ns.
        Advertising a `waveform_length` it never allocates would report
        adjustments that correspond to nothing it does.
        """
        return pulser_constraints(
            sample_rate=1e9,
            digital_channels=self._digital,
            analog_channels=self._analog,
            element_step=self.GRANULARITY * 1e-9,
            min_element=self.GRANULARITY * 1e-9,
            # Both analog channels together cost the last two digital
            # lines, which is the shape a real device's channel budget
            # takes and the thing a mock with one config never catches.
            activation_configs=(
                self._digital,
                (*self._analog, *self._digital[:-2]),
            ),
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        _BENCH.clear()

    def _read_sync(self) -> dict[str, Any]:
        report = self._report
        return {
            "running": self._running,
            "instructions": report.instructions if report else 0,
            "readouts": report.readouts if report else 0,
            "sequence_duration": report.duration if report else 0.0,
            "sample_rate": 1e9,
        }

    async def upload_sequence(
        self, sequence: PulseSequence, channels: ChannelMap
    ) -> SequenceReport:
        """Compile to instructions, never to samples.

        Order matters: validate the sequence, then check it fits an
        activation config, then quantise. A sequence that cannot be
        played at all should fail before anything is rounded, so the
        error names the real problem.
        """
        sequence.validate()
        constraints = self.pulser_constraints()
        activation = constraints.check(sequence, channels)

        # Every element becomes one instruction. That is the honest
        # measure for this class of device — a 5 ms idle costs exactly as
        # much as a 5 ns pulse.
        intervals = list(expand(sequence))
        quantised = quantise_elements(intervals, constraints, minimum=self.GRANULARITY * 1e-9)
        quantised = Quantised(
            {**quantised.values, "sample_rate": 1e9}, quantised.adjustments
        )

        _BENCH.sequence = sequence
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

    async def pulser_on(self) -> None:
        if self._report is None:
            raise RuntimeError(
                f"{self._name} has no sequence loaded — call upload_sequence first"
            )
        self._running = True
        _BENCH.playing = True

    async def pulser_off(self) -> None:
        # Safe when nothing is playing: this is what an abort calls, and
        # an abort cannot know how far the run got.
        self._running = False
        _BENCH.playing = False


# --- The gated counter ------------------------------------------------------


class MockGatedCounter(GatedCounterMixin, AdapterBase):
    """A simulated gated photon counter with an NV sample behind it.

    The injected physics is settable, so a test can assert that a fit
    recovered what was put in. Real hardware has no such knobs — this is
    the simulated sample, the same convention `MockBasic`'s
    `_SimulatedSample` already follows for scans.
    """

    #: Bin widths a real time tagger's clock can divide down to.
    BIN_WIDTHS = (1e-9, 2e-9, 4e-9, 8e-9, 16e-9, 32e-9, 64e-9)

    def __init__(self, name: str = "mock_gated_counter") -> None:
        super().__init__()
        self._name = name
        self._config: GateConfig | None = None
        self._running = False
        self._started = 0.0
        self._elapsed = 0.0

        # The sample.
        self.experiment = "rabi"
        self.rabi_period = 200e-9
        self.coherence_time = 2e-6
        self.contrast = 0.25
        """Fraction by which ms=+/-1 is darker than ms=0. 0.2-0.3 is what
        a decent single NV gives at room temperature."""
        self.bright_rate = 4e6
        """Photons per second at the start of the readout window."""
        self.dark_fraction = 0.35
        """Steady-state rate as a fraction of the initial rate, once the
        spin has been repolarised by the readout laser."""
        self.readout_decay = 300e-9
        """How fast the readout transient decays. What makes extraction a
        real problem rather than a rectangle."""
        self.gate_delay = 300e-9
        """Between the gate opening and the first photon arriving — cable
        length, AOM rise time and the laser's own delay. It is why the
        record has a leading edge to find at all: without it the pulse
        starts at bin zero and an extraction method could pass by
        returning a constant."""
        self.background_rate = 2e4
        """Dark counts and room light, per second. What the record holds
        outside the laser pulse, and the reason a window that starts too
        early costs contrast rather than merely counts."""
        self.seed = 0

    @property
    def schema(self) -> DeviceSchema:
        def sample(name: str, unit: str = "", description: str = "") -> Parameter:
            return Parameter(
                name, unit=unit, role=ParamRole.SETTING, settable=True,
                readable=True, description=description,
            )

        return DeviceSchema(
            name=self._name,
            kind="counter",
            parameters=(
                Parameter("running", dtype="bool", role=ParamRole.STATUS),
                Parameter("sweeps", dtype="i8", role=ParamRole.STATUS),
                Parameter("gates", dtype="i8", role=ParamRole.STATUS),
                Parameter("bins", dtype="i8", role=ParamRole.STATUS),
                Parameter(
                    "experiment", dtype="str", role=ParamRole.SETTING,
                    settable=True, readable=True,
                    choices=("rabi", "ramsey", "hahn_echo", "t1"),
                    description="Which physics the simulated sample shows",
                ),
                sample("rabi_period", "s", "Injected pi-pulse calibration"),
                sample("coherence_time", "s", "T2* / T2 / T1, per experiment"),
                sample("contrast", "", "ms=+/-1 darkness, 0-1"),
                sample("bright_rate", "Hz", "Photon rate at readout start"),
            ),
            tags=["Mock", "GatedCounter", "TimeTagger", "Photon", "ODMR", "Pulsed"],
            actions=["start_counting", "stop_counting"],
        )

    def counter_constraints(self) -> Constraints:
        return Constraints(
            scalars=(
                ScalarConstraint(BIN_WIDTH, allowed=self.BIN_WIDTHS, unit="s"),
                ScalarConstraint(
                    RECORD_LENGTH, bounds=(1e-9, 1e-3), step=1e-9, unit="s"
                ),
                ScalarConstraint(GATES, bounds=(1, 100_000), enforce_int=True),
            )
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        self._running = False

    def _read_sync(self) -> dict[str, Any]:
        config = self._config
        return {
            "running": self._running,
            "sweeps": self.sweeps,
            "gates": config.gates if config else 0,
            "bins": config.bins if config else 0,
            "experiment": self.experiment,
            "rabi_period": self.rabi_period,
            "coherence_time": self.coherence_time,
            "contrast": self.contrast,
            "bright_rate": self.bright_rate,
        }

    # --- Settables ---------------------------------------------------------

    async def set_experiment(self, value: str) -> None:
        self.experiment = str(value)

    async def set_rabi_period(self, value: float) -> None:
        self.rabi_period = float(value)

    async def set_coherence_time(self, value: float) -> None:
        self.coherence_time = float(value)

    async def set_contrast(self, value: float) -> None:
        self.contrast = float(value)

    async def set_bright_rate(self, value: float) -> None:
        self.bright_rate = float(value)

    # --- The contract ------------------------------------------------------

    async def configure_gates(
        self, bin_width_s: float, record_length_s: float, gates: int
    ) -> GateConfig:
        quantised = self.counter_constraints().quantise(
            {
                BIN_WIDTH: bin_width_s,
                RECORD_LENGTH: record_length_s,
                GATES: gates,
            }
        )
        self._config = GateConfig(
            bin_width_s=float(quantised[BIN_WIDTH]),
            record_length_s=float(quantised[RECORD_LENGTH]),
            gates=int(quantised[GATES]),
            quantised=quantised,
        )
        self._elapsed = 0.0
        return self._config

    async def start_counting(self) -> None:
        if self._config is None:
            raise RuntimeError(
                f"{self._name} has no gates configured — call configure_gates first"
            )
        self._running = True
        self._started = time.monotonic()

    async def stop_counting(self) -> None:
        if self._running:
            self._elapsed += time.monotonic() - self._started
        self._running = False

    @property
    def sweeps(self) -> int:
        """Complete passes over every gate, paced by the sequence's own
        duration — the same "what would real elapsed time have produced"
        rule `mock/hardware_scan.py` uses, rather than an artificial
        per-point delay."""
        sequence = _BENCH.sequence
        if sequence is None or sequence.duration <= 0:
            return 0
        elapsed = self._elapsed + (
            time.monotonic() - self._started if self._running else 0.0
        )
        return int(elapsed / sequence.duration)

    async def counter_status(self) -> dict[str, Any]:
        return {"running": self._running, "sweeps": self.sweeps}

    async def get_trace(self) -> Dataset:
        """The accumulated `(gate, time_bin)` trace, with real axes.

        A `Dataset` rather than a bare array plus an info dict, so the
        axes travel with the numbers and the run lands in HDF5 with
        coordinates nobody had to re-derive.
        """
        if self._config is None:
            raise RuntimeError(f"{self._name} has no gates configured")

        config = self._config
        sweeps = max(self.sweeps, 0)
        counts = self._simulate(config, sweeps)

        return Dataset(
            (
                DataArray(
                    "counts",
                    counts,
                    unit="counts",
                    axes=(
                        Axis("readout", np.arange(config.gates), kind="index"),
                        Axis(
                            "time",
                            np.arange(config.bins) * config.bin_width_s,
                            unit="s", kind="time",
                        ),
                    ),
                ),
            ),
            RunMeta(device=self._name, params={"sweeps": sweeps}),
        )

    # --- The simulated sample ----------------------------------------------

    def _simulate(self, config: GateConfig, sweeps: int) -> np.ndarray:
        """One readout transient per gate, brightness set by the spin.

        The transient is the point. A real NV readout is bright for a few
        hundred nanoseconds and then settles as the laser repolarises the
        spin, so the signal lives in the *leading edge* of the window and
        the tail is a per-shot reference. A flat rectangle would let an
        extraction algorithm pass a test it should fail.

        So is where the transient sits. The record starts when the gate
        opens and the photons arrive `gate_delay` later, with dark counts
        before and after — which is what gives extraction two real edges
        to find instead of a pulse conveniently starting at bin zero.

        And so is *which part of it* the spin state reaches. Only the
        decaying component carries it: the same laser that reads the NV
        out repolarises it, so by the tail of the window every readout is
        equally bright whatever it started as. That is precisely what
        makes the tail usable as a per-shot reference — a simulation that
        scaled the whole window by the spin state would let `mean_norm`
        divide the physics away and return a flat line, which is a bug
        this file exists to not have.
        """
        bins = np.arange(config.bins) * config.bin_width_s
        start = self.gate_delay
        stop = start + self._laser_window(config)
        lit = (bins >= start) & (bins < stop)

        # Time since the laser turned on, so the decay is measured from
        # the pulse rather than from the gate.
        decaying = np.where(
            lit,
            np.exp(
                -np.clip(bins - start, 0.0, None) / max(self.readout_decay, 1e-12)
            ),
            0.0,
        )
        repolarised = np.where(lit, self.dark_fraction, 0.0)

        brightness = np.array(
            [self._brightness(gate, config.gates) for gate in range(config.gates)]
        )
        rate = self.background_rate + self.bright_rate * (
            repolarised
            + (1.0 - self.dark_fraction) * np.outer(brightness, decaying)
        )
        expected = rate * config.bin_width_s * max(sweeps, 0)

        generator = np.random.default_rng(self.seed)
        return generator.poisson(expected).astype(np.int64)

    def _laser_window(self, config: GateConfig) -> float:
        """How long the readout laser is on inside one record.

        From the loaded sequence, because that is where it is written —
        the same `_BENCH` cable that tells this counter what was swept.
        With no sequence loaded the laser fills whatever record is left
        after the delay, which keeps a bare `configure_gates` + `get_trace`
        from returning an empty record.
        """
        sequence = _BENCH.sequence
        window = sequence.readout_window() if sequence is not None else 0.0
        return window or max(config.record_length_s - self.gate_delay, 0.0)

    def _brightness(self, gate: int, gates: int) -> float:
        """Relative fluorescence of readout `gate`, in `[1 - contrast, 1]`.

        The tau this readout belongs to comes from the loaded sequence's
        own sweep — the sequence knows what it swept, which is the whole
        reason `describe()` can state a run's axes up front, and it is
        just as useful here.
        """
        sequence = _BENCH.sequence
        if sequence is None or sequence.sweep is None or not len(sequence.sweep):
            return 1.0

        values = sequence.sweep.values
        if sequence.alternating:
            # Signal and reference alternate, so two readouts share a tau
            # and the odd one is the opposite projection.
            point, arm = divmod(gate, 2)
        else:
            point, arm = gate, 0
        tau = values[min(point, len(values) - 1)]

        population = self._population(tau)
        if arm:
            population = 1.0 - population
        return 1.0 - self.contrast * (1.0 - population)

    def _population(self, tau: float) -> float:
        """ms=0 population after evolving for `tau`, in `[0, 1]`."""
        decay = math.exp(-tau / max(self.coherence_time, 1e-12))
        if self.experiment == "rabi":
            # Starts bright, first minimum at the pi pulse.
            return 0.5 * (1.0 + decay * math.cos(2 * math.pi * tau / self.rabi_period))
        if self.experiment == "t1":
            # Relaxation toward a 50/50 mixture, no oscillation.
            return 0.5 * (1.0 + decay)
        # Ramsey and Hahn echo: coherence decays, no detuning modelled.
        return 0.5 * (1.0 + decay)


adapter_registry.register("mock_pulser", MockPulser)
adapter_registry.register("mock_gated_counter", MockGatedCounter)
