"""0D detector rolling-trend viewer (qudi time_series_gui.py style).

Replaces the plain single-value `ViewerComponent` (dimensionality="0D", a
`Viewer0D` showing just the latest scalar) for a 0D detector — a rolling
history of the last `trace_window_s` seconds instead, matching qudi's
time_series module (a trend/chart-recorder view: current value + a
scrolling trace, trace-length/moving-average configurable inline). Fed
from the exact same per-poll dispatch every other component uses
(`InstrumentContext._dispatch_data` -> `on_data`), no separate polling
path or timer of its own.
"""

from __future__ import annotations

import time
from collections import deque

import numpy as np
from components.base import UIComponent
from components.widgets import ProfessionalSpinBox, ValueReadout, dock
from pymodaq_data.data import Axis, DataRaw
from pymodaq_gui.plotting.data_viewers.viewer1D import Viewer1D
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class TimeSeriesComponent(UIComponent):
    component_type = "time_series"
    default_params = {
        "dock_title": "Trend",
        "trace_window_s": 30.0,
        "moving_average_width": 1,
    }

    def build(self) -> None:
        window = self.window
        ctx = self.ctx

        self._start_time = time.monotonic()
        self._times: deque = deque()
        self._values: deque = deque()
        self.trace_window_s = float(self.params["trace_window_s"])
        self.moving_average_width = max(1, int(self.params["moving_average_width"]))

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.value_display = ValueReadout(ctx.units, font_size=26)
        header.addWidget(self.value_display)
        header.addStretch()
        header.addWidget(QLabel("Trace:"))
        self.trace_length_spinbox = ProfessionalSpinBox(1, 3600, 0, "s")
        self.trace_length_spinbox.setValue(self.trace_window_s)
        self.trace_length_spinbox.valueChanged.connect(self._on_trace_length_changed)
        header.addWidget(self.trace_length_spinbox)
        header.addWidget(QLabel("Avg:"))
        self.avg_spinbox = ProfessionalSpinBox(1, 500, 0, "pts")
        self.avg_spinbox.setValue(self.moving_average_width)
        self.avg_spinbox.valueChanged.connect(self._on_avg_changed)
        header.addWidget(self.avg_spinbox)
        layout.addLayout(header)

        plot_content = QWidget()
        self.viewer = Viewer1D(plot_content)
        layout.addWidget(plot_content, 1)

        d = dock(self.params["dock_title"], window)
        d.setWidget(content)
        self.add_dock(d)
        ctx.viewer = self.viewer

    def _on_trace_length_changed(self, value) -> None:
        self.trace_window_s = float(value)
        self._trim()

    def _on_avg_changed(self, value) -> None:
        self.moving_average_width = max(1, int(value))

    def _trim(self) -> None:
        if not self._times:
            return
        newest = self._times[-1]
        while self._times and (newest - self._times[0]) > self.trace_window_s:
            self._times.popleft()
            self._values.popleft()

    def on_data(self, data: dict) -> None:
        ctx = self.ctx
        if ctx.value_key is None or ctx.value_key not in data:
            return
        value = float(data[ctx.value_key])
        t = time.monotonic() - self._start_time
        self._times.append(t)
        self._values.append(value)
        self._trim()

        self.value_display.set_value(f"{value:.4g}")

        y = np.asarray(self._values, dtype=float)
        x = np.asarray(self._times, dtype=float)
        if self.moving_average_width > 1 and len(y) >= self.moving_average_width:
            kernel = np.ones(self.moving_average_width) / self.moving_average_width
            y = np.convolve(y, kernel, mode="valid")
            x = x[-len(y):]

        axis = Axis("time", units="s", data=x, index=0)
        self.viewer.show_data(
            DataRaw(ctx.value_key or "value", data=[y], axes=[axis], units=ctx.units)
        )
