"""CompositeWindow - Multi-widget layouts for complex control panels.

Handles DSL specifications with multiple widgets arranged in layouts.
Uses pyqtgraph GraphicsLayoutWidget for flexible multi-plot arrangements
and standard Qt layouts for control widgets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtWidgets import (
        QWidget,
    )

    from labpilot_core.core.events import Event

from labpilot_core.qt.windows._base import LabPilotWindow

__all__ = ["CompositeWindow"]

log = logging.getLogger(__name__)


class CompositeWindow(LabPilotWindow):
    """Composite window with multiple widgets.

    Supports various layout types:
    - Vertical: Widgets stacked vertically
    - Horizontal: Widgets arranged horizontally
    - Grid: Widgets in grid layout (auto-sizing)
    - Tabs: Widgets in separate tabs

    Automatically converts DSL widget specs to Qt widgets and handles
    mixed content (plots, controls, displays).

    Example DSL that creates composite window:
        >>> w = window("Control Panel", layout="vertical")
        >>> w.add(spectrum_plot(source="spec.data"))
        >>> w.add(row(
        ...     slider("Power", "laser", "power", 0, 100),
        ...     button("Start", "trigger", "laser")
        ... ))
        >>> show(w)
    """

    def __init__(
        self,
        window_id: str,
        title: str,
        layout: str,
        widgets: list[dict[str, Any]],
    ) -> None:
        """Initialize composite window.

        Args:
            window_id: Unique window identifier.
            title: Window title.
            layout: Layout type ("vertical", "horizontal", "grid").
            widgets: List of widget specifications from DSL.
        """
        # Extract all sources from widget specs for EventBus subscription
        sources = self._extract_sources(widgets)

        # Initialize Qt main window
        from PyQt6.QtWidgets import QMainWindow
        QMainWindow.__init__(self)

        # Initialize LabPilot window
        LabPilotWindow.__init__(self, window_id, sources)

        # Store parameters
        self.layout_type = layout
        self.widget_specs = widgets

        # Window setup
        self.setWindowTitle(title)
        self.resize(1000, 800)

        # Widget storage
        self.qt_widgets: dict[str, QWidget] = {}
        self.widget_sources: dict[str, str] = {}  # widget_id -> source

        # Initialize UI
        self._setup_ui()
        self._apply_labpilot_style()

        log.info(f"Created composite window: {window_id} with {len(widgets)} widgets")

    def _extract_sources(self, widgets: list[dict[str, Any]]) -> list[str]:
        """Extract all data sources from widget specifications.

        Args:
            widgets: List of widget specs.

        Returns:
            List of unique sources.
        """
        sources = set()

        def extract_from_spec(spec: dict[str, Any]) -> None:
            # Check for direct sources
            if 'source' in spec:
                sources.add(spec['source'])
            if 'x_source' in spec:
                sources.add(spec['x_source'])
            if 'y_source' in spec:
                sources.add(spec['y_source'])

            # Recursively check nested widgets
            if 'widgets' in spec and isinstance(spec['widgets'], list):
                for widget in spec['widgets']:
                    extract_from_spec(widget)
            if 'tabs' in spec and isinstance(spec['tabs'], dict):
                for tab_widget in spec['tabs'].values():
                    extract_from_spec(tab_widget)

        for widget in widgets:
            extract_from_spec(widget)

        return list(sources)

    def _setup_ui(self) -> None:
        """Setup Qt UI from widget specifications."""
        try:
            from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

            # Create central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)

            # Create main layout
            if self.layout_type == "vertical":
                main_layout = QVBoxLayout(central_widget)
            elif self.layout_type == "horizontal":
                main_layout = QHBoxLayout(central_widget)
            elif self.layout_type == "grid":
                main_layout = QGridLayout(central_widget)
            else:
                raise ValueError(f"Unsupported layout type: {self.layout_type}")

            # Create widgets from specifications
            for i, widget_spec in enumerate(self.widget_specs):
                try:
                    widget = self._create_widget_from_spec(widget_spec)
                    if widget is not None:
                        if self.layout_type == "grid":
                            # Auto-arrange in grid (2 columns)
                            row = i // 2
                            col = i % 2
                            main_layout.addWidget(widget, row, col)
                        else:
                            main_layout.addWidget(widget)

                except Exception as e:
                    log.error(f"Failed to create widget {i}: {e}")

        except Exception as e:
            log.error(f"Failed to setup composite UI: {e}")
            raise

    def _create_widget_from_spec(self, spec: dict[str, Any]) -> QWidget | None:
        """Create Qt widget from DSL specification.

        Args:
            spec: Widget specification from DSL.

        Returns:
            Qt widget instance or None if creation failed.
        """
        try:
            widget_type = spec.get('type')

            if widget_type == 'spectrum_plot':
                return self._create_embedded_spectrum_plot(spec)
            elif widget_type == 'image_view':
                return self._create_embedded_image_view(spec)
            elif widget_type == 'waveform_plot':
                return self._create_embedded_waveform_plot(spec)
            elif widget_type == 'scatter_plot':
                return self._create_scatter_plot(spec)
            elif widget_type == 'slider':
                return self._create_slider(spec)
            elif widget_type == 'button':
                return self._create_button(spec)
            elif widget_type == 'toggle':
                return self._create_toggle(spec)
            elif widget_type == 'dropdown':
                return self._create_dropdown(spec)
            elif widget_type == 'value_display':
                return self._create_value_display(spec)
            elif widget_type == 'text_display':
                return self._create_text_display(spec)
            elif widget_type == 'row':
                return self._create_row_layout(spec)
            elif widget_type == 'column':
                return self._create_column_layout(spec)
            elif widget_type == 'tabs':
                return self._create_tabs(spec)
            else:
                log.warning(f"Unknown widget type: {widget_type}")
                return None

        except Exception as e:
            log.error(f"Failed to create widget from spec: {e}")
            return None

    def _create_embedded_spectrum_plot(self, spec: dict[str, Any]) -> QWidget | None:
        """Create embedded spectrum plot widget."""
        try:
            import pyqtgraph as pg

            # Create plot widget
            plot_widget = pg.PlotWidget()
            plot_widget.setLabel('bottom', spec.get('xlabel', 'Wavelength (nm)'))
            plot_widget.setLabel('left', spec.get('ylabel', 'Intensity (counts)'))
            plot_widget.showGrid(x=True, y=True, alpha=0.3)

            # Store reference for updates
            widget_id = f"plot_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = plot_widget

            if 'source' in spec:
                self.widget_sources[widget_id] = spec['source']

            return plot_widget

        except Exception as e:
            log.error(f"Failed to create spectrum plot: {e}")
            return None

    def _create_embedded_image_view(self, spec: dict[str, Any]) -> QWidget | None:
        """Create embedded image view widget."""
        try:
            import pyqtgraph as pg

            # Create image view
            image_view = pg.ImageView()

            # Hide unnecessary controls for embedded view
            if not spec.get('show_histogram', True):
                image_view.ui.histogram.hide()

            # Store reference
            widget_id = f"image_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = image_view

            if 'source' in spec:
                self.widget_sources[widget_id] = spec['source']

            return image_view

        except Exception as e:
            log.error(f"Failed to create image view: {e}")
            return None

    def _create_embedded_waveform_plot(self, spec: dict[str, Any]) -> QWidget | None:
        """Create embedded waveform plot widget."""
        try:
            import pyqtgraph as pg

            # Create plot widget
            plot_widget = pg.PlotWidget()
            plot_widget.setLabel('bottom', spec.get('xlabel', 'Time (s)'))
            plot_widget.setLabel('left', 'Amplitude')
            plot_widget.showGrid(x=True, y=True, alpha=0.3)

            # Store reference
            widget_id = f"waveform_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = plot_widget

            if 'source' in spec:
                self.widget_sources[widget_id] = spec['source']

            return plot_widget

        except Exception as e:
            log.error(f"Failed to create waveform plot: {e}")
            return None

    def _create_scatter_plot(self, spec: dict[str, Any]) -> QWidget | None:
        """Create scatter plot widget."""
        try:
            import pyqtgraph as pg

            plot_widget = pg.PlotWidget()
            plot_widget.setLabel('bottom', spec.get('xlabel', 'X'))
            plot_widget.setLabel('left', spec.get('ylabel', 'Y'))
            plot_widget.showGrid(x=True, y=True, alpha=0.3)

            # Store reference
            widget_id = f"scatter_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = plot_widget

            # Store both sources for scatter plot
            if 'x_source' in spec and 'y_source' in spec:
                self.widget_sources[widget_id] = f"{spec['x_source']},{spec['y_source']}"

            return plot_widget

        except Exception as e:
            log.error(f"Failed to create scatter plot: {e}")
            return None

    def _create_slider(self, spec: dict[str, Any]) -> QWidget | None:
        """Create slider control widget."""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QLabel, QSlider, QVBoxLayout, QWidget

            # Create container
            container = QWidget()
            layout = QVBoxLayout(container)

            # Create label
            label = QLabel(spec.get('label', 'Slider'))
            layout.addWidget(label)

            # Create slider
            slider = QSlider(Qt.Orientation.Horizontal)
            min_val = spec.get('min', 0)
            max_val = spec.get('max', 100)
            step = spec.get('step', 1)

            # Convert to integer range for Qt slider
            slider.setMinimum(int(min_val * 100))
            slider.setMaximum(int(max_val * 100))
            slider.setSingleStep(int(step * 100))

            layout.addWidget(slider)

            # Store reference
            widget_id = f"slider_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = container

            return container

        except Exception as e:
            log.error(f"Failed to create slider: {e}")
            return None

    def _create_button(self, spec: dict[str, Any]) -> QWidget | None:
        """Create button widget."""
        try:
            from PyQt6.QtWidgets import QPushButton

            button = QPushButton(spec.get('label', 'Button'))

            # Connect button action (TODO: implement device actions)
            action = spec.get('action', 'trigger')
            device = spec.get('device')

            def on_click():
                log.info(f"Button clicked: {action} on {device}")
                # TODO: Implement actual device actions

            button.clicked.connect(on_click)

            # Store reference
            widget_id = f"button_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = button

            return button

        except Exception as e:
            log.error(f"Failed to create button: {e}")
            return None

    def _create_toggle(self, spec: dict[str, Any]) -> QWidget | None:
        """Create toggle checkbox widget."""
        try:
            from PyQt6.QtWidgets import QCheckBox

            toggle = QCheckBox(spec.get('label', 'Toggle'))

            # Store reference
            widget_id = f"toggle_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = toggle

            return toggle

        except Exception as e:
            log.error(f"Failed to create toggle: {e}")
            return None

    def _create_dropdown(self, spec: dict[str, Any]) -> QWidget | None:
        """Create dropdown combobox widget."""
        try:
            from PyQt6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

            # Create container
            container = QWidget()
            layout = QVBoxLayout(container)

            # Create label
            label = QLabel(spec.get('label', 'Dropdown'))
            layout.addWidget(label)

            # Create combobox
            combo = QComboBox()
            options = spec.get('options', [])
            combo.addItems(options)

            layout.addWidget(combo)

            # Store reference
            widget_id = f"dropdown_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = container

            return container

        except Exception as e:
            log.error(f"Failed to create dropdown: {e}")
            return None

    def _create_value_display(self, spec: dict[str, Any]) -> QWidget | None:
        """Create value display widget."""
        try:
            from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

            # Create container
            container = QWidget()
            layout = QVBoxLayout(container)

            # Create label
            label_text = spec.get('label', 'Value')
            unit = spec.get('unit', '')
            if unit:
                label_text += f" ({unit})"

            label = QLabel(label_text)
            layout.addWidget(label)

            # Create value display
            value_label = QLabel("0.000")
            value_label.setStyleSheet("font-size: 14px; font-weight: bold;")
            layout.addWidget(value_label)

            # Store reference
            widget_id = f"display_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = container

            if 'source' in spec:
                self.widget_sources[widget_id] = spec['source']

            return container

        except Exception as e:
            log.error(f"Failed to create value display: {e}")
            return None

    def _create_text_display(self, spec: dict[str, Any]) -> QWidget | None:
        """Create text display widget."""
        try:
            from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

            # Create container
            container = QWidget()
            layout = QVBoxLayout(container)

            # Create label
            label = QLabel(spec.get('label', 'Text'))
            layout.addWidget(label)

            # Create text display
            text_label = QLabel("No data")
            text_label.setWordWrap(True)
            layout.addWidget(text_label)

            # Store reference
            widget_id = f"text_{len(self.qt_widgets)}"
            self.qt_widgets[widget_id] = container

            if 'source' in spec:
                self.widget_sources[widget_id] = spec['source']

            return container

        except Exception as e:
            log.error(f"Failed to create text display: {e}")
            return None

    def _create_row_layout(self, spec: dict[str, Any]) -> QWidget | None:
        """Create horizontal row of widgets."""
        try:
            from PyQt6.QtWidgets import QHBoxLayout, QWidget

            container = QWidget()
            layout = QHBoxLayout(container)

            widgets = spec.get('widgets', [])
            for widget_spec in widgets:
                widget = self._create_widget_from_spec(widget_spec)
                if widget:
                    layout.addWidget(widget)

            return container

        except Exception as e:
            log.error(f"Failed to create row layout: {e}")
            return None

    def _create_column_layout(self, spec: dict[str, Any]) -> QWidget | None:
        """Create vertical column of widgets."""
        try:
            from PyQt6.QtWidgets import QVBoxLayout, QWidget

            container = QWidget()
            layout = QVBoxLayout(container)

            widgets = spec.get('widgets', [])
            for widget_spec in widgets:
                widget = self._create_widget_from_spec(widget_spec)
                if widget:
                    layout.addWidget(widget)

            return container

        except Exception as e:
            log.error(f"Failed to create column layout: {e}")
            return None

    def _create_tabs(self, spec: dict[str, Any]) -> QWidget | None:
        """Create tabbed widget container."""
        try:
            from PyQt6.QtWidgets import QTabWidget

            tab_widget = QTabWidget()

            tabs = spec.get('tabs', {})
            for tab_name, tab_spec in tabs.items():
                widget = self._create_widget_from_spec(tab_spec)
                if widget:
                    tab_widget.addTab(widget, tab_name)

            return tab_widget

        except Exception as e:
            log.error(f"Failed to create tabs: {e}")
            return None

    def _update_from_event(self, event: Event) -> None:
        """Update widgets from EventBus event (called in Qt thread).

        Args:
            event: Event containing data updates.
        """
        try:
            # Update all widgets that have matching sources
            for widget_id, source in self.widget_sources.items():
                widget = self.qt_widgets.get(widget_id)
                if widget is None:
                    continue

                # Parse data for this widget's source
                data = self._parse_source_data(event, source)
                if data is not None:
                    self._update_widget_data(widget_id, widget, data)

        except Exception as e:
            log.error(f"Failed to update composite window from event: {e}")

    def _update_widget_data(self, widget_id: str, widget: QWidget, data: Any) -> None:
        """Update specific widget with new data.

        Args:
            widget_id: Widget identifier.
            widget: Qt widget instance.
            data: New data value.
        """
        try:
            # Determine widget type from ID and update accordingly
            if widget_id.startswith('plot_'):
                self._update_plot_widget(widget, data)
            elif widget_id.startswith('display_'):
                self._update_display_widget(widget, data)
            elif widget_id.startswith('text_'):
                self._update_text_widget(widget, data)
            # Add more widget type handlers as needed

        except Exception as e:
            log.error(f"Failed to update widget {widget_id}: {e}")

    def _update_plot_widget(self, widget: QWidget, data: Any) -> None:
        """Update plot widget with new data."""
        # Basic plot update - implement based on data format
        # This is a simplified version
        log.debug(f"Updating plot widget with data: {type(data)}")

    def _update_display_widget(self, widget: QWidget, data: Any) -> None:
        """Update value display widget."""
        try:
            from PyQt6.QtWidgets import QLabel

            # Find value label (second child)
            layout = widget.layout()
            if layout and layout.count() > 1:
                value_label = layout.itemAt(1).widget()
                if isinstance(value_label, QLabel):
                    if isinstance(data, (int, float)):
                        value_label.setText(f"{data:.3f}")
                    else:
                        value_label.setText(str(data))

        except Exception as e:
            log.error(f"Failed to update display widget: {e}")

    def _update_text_widget(self, widget: QWidget, data: Any) -> None:
        """Update text display widget."""
        try:
            from PyQt6.QtWidgets import QLabel

            # Find text label (second child)
            layout = widget.layout()
            if layout and layout.count() > 1:
                text_label = layout.itemAt(1).widget()
                if isinstance(text_label, QLabel):
                    text_label.setText(str(data))

        except Exception as e:
            log.error(f"Failed to update text widget: {e}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        log.info(f"Closing composite window: {self.window_id}")

        # Call parent close handler
        LabPilotWindow.closeEvent(self, event)
