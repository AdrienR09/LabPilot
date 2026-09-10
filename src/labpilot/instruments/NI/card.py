"""One adapter for every NI DAQ card: pick the model, wire the terminals.

There used to be two adapters here — `ni_daq` for analog I/O and
`ni_daq_scanner` for hardware-timed scanning — and a card that did both
had to be loaded twice, as two instruments, each opening its own DAQmx
session against the same physical device. That is not how the hardware
works: one 6363 has one set of terminals, one timebase, and one clock that
its analog input, analog output and counters all share. So it is one
instrument here too, and what it *can* do follows from the model you chose
and the terminals you wired, not from which of two classes you picked.

## Three things this knows that the driver cannot tell you offline

NI-DAQmx does not exist for macOS and is not installed on most dev
machines, and a card that is not plugged in answers no questions at all.
Everything up to `connect()` therefore works with no driver present:

- **the model** — `models.toml` says a 6363 has 32 AI, 4 AO, 4 counters
  and 16 PFI lines, so a wiring can be laid out and checked at a desk;
- **the wiring** — `channels.py` turns `x=ao0, apd=ctr0/pfi8` into a
  validated set of channels, with errors that name what the card has;
- **the schema** — which follows from the two above, so the instrument
  browser, the settings tree and `describe()` all work uninstalled.

`connect()` is where the driver becomes necessary, and it is also where
the table stops being trusted: it asks DAQmx what the card really is and
records every disagreement in `warning`, which rides along in each
reading. A stale table entry that silently overrode a real device would be
worse than having no table — and a check nobody calls is not a check, so
this one is not left to a caller to remember.

## What it deliberately is not

**Not a gated counter.** The pulsed subsystem's `GatedCounterMixin` wants
per-readout time bins at nanosecond resolution, and an NI counter bins on
a sample clock it must be given — you can count photons in a window with
one, but not bin a 3 µs readout into 30 ns slices without a 33 MHz clock
to drive it. Qudi does not implement a fast counter on NI hardware either,
for the same reason; its NI counter modules serve CW ODMR and confocal
scanning. A TimeTagger or a FastComTec does that job.

Attribution: talks to the card through pylablib (Alexey Shkarin, GPL v3),
whose `devices/NI/daq.py` is the source-verified API used here. Built
against that source rather than against hardware — **no NI card was
attached to the machine this was written on** — so the I/O paths below
should be checked on a real card before being trusted, while the model,
channel and schema layers are exercised headlessly in
`tests/test_ni_card.py` and by `mock_ni_card`.
"""

from __future__ import annotations

import contextlib
from typing import Any

import numpy as np

from labpilot.core.device.action import Action
from labpilot.core.device.capabilities import HARDWARE_SCAN
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.hardware_scan_mixin import build_scan_waveform
from labpilot.instruments.NI.channels import (
    KINDS,
    Channel,
    parse_channels,
    validate_channels,
)
from labpilot.instruments.NI.models import NICardModel, find_model, load_models

__all__ = ["NICardAdapter", "card_schema", "model_choices"]

DEFAULT_MODEL = "PCIe-6363"


def model_choices() -> tuple[str, ...]:
    """Every card in the table, as the dropdown shows them.

    The product name rather than the bare number — `PCIe-6363` is what is
    printed on the card and what NI-MAX reports, and a list of four-digit
    numbers is a list nobody can read. One entry per model, using its
    first bus, since matching ignores the prefix anyway.
    """
    return tuple(
        sorted(model.product_names()[0] for model in load_models().values())
    )


def card_schema(
    name: str,
    model: NICardModel,
    channels: tuple[Channel, ...],
    *,
    device: str = "",
    tags: tuple[str, ...] = (),
) -> DeviceSchema:
    """The schema a configured card presents — shared with `mock_ni_card`.

    Written once and used by both so the mock cannot drift from the real
    thing: the whole value of choosing `PCIe-6363` on a mock is that the
    configuration you arrive at is the one the card will accept.
    """
    parameters = [
        # Both settable, and both rendered by the ordinary settings tree:
        # `model` has `choices`, which the tree turns into a dropdown, and
        # `channels` is a record table, which `components/channel_table.py`
        # owns. Together they are the whole configuration of an NI card,
        # editable in the settings window of a running instrument rather
        # than only in the form that created it.
        Parameter(
            "model", dtype="str", settable=True, role=ParamRole.SETTING,
            choices=model_choices(),
            description=f"Which card this is — currently {model.label}"
            + (f" ({model.family} Series)" if model.family else ""),
        ),
        Parameter(
            "channels", shape=(None,), settable=True, role=ParamRole.SETTING,
            fields=(
                Parameter("name", dtype="str", settable=True,
                          description="What a workflow calls this channel"),
                Parameter("kind", dtype="str", settable=True, choices=KINDS,
                          description="ai/ao input or output, ci counter, "
                                      "di/do digital, co pulse train"),
                Parameter("terminal", dtype="str", settable=True,
                          description="ai0, ao1, ctr0, port0/line3"),
                Parameter("source", dtype="str", settable=True,
                          description="For a counter: the PFI line it counts"),
            ),
            description="What is wired where. Terminals are checked against "
                        "the chosen model.",
        ),
        Parameter(
            "device", dtype="str", readable=True, settable=False,
            role=ParamRole.STATUS, description="NI-MAX device name",
        ),
        Parameter(
            "warning", dtype="str", readable=True, settable=False,
            role=ParamRole.STATUS,
            description="How the connected card disagrees with the model "
                        "table, if it does. Empty is the normal case.",
        ),
    ]
    for channel in channels:
        if channel.kind == "co":
            continue
        parameters.append(
            Parameter(
                channel.name,
                dtype=channel.dtype,
                unit=channel.unit,
                readable=channel.readable,
                settable=channel.settable,
                limits=channel.limits,
                role=ParamRole.SETTING if channel.settable else ParamRole.VALUE,
                description=f"{channel.kind} on {channel.terminal}"
                + (f" counting {channel.source}" if channel.source else ""),
            )
        )

    actions: list[Action] = []
    pulses = [c for c in channels if c.kind == "co"]
    if pulses:
        actions += [
            Action(
                "pulse_on",
                params=(
                    Parameter("channel", dtype="str", settable=True,
                              choices=tuple(c.name for c in pulses)),
                    Parameter("frequency", unit="Hz", settable=True,
                              limits=(1e-3, None)),
                    Parameter("duty", settable=True, limits=(0.0, 1.0)),
                ),
                description="Start a continuous pulse train on a counter output.",
            ),
            Action(
                "pulse_off",
                params=(
                    Parameter("channel", dtype="str", settable=True,
                              choices=tuple(c.name for c in pulses)),
                ),
                description="Stop a counter output's pulse train.",
            ),
        ]

    capabilities: set[str] = set()
    if model.timed_output and any(c.kind == "ao" for c in channels) and any(
        c.kind in ("ai", "ci") for c in channels
    ):
        # Hardware-timed scanning needs somewhere to drive the position
        # from, something to read back, and outputs that can follow a
        # clock — a USB-6008's cannot, so it never claims this.
        capabilities.add(HARDWARE_SCAN)

    return DeviceSchema(
        name=name,
        kind="generic",
        parameters=tuple(parameters),
        actions=tuple(actions),
        capabilities=frozenset(capabilities),
        tags=[
            "National Instruments", "NI-DAQmx", "DAQ",
            model.number, *( [f"{model.family} Series"] if model.family else [] ),
            *tags,
        ],
    )


class _CardConfig:
    """The driver-free half of an NI card: model, wiring, schema.

    Split out so `mock_ni_card` is the same configuration with a simulated
    back end rather than a second implementation of the same rules.
    """

    def __init__(
        self,
        device: str = "Dev1",
        model: str = DEFAULT_MODEL,
        channels: Any = None,
        voltage_range: tuple[float, float] | None = None,
        rate: float = 1000.0,
        clock_source: str = "",
        name: str = "ni_card",
    ) -> None:
        self._device = str(device or "Dev1").strip("/")
        self._model = find_model(model)
        self._channels = validate_channels(parse_channels(channels), self._model)
        self._range = tuple(voltage_range) if voltage_range else self._model.voltage_range
        self._rate = float(rate)
        self._clock_source = clock_source
        self._name = name
        self._product_name = str(model)

    # --- What was configured ---------------------------------------------

    @property
    def model(self) -> NICardModel:
        return self._model

    @property
    def channels(self) -> tuple[Channel, ...]:
        return self._channels

    def of_kind(self, *kinds: str) -> tuple[Channel, ...]:
        return tuple(c for c in self._channels if c.kind in kinds)

    # --- Reconfiguring, from the settings window --------------------------

    def apply_model(self, product_name: str) -> None:
        """Point this instrument at a different card model.

        The wiring is re-validated against the new model *before* anything
        changes, so choosing the wrong card from the dropdown says which
        terminal does not exist on it rather than leaving an instrument
        that claims terminals it has not got. Either both change or
        neither does.
        """
        model = find_model(product_name)
        channels = validate_channels(self._channels, model)
        self._model = model
        self._channels = channels
        self._product_name = str(product_name)
        self._range = self._model.voltage_range
        self._rewired()

    def apply_channels(self, spec: Any) -> None:
        """Re-wire, from the channel table or a script.

        Validated against the current model first, for the same reason:
        a half-applied wiring is worse than a rejected one.
        """
        self._channels = validate_channels(parse_channels(spec), self._model)
        self._rewired()

    def _rewired(self) -> None:
        """Called after the model or the wiring changed.

        The base does nothing — a configuration object has nothing to
        rebuild. Each adapter overrides it to bring its own state back in
        line, which for the real card means rebuilding its DAQmx tasks.
        """

    def channel_records(self) -> list[dict[str, Any]]:
        """The wiring as the record table the settings window edits."""
        return [
            {
                "name": c.name, "kind": c.kind,
                "terminal": c.terminal, "source": c.source,
            }
            for c in self._channels
        ]

    def channel(self, name: str) -> Channel:
        for channel in self._channels:
            if channel.name == name:
                return channel
        raise KeyError(
            f"{self._name} has no channel {name!r} — it has "
            f"{', '.join(c.name for c in self._channels) or 'none configured'}"
        )

    @property
    def schema(self) -> DeviceSchema:
        return card_schema(
            self._name, self._model, self._channels, device=self._device
        )

    def constraints(self):
        """What this card will do with a requested rate or range."""
        return self._model.constraints()


class NICardAdapter(_CardConfig, AdapterBase):
    """An NI DAQ card, whichever model it is.

    Args:
        device: NI-MAX device name, e.g. `"Dev1"`.
        model: Product name or bare number — `"PCIe-6363"`, `"USB-6363"`
            and `"6363"` all select the same entry.
        channels: The wiring. Either a string
            (`"x=ao0, y=ao1, apd=ctr0/pfi8"`) or a list of records; see
            `channels.py`.
        voltage_range: `(min, max)` volts for every analog channel that
            does not state its own. Defaults to the model's widest input
            range.
        rate: Sample-clock rate in Hz for the shared input task.
        clock_source: What clocks the counters. Empty means the analog
            input clock, `ai/SampleClock`, which is what an NI card
            normally uses and what pylablib expects — a card with no
            analog input at all (a 6602) has no such clock and must name
            an external one.
        name: Instrument name.
    """

    def __init__(
        self,
        device: str = "Dev1",
        model: str = DEFAULT_MODEL,
        channels: Any = None,
        voltage_range: tuple[float, float] | None = None,
        rate: float = 1000.0,
        clock_source: str = "",
        name: str = "ni_card",
    ) -> None:
        AdapterBase.__init__(self)
        _CardConfig.__init__(
            self, device=device, model=model, channels=channels,
            voltage_range=voltage_range, rate=rate, clock_source=clock_source,
            name=name,
        )
        self._daq: Any = None
        self._columns: tuple[str, ...] = ()
        self._running_scan = False
        self._axes: list[str] = []
        self._waveforms: dict[str, np.ndarray] = {}
        self._frame_size = 0
        self._accumulated: list[float | None] = []
        self._filled = 0
        self._detector = ""
        self._live: dict[str, Any] = {}
        self._differences: dict[str, Any] = {}

    # --- Connection --------------------------------------------------------

    def _open(self) -> Any:
        """pylablib's NIDAQ, imported here rather than at module scope.

        The point of a late import is that everything above `connect()`
        works without the driver: the instrument browser lists this card,
        `describe()` returns its schema, and a wiring can be validated on
        a machine where NI-DAQmx cannot even be installed.
        """
        try:
            from pylablib.devices.NI import NIDAQ
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise ImportError(
                "Talking to an NI card needs pylablib and the NI-DAQmx "
                "runtime: `pip install 'pylablib[devio-full]' nidaqmx` plus "
                "NI-DAQmx itself (Windows or Linux; NI does not ship it for "
                "macOS). Configuring one — model, terminals, schema — needs "
                "neither."
            ) from exc
        return NIDAQ(dev_name=self._device, rate=self._rate)

    def _connect_sync(self) -> None:
        self._daq = self._open()
        counters = self.of_kind("ci")

        if counters and not self.of_kind("ai") and not self._clock_source:
            if self._model.ai == 0:
                raise ValueError(
                    f"{self._product_name} has no analog input, so there is no "
                    f"'ai/SampleClock' to count against — give the card a "
                    f"clock_source (a PFI line carrying the gate or clock)"
                )
            # pylablib's own requirement: a counter is clocked from the
            # analog-input task, which must have at least one channel even
            # if nothing reads it. Qudi sets up the same dummy task.
            self._daq.add_voltage_input("_clock", "ai0", rng=self._range)

        for channel in self.of_kind("ai"):
            self._daq.add_voltage_input(
                channel.name, channel.terminal, rng=self._span(channel)
            )
        for channel in counters:
            self._daq.add_counter_input(
                channel.name, channel.terminal, channel.source,
                clk_src=self._clock_source or "ai/SampleClock",
                output_format="rate",
            )
        for channel in self.of_kind("di"):
            self._daq.add_digital_input(channel.name, channel.terminal)
        for channel in self.of_kind("do"):
            self._daq.add_digital_output(channel.name, channel.terminal)
        for channel in self.of_kind("ao"):
            self._daq.add_voltage_output(
                channel.name, channel.terminal, rng=self._span(channel)
            )

        # The read order pylablib returns columns in — it hands back a
        # plain 2-D array, so the names have to be kept alongside it.
        self._columns = tuple(self._daq.get_input_channels(include=("ai", "ci", "di")))

        # Ask the card what it is, now that one is actually open. Doing it
        # here rather than leaving `reconcile()` for someone to call is the
        # difference between a claim and a check: a table entry that
        # disagrees with the hardware is exactly the failure this whole
        # file is arranged to make visible, and a method nobody calls
        # cannot make anything visible.
        self._live = _inventory(self._daq, self._device)
        self._differences = _differences(self._model, self._product_name, self._live)

    def _span(self, channel: Channel) -> tuple[float, float]:
        low, high = channel.limits or (None, None)
        return (
            self._range[0] if low is None else low,
            self._range[1] if high is None else high,
        )

    def _disconnect_sync(self) -> None:
        if self._daq is not None:
            with contextlib.suppress(Exception):
                self._daq.close()
            self._daq = None

    def _self_test_sync(self) -> None:
        self._require()
        self._daq.get_device_info()

    def _require(self) -> Any:
        if self._daq is None:
            raise RuntimeError(f"{self._name} is not connected")
        return self._daq

    # --- Reading and writing ----------------------------------------------

    def _rewired(self) -> None:
        """Rebuild the DAQmx tasks against the new wiring.

        A task is created per channel at connect time, so a card that is
        open has to be closed and reopened — there is no way to add a
        counter to a running task. Doing it here rather than asking the
        user to reconnect is the difference between editing the wiring in
        the settings window and editing a config file.
        """
        if self._daq is None:
            return
        self._disconnect_sync()
        self._connect_sync()

    def _read_sync(self) -> dict[str, Any]:
        reading: dict[str, Any] = {
            "model": self._product_name,
            "channels": self.channel_records(),
            "device": self._device,
            "warning": self.warning,
        }
        inputs = self.of_kind("ai", "ci", "di")
        if not inputs or self._daq is None:
            return reading

        # flush_read=1 because a counter's first sample is the count since
        # the task started, which is not a rate — pylablib's own note.
        samples = np.atleast_2d(
            self._daq.read(n=1, flush_read=1 if self.of_kind("ci") else 0)
        )
        wanted = {c.name for c in inputs}
        for index, column in enumerate(self._columns):
            if column in wanted and index < samples.shape[1]:
                value = samples[0, index]
                channel = self.channel(column)
                reading[column] = bool(value) if channel.kind == "di" else float(value)
        return reading

    async def write(self, values: dict[str, Any]) -> None:
        """Overridden because the settable names are the rig's, not this
        class's: there is no `set_x` method to define when `x` is whatever
        someone called the galvo axis."""
        checked = self.validate_write(values)

        # `model` and `channels` are configuration, not output: they change
        # what this instrument *is*, so they are applied first and the rest
        # of the write then goes to the wiring that results.
        if "model" in checked:
            self.apply_model(str(checked.pop("model")))
        if "channels" in checked:
            self.apply_channels(checked.pop("channels"))
        if not checked:
            return

        daq = self._require()
        analog = {k: float(v) for k, v in checked.items() if self.channel(k).kind == "ao"}
        digital = {k: bool(v) for k, v in checked.items() if self.channel(k).kind == "do"}
        if analog:
            await self._to_thread(
                daq.set_voltage_outputs, list(analog), list(analog.values())
            )
        if digital:
            await self._to_thread(
                daq.set_digital_outputs, list(digital), list(digital.values())
            )

    # --- Counter outputs ---------------------------------------------------

    async def pulse_on(self, channel: str, frequency: float = 1e3, duty: float = 0.5) -> dict[str, Any]:
        """Start a continuous pulse train on a counter output."""
        spec = self.channel(channel)
        if spec.kind != "co":
            raise ValueError(f"{channel!r} is a {spec.kind} channel, not a counter output")
        daq = self._require()
        period = 1.0 / float(frequency)
        on = period * float(duty)

        def _start() -> None:
            if channel not in daq.get_pulse_output_channels():
                daq.add_pulse_output(
                    channel, spec.terminal, spec.source or "", kind="time",
                    on=on, off=period - on, continuous=True,
                )
            else:
                daq.set_pulse_output(channel, on=on, off=period - on, continuous=True)
            daq.start_pulse_output([channel])

        await self._to_thread(_start)
        return {"channel": channel, "frequency": float(frequency), "duty": float(duty)}

    async def pulse_off(self, channel: str) -> dict[str, Any]:
        """Stop a counter output's pulse train."""
        daq = self._require()
        await self._to_thread(daq.stop_pulse_output, [channel])
        return {"channel": channel}

    # --- Hardware-timed scanning -------------------------------------------
    #
    # One shared master clock drives both the position output and the
    # counter, which is the whole reason to scan on an NI card rather than
    # point by point: no per-pixel software round trip. `ai/SampleClock`
    # is pylablib's "main system clock" and the same timebase qudi's own
    # NI modules synchronise to.

    async def configure_scan(
        self, axes: list[str], ranges: dict[str, tuple[float, float]],
        resolution: dict[str, int], frequency: float,
    ) -> None:
        daq = self._require()
        outputs = {c.name for c in self.of_kind("ao")}
        unknown = [axis for axis in axes if axis not in outputs]
        if unknown:
            raise NotImplementedError(
                f"No analog output wired for {unknown} — this card has "
                f"{sorted(outputs) or 'no output channels'}"
            )
        detector = next(iter(self.of_kind("ci", "ai")), None)
        if detector is None:
            raise NotImplementedError(
                f"{self._name} has nothing to read back during a scan — wire a "
                f"counter (e.g. 'apd=ctr0/pfi8') or an analog input"
            )

        self._axes = list(axes)
        self._waveforms, _positions, self._frame_size = build_scan_waveform(
            axes, ranges, resolution
        )
        self._accumulated = [None] * self._frame_size
        self._filled = 0
        rate = float(frequency)
        frame = self._frame_size

        def _configure() -> None:
            daq.setup_clock(rate)
            # continuous=False: play the frame's waveform once and hold,
            # rather than looping it — this is one scan, not a drive signal.
            daq.setup_voltage_output_clock(
                rate=rate, sync_with_ai=True, continuous=False, samps_per_chan=frame,
            )
            daq.set_voltage_outputs(
                list(self._axes), [self._waveforms[axis] for axis in self._axes]
            )

        await self._to_thread(_configure)
        self._detector = detector.name

    async def start_scan(self) -> None:
        daq = self._require()
        await self._to_thread(daq.start, 1, self._frame_size)
        self._running_scan = True

    async def get_scan_data(self) -> dict[str, Any]:
        daq = self._require()
        column = self._columns.index(self._detector) if self._detector in self._columns else 0

        def _drain() -> list[float]:
            available = daq.available_samples()
            if available <= 0:
                return []
            samples = np.atleast_2d(daq.read(n=available))
            return [float(v) for v in samples[:, column]]

        # pylablib's read() resumes from wherever the last one left off, so
        # each call brings only what is new; the running frame is kept here
        # because the caller asks for the whole thing every time.
        for value in await self._to_thread(_drain):
            if self._filled < self._frame_size:
                self._accumulated[self._filled] = value
                self._filled += 1

        done = self._filled >= self._frame_size
        if done:
            self._running_scan = False
        return {
            "data": list(self._accumulated), "completed": self._filled,
            "total": self._frame_size, "done": done,
        }

    async def stop_scan(self) -> None:
        if self._daq is not None:
            await self._to_thread(self._daq.stop)
        self._running_scan = False
        self._filled = 0
        self._accumulated = [None] * self._frame_size

    # --- The table versus the card ----------------------------------------

    async def reconcile(self) -> dict[str, Any]:
        """What the card says about itself, against what the table claims.

        `_connect_sync` already did this and kept the answer — see
        `warning`, which puts it in every reading. This re-asks, for a
        caller that wants the detail rather than the one-line summary.

        Differences are reported, never resolved: the device is right by
        definition, and the point is to say so out loud so a wrong entry in
        `models.toml` gets fixed rather than quietly mis-describing every
        card of that model.
        """
        daq = self._require()
        self._live = await self._to_thread(_inventory, daq, self._device)
        self._differences = _differences(
            self._model, self._product_name, self._live
        )
        return {
            "model": self._model.number,
            "device": self._live,
            "differences": self._differences,
            "warning": self.warning,
        }

    @property
    def warning(self) -> str:
        """One line naming every way the card disagrees with the table, or
        empty. Carried in each reading so it reaches the instrument window
        and the run's saved metadata instead of only a caller who thought
        to ask."""
        if not self._differences:
            return ""
        parts = ", ".join(
            f"{key}: table says {value['table']}, card says {value['device']}"
            for key, value in sorted(self._differences.items())
        )
        return (
            f"{self._product_name} does not match this table entry ({parts}). "
            f"The card is right — run `python scripts/ni_probe.py --check "
            f"{self._device}` and put the block it prints in "
            f"~/.labpilot/config/ni_models.toml."
        )


def _differences(
    model: NICardModel, product_name: str, live: dict[str, Any]
) -> dict[str, Any]:
    """Where a live card and its table entry disagree.

    Only over what the card actually answered: a property it does not
    implement leaves that fact unknown rather than counting as a
    difference. A model that states nothing — the `generic` escape hatch —
    has nothing to disagree with.
    """
    if not model.stated:
        return {}
    expected = {
        "product": product_name,
        "ai": model.ai,
        "ao": model.ao,
        "counters": model.counters,
    }
    return {
        key: {"table": expected[key], "device": live[key]}
        for key in expected
        if live.get(key) is not None and live[key] != expected[key]
    }


def _inventory(daq: Any, device: str) -> dict[str, Any]:
    """A live card's own account of itself, via DAQmx.

    Exactly the four properties qudi reads off `nidaqmx.system.Device`,
    guarded one by one: a property a given card does not implement should
    leave that fact unknown rather than fail the whole comparison.
    """
    info = daq.get_device_info()
    found: dict[str, Any] = {"product": getattr(info, "model", None)}
    try:
        import nidaqmx

        handle = nidaqmx.system.Device(device)
        found["ai"] = len(handle.ai_physical_chans.channel_names)
        found["ao"] = len(handle.ao_physical_chans.channel_names)
        found["counters"] = len(handle.co_physical_chans.channel_names)
        found["terminals"] = [
            t.rsplit("/", 1)[-1].lower() for t in handle.terminals if "pfi" in t.lower()
        ]
    except Exception:
        pass
    return found


adapter_registry.register("ni_card", NICardAdapter)
