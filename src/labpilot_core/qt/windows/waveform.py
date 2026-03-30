"""WaveformWindow - Real-time waveform display with rolling buffer.

Specialized Qt window for displaying time-series signals with:
- Rolling buffer of N samples per channel
- Multi-channel support with automatic color coding
- Trigger level visualization and adjustment
- Time/division controls and auto-scale
- Real-time updates optimized for high-frequency data
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pyqtgraph as pg
    from PyQt6.QtGui import QAction, QCloseEvent
    from PyQt6.QtWidgets import (
        QDoubleSpinBox,
        QToolBar,
    )

    from labpilot_core.core.events import Event

from labpilot_core.qt.windows._base import LabPilotWindow

__all__ = ["WaveformWindow"]

log = logging.getLogger(__name__)


class WaveformWindow(LabPilotWindow):
    """Real-time waveform display window.

    Features:
    - pyqtgraph PlotWidget with time axis and multiple traces
    - Circular buffer using collections.deque for efficient rolling updates
    - Multi-channel support with legend and automatic coloring
    - Trigger level line (draggable InfiniteLine)
    - Toolbar with time/div selector, auto-scale, freeze
    - Optimized for high-frequency real-time data (>1kHz)

    Example:
        >>> window = WaveformWindow(
        ...     window_id="lockin_xy",
        ...     title="Lock-in X/Y Signals",
        ...     source="lockin.xy_signal",
        ...     n_samples=2000,
        ...     channels=["X", "Y"]
        ... )
    """

    def __init__(
        self,
        window_id: str,
        title: str,
        source: str,
        n_samples: int = 1000,
        channels: list[str] | None = None,
        xlabel: str = "Time (s)",
    ) -> None:
        """Initialize waveform window.

        Args:
            window_id: Unique window identifier.
            title: Window title.
            source: Data source ("device.parameter").
            n_samples: Number of samples in rolling buffer.
            channels: List of channel names (auto-detected if None).
            xlabel: X-axis label.
        """
        # Initialize Qt main window
        from PyQt6.QtWidgets import QMainWindow
        QMainWindow.__init__(self)

        # Initialize LabPilot window
        LabPilotWindow.__init__(self, window_id, [source])

        # Store parameters
        self.source = source
        self.n_samples = n_samples
        self.channels = channels or []
        self.xlabel = xlabel

        # Window setup
        self.setWindowTitle(title)
        self.resize(1000, 600)

        # Data storage - rolling buffers per channel
        self.time_buffer: deque[float] = deque(maxlen=n_samples)
        self.channel_buffers: dict[str, deque[float]] = {}
        self.sample_count = 0
        self.sample_rate = 1.0  # Hz, estimated from data
        self.last_timestamp = 0.0

        # Display parameters
        self.time_span = 10.0  # seconds
        self.trigger_level = 0.0
        self.frozen = False

        # UI components (will be initialized in _setup_ui)
        self.plot_widget: pg.PlotWidget | None = None
        self.plot_items: dict[str, pg.PlotCurveItem] = {}
        self.trigger_line: pg.InfiniteLine | None = None
        self.legend: pg.LegendItem | None = None
        self.toolbar: QToolBar | None = None

        # Controls
        self.time_div_spinbox: QDoubleSpinBox | None = None
        self.trigger_spinbox: QDoubleSpinBox | None = None

        # Actions
        self.autoscale_action: QAction | None = None
        self.freeze_action: QAction | None = None
        self.clear_action: QAction | None = None

        # Initialize UI
        self._setup_ui()
        self._apply_labpilot_style()

        log.info(f"Created waveform window: {window_id} for source: {source}")

    def _setup_ui(self) -> None:
        """Setup Qt UI components."""
        try:
            import pyqtgraph as pg
            from PyQt6.QtWidgets import QVBoxLayout, QWidget

            # Create central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            # Create plot widget
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setLabel('bottom', self.xlabel)
            self.plot_widget.setLabel('left', 'Amplitude')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setMouseEnabled(x=True, y=True)

            # Add legend
            self.legend = pg.LegendItem(offset=(70, 30))
            self.legend.setParentItem(self.plot_widget.graphicsItem())

            # Create trigger level line
            self.trigger_line = pg.InfiniteLine(
                angle=0,  # Horizontal line
                pos=self.trigger_level,
                pen=pg.mkPen(color='#ff4400', width=2, style=2),  # Dashed
                movable=True,
                label='Trigger'
            )
            self.trigger_line.sigPositionChanged.connect(self._on_trigger_moved)
            self.plot_widget.addItem(self.trigger_line)

            layout.addWidget(self.plot_widget)

            # Setup initial channels if provided
            if self.channels:
                self._setup_channels(self.channels)

            # Create toolbar
            self._setup_toolbar()

        except ImportError:
            log.error("pyqtgraph not available - waveform window will not function")
            raise
        except Exception as e:
            log.error(f"Failed to setup waveform window UI: {e}")
            raise

    def _setup_channels(self, channel_names: list[str]) -> None:
        """Setup plot curves for each channel.

        Args:
            channel_names: List of channel names to create.
        """
        try:
            import pyqtgraph as pg

            if self.plot_widget is None:
                return

            # Color cycle for channels
            colors = ['#00ff88', '#ff4400', '#44aaff', '#ffaa00', '#aa44ff', '#ff0088']

            for i, channel in enumerate(channel_names):
                # Create buffer for this channel
                self.channel_buffers[channel] = deque(maxlen=self.n_samples)

                # Create plot curve
                color = colors[i % len(colors)]
                pen = pg.mkPen(color=color, width=2)
                curve = pg.PlotCurveItem(pen=pen, name=channel)
                self.plot_widget.addItem(curve)
                self.plot_items[channel] = curve

                # Add to legend
                if self.legend is not None:
                    self.legend.addItem(curve, channel)

            self.channels = channel_names
            log.debug(f"Setup {len(channel_names)} channels: {channel_names}")

        except Exception as e:
            log.error(f"Failed to setup channels: {e}")

    def _setup_toolbar(self) -> None:
        """Setup window toolbar with controls."""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QAction
            from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QToolBar

            self.toolbar = QToolBar("Waveform Controls")
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

            # Time/Division control
            self.toolbar.addWidget(QLabel("Time/Div (s):"))
            self.time_div_spinbox = QDoubleSpinBox()
            self.time_div_spinbox.setRange(0.001, 60.0)  # 1ms to 60s
            self.time_div_spinbox.setSingleStep(0.1)
            self.time_div_spinbox.setValue(self.time_span / 10.0)  # 10 divisions
            self.time_div_spinbox.valueChanged.connect(self._set_time_div)
            self.toolbar.addWidget(self.time_div_spinbox)

            self.toolbar.addSeparator()

            # Trigger level control
            self.toolbar.addWidget(QLabel("Trigger:"))
            self.trigger_spinbox = QDoubleSpinBox()
            self.trigger_spinbox.setRange(-1000.0, 1000.0)
            self.trigger_spinbox.setSingleStep(0.1)
            self.trigger_spinbox.setValue(self.trigger_level)
            self.trigger_spinbox.valueChanged.connect(self._set_trigger_level)
            self.toolbar.addWidget(self.trigger_spinbox)

            self.toolbar.addSeparator()

            # Auto-scale
            self.autoscale_action = QAction("Auto Scale", self)
            self.autoscale_action.triggered.connect(self._auto_scale)
            self.toolbar.addAction(self.autoscale_action)

            # Freeze
            self.freeze_action = QAction("Freeze", self)
            self.freeze_action.setCheckable(True)
            self.freeze_action.triggered.connect(self._toggle_freeze)
            self.toolbar.addAction(self.freeze_action)

            # Clear
            self.clear_action = QAction("Clear", self)
            self.clear_action.triggered.connect(self._clear_buffers)
            self.toolbar.addAction(self.clear_action)

        except Exception as e:
            log.error(f"Failed to setup toolbar: {e}")

    def _set_time_div(self, time_div: float) -> None:
        """Set time per division.

        Args:
            time_div: Time per division in seconds.
        """
        try:
            self.time_span = time_div * 10.0  # 10 divisions
            self._update_time_axis()
            log.debug(f"Set time/div: {time_div}s (span: {self.time_span}s)")
        except Exception as e:
            log.error(f"Failed to set time division: {e}")

    def _set_trigger_level(self, level: float) -> None:
        """Set trigger level.

        Args:
            level: Trigger level value.
        """
        try:
            self.trigger_level = level
            if self.trigger_line is not None:
                self.trigger_line.setPos(level)
            log.debug(f"Set trigger level: {level}")
        except Exception as e:
            log.error(f"Failed to set trigger level: {e}")

    def _on_trigger_moved(self) -> None:
        """Handle trigger line movement."""
        try:
            if self.trigger_line is not None and self.trigger_spinbox is not None:
                new_level = self.trigger_line.pos().y()
                self.trigger_level = new_level
                self.trigger_spinbox.setValue(new_level)
        except Exception as e:
            log.error(f"Failed to handle trigger move: {e}")

    def _auto_scale(self) -> None:
        """Auto-scale plot to fit data."""
        try:
            if self.plot_widget is not None:
                self.plot_widget.autoRange()
                log.debug("Auto-scaled waveform plot")
        except Exception as e:
            log.error(f"Failed to auto-scale: {e}")

    def _toggle_freeze(self) -> None:
        """Toggle freeze mode (pause updates)."""
        try:
            self.frozen = self.freeze_action.isChecked()
            log.debug(f"Waveform freeze: {self.frozen}")
        except Exception as e:
            log.error(f"Failed to toggle freeze: {e}")

    def _clear_buffers(self) -> None:
        """Clear all data buffers."""
        try:
            self.time_buffer.clear()
            for buffer in self.channel_buffers.values():
                buffer.clear()

            # Clear plot curves
            for curve in self.plot_items.values():
                curve.setData([], [])

            self.sample_count = 0
            log.debug("Cleared waveform buffers")

        except Exception as e:
            log.error(f"Failed to clear buffers: {e}")

    def _update_time_axis(self) -> None:
        """Update plot time axis range."""
        try:
            if (self.plot_widget is not None and
                len(self.time_buffer) > 0):
                # Set X range to show last time_span seconds
                current_time = self.time_buffer[-1]
                self.plot_widget.setXRange(
                    current_time - self.time_span,
                    current_time,
                    padding=0
                )
        except Exception as e:
            log.error(f"Failed to update time axis: {e}")

    def _update_from_event(self, event: Event) -> None:
        """Update waveform from EventBus event (called in Qt thread).

        Args:
            event: Event containing waveform data.
        """
        try:
            if self.frozen:
                return  # Skip updates when frozen

            # Extract data from event
            data = self._parse_source_data(event, self.source)
            if data is None:
                return

            # Get timestamp
            timestamp = getattr(event, 'timestamp', self.sample_count / self.sample_rate)

            # Handle different data formats
            if isinstance(data, dict):
                # Multi-channel data dict
                self._add_multichannel_data(data, timestamp)
            elif isinstance(data, (list, np.ndarray)):
                # Array data (single or multi-channel)
                data_array = np.asarray(data)
                if data_array.ndim == 0:
                    # Single scalar value
                    self._add_single_channel_data('signal', float(data_array), timestamp)
                elif data_array.ndim == 1:
                    # Single channel array or multi-channel sample
                    if len(self.channels) == 0:
                        # Auto-detect channels
                        if len(data_array) == 1:
                            self._setup_channels(['signal'])
                        else:
                            self._setup_channels([f'ch{i}' for i in range(len(data_array))])

                    if len(data_array) == len(self.channels):
                        # Multi-channel sample
                        for i, channel in enumerate(self.channels):
                            self._add_single_channel_data(channel, float(data_array[i]), timestamp)
                    else:
                        # Single channel array - add all points
                        if len(self.channels) == 0:
                            self._setup_channels(['signal'])
                        channel = self.channels[0]
                        for value in data_array:
                            self._add_single_channel_data(channel, float(value), timestamp)
                            timestamp += 1.0 / self.sample_rate
            else:
                # Single scalar value
                if len(self.channels) == 0:
                    self._setup_channels(['signal'])
                self._add_single_channel_data(self.channels[0], float(data), timestamp)

            # Update plots
            self._update_plot_data()

            # Update time axis
            self._update_time_axis()

        except Exception as e:
            log.error(f"Failed to update waveform from event: {e}")

    def _add_multichannel_data(self, data: dict[str, Any], timestamp: float) -> None:
        """Add multi-channel data from dict.

        Args:
            data: Dict with channel names as keys.
            timestamp: Sample timestamp.
        """
        try:
            # Extract channel names from data
            channels = [k for k, v in data.items() if isinstance(v, (int, float))]

            if not channels:
                return

            # Setup channels if not already done
            if len(self.channels) == 0:
                self._setup_channels(channels)

            # Add data for each channel
            for channel in channels:
                if channel in data and channel in self.channel_buffers:
                    self._add_single_channel_data(channel, float(data[channel]), timestamp)

        except Exception as e:
            log.error(f"Failed to add multichannel data: {e}")

    def _add_single_channel_data(self, channel: str, value: float, timestamp: float) -> None:
        """Add single data point to channel.

        Args:
            channel: Channel name.
            value: Data value.
            timestamp: Sample timestamp.
        """
        try:
            # Ensure channel buffer exists
            if channel not in self.channel_buffers:
                if channel not in self.channels:
                    self._setup_channels(self.channels + [channel])

            # Add data to buffers
            if len(self.time_buffer) == 0 or timestamp != self.time_buffer[-1]:
                self.time_buffer.append(timestamp)

            self.channel_buffers[channel].append(value)

            # Estimate sample rate
            if len(self.time_buffer) > 1:
                dt = timestamp - self.last_timestamp
                if dt > 0:
                    self.sample_rate = 1.0 / dt

            self.last_timestamp = timestamp
            self.sample_count += 1

        except Exception as e:
            log.error(f"Failed to add data for channel {channel}: {e}")

    def _update_plot_data(self) -> None:
        """Update plot curves with current buffer data."""
        try:
            if len(self.time_buffer) == 0:
                return

            # Convert time buffer to array
            time_array = np.array(self.time_buffer)

            # Update each channel
            for channel, curve in self.plot_items.items():
                if channel in self.channel_buffers:
                    buffer = self.channel_buffers[channel]
                    if len(buffer) > 0:
                        # Get data arrays of matching length
                        n_points = min(len(time_array), len(buffer))
                        if n_points > 0:
                            time_data = time_array[-n_points:]
                            value_data = np.array(list(buffer)[-n_points:])
                            curve.setData(time_data, value_data)

        except Exception as e:
            log.error(f"Failed to update plot data: {e}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        log.info(f"Closing waveform window: {self.window_id}")

        # Call parent close handler
        LabPilotWindow.closeEvent(self, event)
