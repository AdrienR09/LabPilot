"""Swabian Instruments Time Tagger — the photon counter for a pulsed rig.

Until this, the only implementation of `GatedCounterMixin` in the repo was
the mock. Two real pulsers could play a sequence on real hardware and
nothing could count what came back, which meant the whole pulsed subsystem
stopped at the bench door. This is the other half.

## `TimeDifferences` *is* the contract

The gated-counter contract wants a 2-D `(gate, time_bin)` array: one
histogram per readout, each sliced into bins. The Time Tagger has exactly
that measurement class, and the mapping needs no cleverness:

    TimeDifferences(tagger,
                    click_channel=<APD>,     # a photon arrived
                    start_channel=<gate>,    # a readout window opened
                    next_channel=<gate>,     # ...and the next one
                    sync_channel=<sync>,     # back to histogram 0
                    binwidth=<ps>, n_bins=<bins>, n_histograms=<gates>)

`start` and `next` are the *same* channel because in a pulsed sequence one
edge does both jobs: it ends the previous readout and begins this one.
`sync_channel` is what makes a long run trustworthy — it pins histogram 0
to the start of the sequence, so a single missed gate shifts one sweep
instead of rotating every subsequent one against the sweep axis. Without
it the device wraps on its own count, and a dropped edge silently smears
the whole measurement.

## Picoseconds, and why `configure_gates` reports back

`binwidth` is an **integer number of picoseconds**. A request of 1.4 ns is
not illegal, it becomes 1400 ps exactly, but a request in units the device
cannot express gets rounded — which is the case `GateConfig.quantised`
exists to report rather than absorb. The record length follows from
`bins * binwidth`, so it quantises too, and the caller must use the
returned values. That is qudi's `FastCounterInterface` rule and it is
right for the same reason here.

## Channels are numbers, and a negative one is a falling edge

The device names its inputs `1..8` (or `1..18`), and `-3` means "channel 3,
falling edge" — the API's own convention, not something invented here. So
the channel settings are plain integers and a rig that gates on a falling
edge writes `-3`.

Attribution: driven through Swabian's own `TimeTagger` Python package,
which ships with their driver installation rather than from PyPI. Imported
inside `_connect_sync`, so this adapter registers, describes itself and
appears in the catalogue on a machine that has never seen one. **Not run
against hardware** — built against the documented API; the contract, the
quantisation and the trace's shape are covered headlessly in
`tests/test_time_tagger.py`.
"""

from __future__ import annotations

import contextlib
from typing import Any

import numpy as np

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta
from labpilot.core.device.constraints import (
    Adjustment,
    Constraints,
    Quantised,
    ScalarConstraint,
)
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.gated_counter_mixin import (
    BIN_WIDTH,
    GATES,
    RECORD_LENGTH,
    GateConfig,
    GatedCounterMixin,
)

__all__ = ["TimeTaggerAdapter"]

#: The hardware timebase: every duration is an integer number of these.
PICOSECOND = 1e-12

#: Beyond this the device is being asked for more histogram memory than it
#: has. Swabian's own limit depends on the model and the installed memory;
#: this is a conservative figure that keeps a mistake (a million gates
#: from a mistyped sweep count) from becoming a driver-level failure.
MAX_CELLS = 200_000_000


class TimeTaggerAdapter(GatedCounterMixin, AdapterBase):
    """A Swabian Time Tagger, counting photons into per-readout histograms.

    Args:
        serial_number: Which unit, when more than one is connected. Empty
            takes the first one found.
        click_channel: The input the detector (APD/SPAD) is wired to.
        gate_channel: The input carrying one edge per readout window —
            the pulser's gate line. Negative counts falling edges.
        sync_channel: Optional input carrying one edge per sequence
            repetition, which pins histogram 0. 0 means none, and then the
            device wraps on its own count — workable, but a dropped gate
            then rotates every later sweep. Wire it if you can.
        trigger_level: Input threshold in volts, applied to the click and
            gate channels.
        dead_time_ps: Detector dead time to enforce in the tagger, in
            picoseconds. 0 leaves the device default.
    """

    def __init__(
        self,
        serial_number: str = "",
        click_channel: int = 1,
        gate_channel: int = 2,
        sync_channel: int = 0,
        trigger_level: float = 0.5,
        dead_time_ps: int = 0,
        name: str = "time_tagger",
    ) -> None:
        super().__init__()
        self._serial = str(serial_number or "")
        self._click = int(click_channel)
        self._gate = int(gate_channel)
        self._sync = int(sync_channel)
        self._level = float(trigger_level)
        self._dead_time = int(dead_time_ps)
        self._name = name

        self._tagger: Any = None
        self._measurement: Any = None
        self._config: GateConfig | None = None
        self._model = ""
        self._channels: tuple[int, ...] = ()

    # --- What it is --------------------------------------------------------

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="counter",
            parameters=(
                Parameter("running", dtype="bool", role=ParamRole.STATUS),
                Parameter("sweeps", dtype="i8", role=ParamRole.STATUS,
                          description="Complete passes over every readout"),
                Parameter("gates", dtype="i8", role=ParamRole.STATUS),
                Parameter("bins", dtype="i8", role=ParamRole.STATUS),
                Parameter("model", dtype="str", role=ParamRole.STATUS),
                Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                Parameter(
                    "click_channel", dtype="i8", settable=True,
                    role=ParamRole.SETTING,
                    description="Detector input; negative counts falling edges",
                ),
                Parameter(
                    "gate_channel", dtype="i8", settable=True,
                    role=ParamRole.SETTING,
                    description="One edge per readout window",
                ),
                Parameter(
                    "sync_channel", dtype="i8", settable=True,
                    role=ParamRole.SETTING,
                    description="One edge per sequence repetition; 0 for none",
                ),
                Parameter(
                    "trigger_level", unit="V", settable=True,
                    role=ParamRole.SETTING, limits=(-2.5, 2.5),
                ),
                Parameter(
                    "dead_time_ps", dtype="i8", unit="ps", settable=True,
                    role=ParamRole.SETTING, limits=(0, None),
                ),
            ),
            actions=["start_counting", "stop_counting", "clear"],
            tags=[
                "Swabian Instruments", "Time Tagger", "GatedCounter",
                "Photon", "TCSPC", "ODMR", "Pulsed",
            ],
        )

    def counter_constraints(self) -> Constraints:
        """What the device will do with a requested configuration.

        Everything is picoseconds underneath, so a bin width snaps to a
        multiple of 1 ps and a record length to a multiple of the bin
        width — the latter is enforced in `configure_gates`, where the bin
        width is finally known.
        """
        return Constraints(
            scalars=(
                ScalarConstraint(
                    BIN_WIDTH, bounds=(PICOSECOND, 1.0), step=PICOSECOND, unit="s"
                ),
                ScalarConstraint(
                    RECORD_LENGTH, bounds=(PICOSECOND, 1.0), step=PICOSECOND, unit="s"
                ),
                ScalarConstraint(GATES, bounds=(1, 1_000_000), enforce_int=True),
            )
        )

    # --- Connection --------------------------------------------------------

    def _import(self) -> Any:
        try:
            import TimeTagger
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise ImportError(
                "Talking to a Time Tagger needs Swabian's own `TimeTagger` "
                "Python package, which comes with their driver installation "
                "(https://www.swabianinstruments.com/time-tagger/) rather than "
                "from PyPI. Configuring one needs neither."
            ) from exc
        return TimeTagger

    def _connect_sync(self) -> None:
        api = self._import()
        self._tagger = (
            api.createTimeTagger(self._serial) if self._serial
            else api.createTimeTagger()
        )
        self._model = str(getattr(self._tagger, "getModel", lambda: "")() or "")
        self._serial = str(getattr(self._tagger, "getSerial", lambda: "")() or "")
        try:
            self._channels = tuple(int(c) for c in self._tagger.getChannelList())
        except Exception:
            self._channels = ()

        self._check_channels()
        for channel in (self._click, self._gate):
            self._tagger.setTriggerLevel(channel, self._level)
        if self._dead_time > 0:
            self._tagger.setDeadtime(self._click, self._dead_time)

    def _check_channels(self) -> None:
        """A wired channel the device does not have, caught here.

        The device reports its own inputs, so this is the one place the
        check can be exact — and a wrong channel number otherwise shows up
        as a measurement that simply counts nothing, which is a much
        worse afternoon.
        """
        if not self._channels:
            return
        available = {abs(c) for c in self._channels}
        wanted = {
            "click_channel": self._click,
            "gate_channel": self._gate,
            **({"sync_channel": self._sync} if self._sync else {}),
        }
        missing = {
            name: value for name, value in wanted.items()
            if abs(value) not in available
        }
        if missing:
            raise ValueError(
                f"{self._model or 'This Time Tagger'} has inputs "
                f"{sorted(available)}; "
                + ", ".join(f"{name}={value}" for name, value in missing.items())
                + " does not exist. A negative number means the falling edge of "
                "that input."
            )

    def _disconnect_sync(self) -> None:
        if self._measurement is not None:
            with contextlib.suppress(Exception):
                self._measurement.stop()
            self._measurement = None
        if self._tagger is not None:
            with contextlib.suppress(Exception):
                self._import().freeTimeTagger(self._tagger)
            self._tagger = None

    def _self_test_sync(self) -> None:
        self._require().getSerial()

    def _require(self) -> Any:
        if self._tagger is None:
            raise RuntimeError(f"{self._name} is not connected")
        return self._tagger

    def _read_sync(self) -> dict[str, Any]:
        config = self._config
        return {
            "running": self._is_running(),
            "sweeps": self._sweeps(),
            "gates": config.gates if config else 0,
            "bins": config.bins if config else 0,
            "model": self._model,
            "serial_number": self._serial,
            "click_channel": self._click,
            "gate_channel": self._gate,
            "sync_channel": self._sync,
            "trigger_level": self._level,
            "dead_time_ps": self._dead_time,
        }

    # --- Settings ----------------------------------------------------------

    async def set_click_channel(self, value: int) -> None:
        self._click = int(value)
        self._reconfigure()

    async def set_gate_channel(self, value: int) -> None:
        self._gate = int(value)
        self._reconfigure()

    async def set_sync_channel(self, value: int) -> None:
        self._sync = int(value)
        self._reconfigure()

    async def set_trigger_level(self, value: float) -> None:
        self._level = float(value)
        if self._tagger is not None:
            for channel in (self._click, self._gate):
                await self._to_thread(self._tagger.setTriggerLevel, channel, self._level)

    async def set_dead_time_ps(self, value: int) -> None:
        self._dead_time = int(value)
        if self._tagger is not None and self._dead_time > 0:
            await self._to_thread(self._tagger.setDeadtime, self._click, self._dead_time)

    def _reconfigure(self) -> None:
        """Rewiring the channels invalidates the measurement built on them.

        Dropping it rather than rebuilding silently: the accumulated
        histogram was counted against the old wiring, and quietly carrying
        it forward would mix two measurements into one array.
        """
        if self._measurement is not None:
            with contextlib.suppress(Exception):
                self._measurement.stop()
            self._measurement = None
        self._config = None

    # --- The gated-counter contract ---------------------------------------

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
        bin_ps = max(round(float(quantised[BIN_WIDTH]) / PICOSECOND), 1)
        bins = max(round(float(quantised[RECORD_LENGTH]) / (bin_ps * PICOSECOND)), 1)
        count = int(quantised[GATES])

        if bins * count > MAX_CELLS:
            raise ValueError(
                f"{bins} bins x {count} readouts is {bins * count} histogram "
                f"cells, past this driver's {MAX_CELLS} ceiling. Widen the bins "
                f"or shorten the record."
            )

        # Derived from the integers the device will really use, so the
        # caller's `bins` and the device's cannot disagree.
        width = bin_ps * PICOSECOND
        record = bins * width

        # And say so. The shared `ScalarConstraint` snaps to the 1 ps grid,
        # but the record length must additionally be a whole number of
        # *bins*, which is not expressible as a step until the bin width is
        # known — so the last adjustment is made here and appended by hand.
        # Leaving it out would put a `record_length_s` in `GateConfig` that
        # its own `quantised` disagrees with, which is precisely the silent
        # difference this type exists to surface.
        adjustments = list(quantised.adjustments)
        if abs(record - record_length_s) >= PICOSECOND / 2:
            adjustments.append(
                Adjustment(
                    RECORD_LENGTH, record_length_s, record,
                    f"a whole number of {width * 1e9:g} ns bins",
                )
            )
        config = GateConfig(
            bin_width_s=width,
            record_length_s=record,
            gates=count,
            quantised=Quantised(
                {**quantised.values, BIN_WIDTH: width, RECORD_LENGTH: record},
                tuple(adjustments),
            ),
        )

        api = self._import()
        tagger = self._require()
        self._reconfigure()
        self._measurement = await self._to_thread(
            api.TimeDifferences,
            tagger,
            self._click,
            self._gate,
            self._gate,
            self._sync if self._sync else 0,
            bin_ps,
            bins,
            count,
        )
        await self._to_thread(self._measurement.stop)
        self._config = config
        return config

    async def start_counting(self) -> None:
        if self._measurement is None:
            raise RuntimeError(
                f"{self._name} has no gates configured — call configure_gates first"
            )
        await self._to_thread(self._measurement.start)

    async def stop_counting(self) -> None:
        """Safe to call when nothing is running: it is what an aborted run
        calls, and an abort cannot know how far the run got."""
        if self._measurement is not None:
            await self._to_thread(self._measurement.stop)

    async def clear(self) -> None:
        """Throw away what has been accumulated and start the histogram
        again from zero."""
        if self._measurement is not None:
            await self._to_thread(self._measurement.clear)

    def _is_running(self) -> bool:
        if self._measurement is None:
            return False
        try:
            return bool(self._measurement.isRunning())
        except Exception:
            return False

    def _sweeps(self) -> int:
        """Complete passes over every readout.

        `TimeDifferences.getCounts()` counts sync events — how many times
        the measurement has been round its histograms — which is exactly
        what a pulsed run counts its progress in.
        """
        if self._measurement is None:
            return 0
        try:
            return int(self._measurement.getCounts())
        except Exception:
            return 0

    async def counter_status(self) -> dict[str, Any]:
        return {"running": self._is_running(), "sweeps": self._sweeps()}

    async def get_trace(self) -> Dataset:
        """Everything counted so far, as `(readout, time_bin)` with axes.

        Safe to call while running — `getData()` takes a consistent
        snapshot, which is what lets a pulsed run stream a converging
        picture instead of waiting for the end.
        """
        if self._measurement is None or self._config is None:
            raise RuntimeError(f"{self._name} has no gates configured")

        config = self._config
        counts = np.asarray(
            await self._to_thread(self._measurement.getData), dtype=float
        ).reshape(config.shape)

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
            RunMeta(device=self._name, params={"sweeps": self._sweeps()}),
        )


adapter_registry.register("swabian_time_tagger", TimeTaggerAdapter)
