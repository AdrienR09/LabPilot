"""A simulated NI DAQ card — the same model table, no driver.

`mock_ni_scanner` before it simulated a *scanner*: it had axes, it had a
detector, and nothing about it was an NI card. This is the card, chosen by
model number like the real one and configured with the same terminal
strings, so a rig can be wired up and a workflow written against
`PCIe-6363` on a laptop and then bound to the real card without editing
anything but the adapter key.

Its physics come from `MockBasic`'s `_SimulatedSample`, the shared
ground-truth peak every other mock here reads: the analog outputs move the
sample, the counter and analog inputs read a signal that genuinely depends
on where the outputs put it. So an optimizer run against this converges on
a real maximum rather than on noise.

The counter reports counts per second with Poisson noise, which is what
makes it a photon counter rather than a smooth curve — the difference
matters to anything that averages or fits.
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.hardware_scan_mixin import build_scan_waveform
from labpilot.instruments.MockBasic.simple import _SimulatedSample
from labpilot.instruments.NI.card import DEFAULT_MODEL, _CardConfig

__all__ = ["MockNICard"]

_PEAK_WIDTH = 1.5
_BRIGHT = 2.0e5
"""Counts per second at the peak — a plausible NV/bead count rate, so a
1 ms dwell gives ~200 counts and the noise looks like real photon noise."""
_DARK = 2.0e3


class MockNICard(_CardConfig, AdapterBase):
    """A simulated NI card. Same arguments as `NICardAdapter`, plus
    `sample`, which names the shared simulated specimen."""

    def __init__(
        self,
        device: str = "Dev1",
        model: str = DEFAULT_MODEL,
        channels: Any = "x=ao0, y=ao1, apd=ctr0/pfi8",
        voltage_range: tuple[float, float] | None = None,
        rate: float = 1000.0,
        clock_source: str = "",
        name: str = "mock_ni_card",
        sample: str = "default",
    ) -> None:
        AdapterBase.__init__(self)
        _CardConfig.__init__(
            self, device=device, model=model, channels=channels,
            voltage_range=voltage_range, rate=rate, clock_source=clock_source,
            name=name,
        )
        self._sample_name = sample
        self._outputs: dict[str, float] = {c.name: 0.0 for c in self.of_kind("ao")}
        self._digital: dict[str, bool] = {c.name: False for c in self.of_kind("do")}
        self._axes: list[str] = []
        self._waveforms: dict[str, np.ndarray] = {}
        self._frame_size = 0
        self._data: list[float | None] = []
        self._filled = 0
        self._started = 0.0
        self._frequency = 1.0
        self._running = False

    @property
    def schema(self):
        """The shared schema, plus a Mock tag."""
        from labpilot.instruments.NI.card import card_schema

        return card_schema(
            self._name, self.model, self.channels,
            device=self._device, tags=("Mock",),
        )

    # --- Connection --------------------------------------------------------

    def _connect_sync(self) -> None:
        self._push_position()

    def _disconnect_sync(self) -> None:
        self._running = False

    def _self_test_sync(self) -> None:
        pass

    # --- Simulated physics -------------------------------------------------

    def _push_position(self) -> None:
        sample = _SimulatedSample.get(self._sample_name, tuple(self._outputs))
        sample.update_position(dict(self._outputs))

    def _brightness(self, at: dict[str, float] | None = None) -> float:
        """0..1 — how close the outputs are to the specimen's peak."""
        sample = _SimulatedSample.get(self._sample_name, tuple(self._outputs))
        if at is None:
            distance_sq = sample.distance_sq(tuple(self._outputs)) if self._outputs else 0.0
        else:
            distance_sq = sum(
                (value - sample.peak.get(axis, 0.0)) ** 2 for axis, value in at.items()
            )
        return math.exp(-distance_sq / (2 * _PEAK_WIDTH**2))

    def _counts(self, at: dict[str, float] | None = None, dwell: float = 1e-3) -> float:
        rate = _DARK + _BRIGHT * self._brightness(at)
        counts = np.random.poisson(max(rate * dwell, 0.0))
        return float(counts / dwell)

    def _rewired(self) -> None:
        """Bring the simulated outputs back in line with the new wiring.

        A channel that is gone stops existing; one that is new starts at
        zero. Keeping a stale entry would let `read()` report a voltage
        for a terminal nothing is wired to.
        """
        self._outputs = {
            c.name: self._outputs.get(c.name, 0.0) for c in self.of_kind("ao")
        }
        self._digital = {
            c.name: self._digital.get(c.name, False) for c in self.of_kind("do")
        }
        self._push_position()

    def _read_sync(self) -> dict[str, Any]:
        reading: dict[str, Any] = {
            "model": self._product_name,
            "channels": self.channel_records(),
            "device": self._device,
        }
        brightness = self._brightness()
        for channel in self.of_kind("ai"):
            reading[channel.name] = float(
                brightness * 5.0 + np.random.normal(0.0, 0.01)
            )
        for channel in self.of_kind("ci"):
            reading[channel.name] = self._counts(dwell=1.0 / self._rate)
        for channel in self.of_kind("di"):
            reading[channel.name] = False
        return reading

    async def write(self, values: dict[str, Any]) -> None:
        checked = self.validate_write(values)
        # Configuration first — see NICardAdapter.write.
        if "model" in checked:
            self.apply_model(str(checked.pop("model")))
        if "channels" in checked:
            self.apply_channels(checked.pop("channels"))

        for key, value in checked.items():
            channel = self.channel(key)
            if channel.kind == "ao":
                self._outputs[key] = float(value)
            elif channel.kind == "do":
                self._digital[key] = bool(value)
        self._push_position()

    async def pulse_on(self, channel: str, frequency: float = 1e3, duty: float = 0.5) -> dict[str, Any]:
        self.channel(channel)
        return {"channel": channel, "frequency": float(frequency), "duty": float(duty)}

    async def pulse_off(self, channel: str) -> dict[str, Any]:
        self.channel(channel)
        return {"channel": channel}

    # --- Hardware-timed scanning -------------------------------------------
    #
    # Paced by real elapsed time against the requested clock rate, exactly
    # as `mock_ni_scanner` did: a frame takes samples/rate seconds and
    # nothing else, which is the only timing property a hardware-timed
    # scan actually guarantees.

    async def configure_scan(
        self, axes: list[str], ranges: dict[str, tuple[float, float]],
        resolution: dict[str, int], frequency: float,
    ) -> None:
        outputs = {c.name for c in self.of_kind("ao")}
        unknown = [axis for axis in axes if axis not in outputs]
        if unknown:
            raise NotImplementedError(
                f"No analog output wired for {unknown} — this card has "
                f"{sorted(outputs) or 'no output channels'}"
            )
        self._axes = list(axes)
        self._waveforms, _positions, self._frame_size = build_scan_waveform(
            axes, ranges, resolution
        )
        self._frequency = max(float(frequency), 1e-9)
        self._data = [None] * self._frame_size
        self._filled = 0

    async def start_scan(self) -> None:
        self._started = time.monotonic()
        self._running = True

    async def get_scan_data(self) -> dict[str, Any]:
        if self._running:
            elapsed = time.monotonic() - self._started
            due = min(int(elapsed * self._frequency), self._frame_size)
            dwell = 1.0 / self._frequency
            while self._filled < due:
                at = {
                    axis: float(self._waveforms[axis][self._filled])
                    for axis in self._axes
                }
                self._data[self._filled] = self._counts(at, dwell)
                self._filled += 1
            if self._filled >= self._frame_size:
                self._running = False
                # Leave the outputs where the scan left them, like a real
                # card whose AO latches its last sample.
                self._outputs.update(
                    {axis: float(self._waveforms[axis][-1]) for axis in self._axes}
                )
                self._push_position()

        return {
            "data": list(self._data), "completed": self._filled,
            "total": self._frame_size, "done": self._filled >= self._frame_size,
        }

    async def stop_scan(self) -> None:
        self._running = False

    async def reconcile(self) -> dict[str, Any]:
        """A mock agrees with the table by construction — it *is* the
        table — so this reports no differences rather than pretending to
        have asked a driver."""
        return {
            "model": self.model.number,
            "device": {
                "product": self._product_name, "ai": self.model.ai,
                "ao": self.model.ao, "counters": self.model.counters,
            },
            "differences": {},
        }


adapter_registry.register("mock_ni_card", MockNICard)
