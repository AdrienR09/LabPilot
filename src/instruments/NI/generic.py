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
