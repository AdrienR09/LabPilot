"""National Instruments DAQ (NI-DAQmx) adapter for pylablib.

Unlike most adapters in this codebase, an NI-DAQ card's channel set isn't
fixed by the device model — it's configured per-use (which physical
terminals are wired to what). So its readable/settable *names* are
supplied at construction time (`input_channels`/`output_channels`, a
name -> physical channel mapping, e.g. `{"photodiode": "ai0"}`), and
`write()` is overridden entirely rather than following the generic
`set_<key>` convention (per AdapterBase.write's own docstring, for
exactly this "settings API doesn't fit the convention" case) — there's no
way to define a fixed `set_photodiode` method when "photodiode" is a
user-chosen name, not a fixed one this class could define at class-body
time.

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices.NI import NIDAQ
except ImportError:
    NIDAQ = None

if NIDAQ is not None:
    from instruments._base import AdapterBase, adapter_registry
    from core.device.schema import DeviceSchema

    class NIDAQAdapter(AdapterBase):
        """NI-DAQmx analog I/O adapter.

        Args:
            dev_name: NI-MAX device name (e.g. "Dev1").
            input_channels: {generic_name: physical_channel} for analog
                inputs to configure, e.g. {"photodiode": "ai0"}.
            output_channels: {generic_name: physical_channel} for analog
                outputs to configure, e.g. {"control": "ao0"}.
            voltage_range: (min, max) volts, applied to every channel.
            name: Device name.
        """

        def __init__(
            self,
            dev_name: str = "Dev1",
            input_channels: dict[str, str] | None = None,
            output_channels: dict[str, str] | None = None,
            voltage_range: tuple[float, float] = (-10.0, 10.0),
            name: str = "nidaq",
        ) -> None:
            super().__init__()
            self._dev_name = dev_name
            self._input_channels = input_channels or {}
            self._output_channels = output_channels or {}
            self._voltage_range = voltage_range
            self._name = name
            self._daq: NIDAQ | None = None

        @property
        def schema(self) -> DeviceSchema:
            readable = {chname: "float64" for chname in self._input_channels}
            settable = {chname: "float64" for chname in self._output_channels}
            units = {chname: "V" for chname in {**self._input_channels, **self._output_channels}}
            limits = {chname: self._voltage_range for chname in {**self._input_channels, **self._output_channels}}
            return DeviceSchema(
                name=self._name,
                kind="generic",
                readable=readable,
                settable=settable,
                units=units,
                limits=limits,
                tags=["National Instruments", "NI-DAQmx", "DAQ"],
            )

        def _connect_sync(self) -> None:
            self._daq = NIDAQ(dev_name=self._dev_name)
            for chname, channel in self._input_channels.items():
                self._daq.add_voltage_input(chname, channel, rng=self._voltage_range)
            for chname, channel in self._output_channels.items():
                self._daq.add_voltage_output(chname, channel, rng=self._voltage_range)

        def _disconnect_sync(self) -> None:
            if self._daq is not None:
                try:
                    self._daq.close()
                except Exception:
                    pass
                self._daq = None

        def _read_sync(self) -> dict[str, Any]:
            if self._daq is None:
                raise RuntimeError("Not connected")
            if not self._input_channels:
                return {}
            table = self._daq.read(n=1)
            return {chname: float(table[chname][0]) for chname in self._input_channels}

        async def write(self, values: dict[str, Any]) -> None:
            """Overridden entirely — see this module's docstring for why
            the generic set_<key> dispatch doesn't fit here."""
            if self._daq is None:
                raise RuntimeError("Not connected")
            unknown = [k for k in values if k not in self._output_channels]
            if unknown:
                raise NotImplementedError(
                    f"{type(self).__name__} has no output channel(s) named {unknown} "
                    f"— configured output_channels: {list(self._output_channels)}"
                )
            names = list(values.keys())
            vals = [float(values[n]) for n in names]
            await self._to_thread(self._daq.set_voltage_outputs, names, vals)

        def _self_test_sync(self) -> None:
            if self._daq is None:
                raise RuntimeError("Not connected")
            _ = self._daq.get_full_info()

    adapter_registry.register("ni_daq", NIDAQAdapter)

    from instruments.hardware_scan_mixin import HardwareScanMixin, build_scan_waveform

    class NIDAQScannerAdapter(HardwareScanMixin, AdapterBase):
        """Real NI-DAQmx hardware-timed scanner — see
        instruments/hardware_scan_mixin.py for the contract, and
        instruments/mock/hardware_scan.py's MockNIScanner for the mock
        equivalent used to develop/test this against (no NI card is
        attached in this development environment — this class is built
        directly against pylablib's real, source-verified API
        (pylablib/devices/NI/daq.py), but has NOT been exercised against
        physical hardware; verify on real hardware before trusting it).

        One shared master clock (`setup_clock` — pylablib's own "analog
        input clock, which is the main system clock") drives both the
        position output and the detector counter input, the same
        synchronization Qudi's own NI hardware module relies on
        (`ai/SampleClock` as the shared timebase) — no per-pixel software
        round-trip.

        Position units here are raw output volts (whatever `voltage_range`
        allows), not a calibrated physical position — a real scanner's
        volts-to-position calibration (piezo/galvo gain, mm/V or similar)
        is a per-device constant this adapter deliberately doesn't invent;
        pass already-in-volts ranges via the workflow's SCAN_RANGES, or
        add a calibration layer on top of this class once real hardware
        parameters are known.
        """

        def __init__(
            self,
            dev_name: str = "Dev1",
            ao_channels: dict[str, str] | None = None,
            counter: str = "ctr0",
            counter_terminal: str = "PFI0",
            voltage_range: tuple[float, float] = (-10.0, 10.0),
            name: str = "ni_daq_scanner",
        ) -> None:
            """
            Args:
                dev_name: NI-MAX device name (e.g. "Dev1").
                ao_channels: {axis_name: physical_channel} for the scan
                    axes' position outputs, e.g. {"x": "ao0", "y": "ao1"}.
                counter: counter device to use for the detector input
                    (e.g. a photon counter), e.g. "ctr0".
                counter_terminal: PFI line the counter's input signal is
                    wired to, e.g. "PFI0".
                voltage_range: (min, max) volts, applied to every AO channel.
            """
            super().__init__()
            self._dev_name = dev_name
            self._ao_channels = ao_channels or {}
            self._counter = counter
            self._counter_terminal = counter_terminal
            self._voltage_range = voltage_range
            self._name = name
            self._daq: NIDAQ | None = None
            self._axes: list[str] = []
            self._flat_waveforms: dict[str, Any] = {}
            self._frame_size = 0
            self._running = False

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="generic",
                readable={"status": "str"},
                settable={},
                tags=["National Instruments", "NI-DAQmx", "DAQ", "HardwareScan", "Scanner"],
            )

        def _connect_sync(self) -> None:
            self._daq = NIDAQ(dev_name=self._dev_name)
            for axis, channel in self._ao_channels.items():
                self._daq.add_voltage_output(axis, channel, rng=self._voltage_range)

        def _disconnect_sync(self) -> None:
            if self._daq is not None:
                try:
                    self._daq.close()
                except Exception:
                    pass
                self._daq = None

        def _read_sync(self) -> dict[str, Any]:
            return {"status": "scanning" if self._running else "idle"}

        async def configure_scan(
            self, axes: list[str], ranges: dict[str, tuple[float, float]],
            resolution: dict[str, int], frequency: float,
        ) -> None:
            if self._daq is None:
                raise RuntimeError("Not connected")
            unknown = [a for a in axes if a not in self._ao_channels]
            if unknown:
                raise NotImplementedError(
                    f"No AO channel configured for axis/axes {unknown} — configured "
                    f"ao_channels: {list(self._ao_channels)}"
                )
            self._axes = list(axes)
            self._flat_waveforms, _axis_positions, self._frame_size = build_scan_waveform(axes, ranges, resolution)
            frequency = float(frequency)
            frame_size = self._frame_size

            def _configure_sync() -> None:
                self._daq.setup_clock(frequency)
                self._daq.add_counter_input(
                    "signal", self._counter, self._counter_terminal,
                    clk_src="ai/SampleClock", output_format="rate",
                )
                # continuous=False: output the frame's waveform exactly
                # once and latch, not a repeating/looping signal — this is
                # a single scan frame, not a periodic drive.
                self._daq.setup_voltage_output_clock(
                    rate=frequency, sync_with_ai=True, continuous=False, samps_per_chan=frame_size,
                )
                names = list(self._axes)
                values = [self._flat_waveforms[axis] for axis in names]
                self._daq.set_voltage_outputs(names, values)

            await self._to_thread(_configure_sync)

        async def start_scan(self) -> None:
            if self._daq is None:
                raise RuntimeError("Not connected")
            await self._to_thread(self._daq.start, finite=self._frame_size)
            self._running = True

        async def get_scan_data(self) -> dict[str, Any]:
            if self._daq is None:
                raise RuntimeError("Not connected")

            def _read_sync() -> dict[str, Any]:
                available = self._daq.available_samples()
                if available <= 0:
                    return {"values": []}
                table = self._daq.read(n=available, include=("ci",))
                return {"values": [float(v) for v in table["signal"]]}

            chunk = await self._to_thread(_read_sync)
            values = chunk["values"]
            # pylablib's own `read()` accumulates from wherever the last
            # read left off — see daq.py's ci_counters bookkeeping — so
            # each call here returns only the newly-available samples,
            # not the whole frame again; the caller (HardwareTimedScanCapability)
            # is responsible for tracking the growing frame itself if it
            # needs the full history (mirrored below for a self-contained
            # get_scan_data() matching MockNIScanner's own always-return-
            # the-whole-frame contract).
            if not hasattr(self, "_accumulated"):
                self._accumulated: list[float | None] = [None] * self._frame_size
                self._filled = 0
            for v in values:
                if self._filled < self._frame_size:
                    self._accumulated[self._filled] = v
                    self._filled += 1
            done = self._filled >= self._frame_size
            if done:
                self._running = False
            return {
                "data": list(self._accumulated), "completed": self._filled,
                "total": self._frame_size, "done": done,
            }

        async def stop_scan(self) -> None:
            if self._daq is not None:
                await self._to_thread(self._daq.stop)
            self._running = False
            if hasattr(self, "_accumulated"):
                del self._accumulated
                del self._filled

    adapter_registry.register("ni_daq_scanner", NIDAQScannerAdapter)
