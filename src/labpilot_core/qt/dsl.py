"""LabPilot GUI DSL - the ONLY interface the AI uses to generate Qt windows.

All PyQt6 and pyqtgraph complexity is hidden inside these 15 functions.
The AI generates calls to these functions. The DSL builds a spec dict.
The spec dict is passed to WindowFactory which spawns the Qt window.

Global invariants:
- AI never writes raw PyQt6/Qt code - only DSL function calls
- All source= strings use "device_name.parameter_name" format
- All device= strings must match connected device names
- show(window) must be the final line of AI-generated code
- Generated code must be valid Python syntax
"""

from __future__ import annotations

from typing import Any, Literal

__all__ = [
    "Widget",
    "Window",
    "button",
    "column",
    "dropdown",
    "image_view",
    "row",
    "scatter_plot",
    "show",
    "slider",
    "spectrum_plot",
    "tabs",
    "text_display",
    "toggle",
    "value_display",
    "volume_view",
    "waveform_plot",
    "window",
]

# Global bridge instance - set by QtBridge.start()
_qt_bridge: QtBridge | None = None


class Widget:
    """Represents a UI widget in the DSL spec."""

    def __init__(self, spec: dict[str, Any]) -> None:
        """Initialize widget with spec dictionary.

        Args:
            spec: Widget specification dictionary.
        """
        self._spec = spec

    def to_spec(self) -> dict[str, Any]:
        """Convert widget to specification dictionary.

        Returns:
            Widget specification dictionary.
        """
        return self._spec.copy()


class Window:
    """Represents a top-level window in the DSL spec."""

    def __init__(self, title: str, layout: str) -> None:
        """Initialize window with title and layout.

        Args:
            title: Window title.
            layout: Layout type ("vertical", "horizontal", "grid").
        """
        self.title = title
        self.layout = layout
        self._widgets: list[Widget] = []

    def add(self, widget: Widget) -> Window:
        """Add widget to window.

        Args:
            widget: Widget to add.

        Returns:
            Self for chaining.
        """
        self._widgets.append(widget)
        return self

    def to_spec(self) -> dict[str, Any]:
        """Convert window to specification dictionary.

        Returns:
            Complete window specification for Qt factory.
        """
        return {
            "type": "window",
            "title": self.title,
            "layout": self.layout,
            "widgets": [w.to_spec() for w in self._widgets],
        }


def window(title: str, layout: str = "vertical") -> Window:
    """Create a top-level window.

    Args:
        title: Window title string.
        layout: Layout type - "vertical", "horizontal", or "grid".

    Returns:
        Window object for adding widgets.

    Example:
        >>> w = window("Spectrometer Control", layout="vertical")
        >>> w.add(spectrum_plot(source="spec.intensities"))
        >>> show(w)
    """
    if layout not in ("vertical", "horizontal", "grid"):
        raise ValueError(f"Invalid layout: {layout}")

    return Window(title, layout)


def spectrum_plot(
    source: str,
    xlabel: str = "Wavelength (nm)",
    ylabel: str = "Intensity (counts)",
    show_peak: bool = False,
    log_y: bool = False,
) -> Widget:
    """Create a spectrum/wavelength plot widget.

    Args:
        source: Data source in format "device.parameter".
        xlabel: X-axis label.
        ylabel: Y-axis label.
        show_peak: Whether to show peak finding overlay.
        log_y: Whether to use logarithmic Y-axis.

    Returns:
        Widget for spectrum plotting.

    Example:
        >>> plot = spectrum_plot(
        ...     source="spectrometer.intensities",
        ...     show_peak=True,
        ...     log_y=False
        ... )
    """
    _validate_source(source)

    return Widget({
        "type": "spectrum_plot",
        "source": source,
        "xlabel": xlabel,
        "ylabel": ylabel,
        "show_peak": show_peak,
        "log_y": log_y,
    })


def waveform_plot(
    source: str,
    n_samples: int = 1000,
    channels: list[str] | None = None,
    xlabel: str = "Time (s)",
) -> Widget:
    """Create a real-time waveform plot with rolling buffer.

    Args:
        source: Data source in format "device.parameter".
        n_samples: Number of samples in rolling buffer.
        channels: List of channel names (auto-detected if None).
        xlabel: X-axis label.

    Returns:
        Widget for waveform plotting.

    Example:
        >>> plot = waveform_plot(
        ...     source="lockin.xy_signal",
        ...     n_samples=2000,
        ...     channels=["X", "Y"]
        ... )
    """
    _validate_source(source)

    return Widget({
        "type": "waveform_plot",
        "source": source,
        "n_samples": n_samples,
        "channels": channels or [],
        "xlabel": xlabel,
    })


def image_view(
    source: str,
    colormap: str = "inferno",
    show_histogram: bool = True,
    show_roi: bool = False,
) -> Widget:
    """Create an image display widget with histogram and ROI.

    Args:
        source: Data source in format "device.parameter".
        colormap: Colormap name ("inferno", "viridis", "grays", etc.).
        show_histogram: Whether to show intensity histogram.
        show_roi: Whether to show ROI selection overlay.

    Returns:
        Widget for image display.

    Example:
        >>> img = image_view(
        ...     source="camera.frame",
        ...     colormap="grays",
        ...     show_roi=True
        ... )
    """
    _validate_source(source)

    return Widget({
        "type": "image_view",
        "source": source,
        "colormap": colormap,
        "show_histogram": show_histogram,
        "show_roi": show_roi,
    })


def scatter_plot(x_source: str, y_source: str, xlabel: str = "x", ylabel: str = "y") -> Widget:
    """Create an X-Y scatter plot widget.

    Args:
        x_source: X data source in format "device.parameter".
        y_source: Y data source in format "device.parameter".
        xlabel: X-axis label.
        ylabel: Y-axis label.

    Returns:
        Widget for scatter plotting.

    Example:
        >>> plot = scatter_plot(
        ...     x_source="stage.position",
        ...     y_source="detector.signal",
        ...     xlabel="Position (mm)",
        ...     ylabel="Signal (V)"
        ... )
    """
    _validate_source(x_source)
    _validate_source(y_source)

    return Widget({
        "type": "scatter_plot",
        "x_source": x_source,
        "y_source": y_source,
        "xlabel": xlabel,
        "ylabel": ylabel,
    })


def volume_view(source: str, colormap: str = "grays") -> Widget:
    """Create a 3D volume rendering widget.

    Args:
        source: Data source in format "device.parameter" (3D array).
        colormap: Colormap for volume rendering.

    Returns:
        Widget for 3D volume display.

    Example:
        >>> vol = volume_view(
        ...     source="scanner.volume_data",
        ...     colormap="viridis"
        ... )
    """
    _validate_source(source)

    return Widget({
        "type": "volume_view",
        "source": source,
        "colormap": colormap,
    })


def slider(
    label: str,
    device: str,
    param: str,
    min: float,
    max: float,
    step: float | None = None,
) -> Widget:
    """Create a parameter control slider.

    Args:
        label: Display label for the slider.
        device: Device name (must be connected).
        param: Parameter name on the device.
        min: Minimum value.
        max: Maximum value.
        step: Step size (auto-calculated if None).

    Returns:
        Widget for parameter control.

    Example:
        >>> s = slider(
        ...     "Wavelength", "laser", "wavelength_nm",
        ...     400.0, 800.0, 0.1
        ... )
    """
    _validate_device(device)

    return Widget({
        "type": "slider",
        "label": label,
        "device": device,
        "param": param,
        "min": min,
        "max": max,
        "step": step,
    })


def dropdown(label: str, device: str, param: str, options: list[str]) -> Widget:
    """Create a parameter dropdown selector.

    Args:
        label: Display label for the dropdown.
        device: Device name (must be connected).
        param: Parameter name on the device.
        options: List of selectable options.

    Returns:
        Widget for parameter selection.

    Example:
        >>> d = dropdown(
        ...     "Filter", "wheel", "position",
        ...     ["Open", "ND1", "ND2", "ND3"]
        ... )
    """
    _validate_device(device)

    return Widget({
        "type": "dropdown",
        "label": label,
        "device": device,
        "param": param,
        "options": options,
    })


def toggle(label: str, device: str, param: str) -> Widget:
    """Create a boolean toggle control.

    Args:
        label: Display label for the toggle.
        device: Device name (must be connected).
        param: Parameter name on the device.

    Returns:
        Widget for boolean control.

    Example:
        >>> t = toggle("Laser Enable", "laser", "output_enabled")
    """
    _validate_device(device)

    return Widget({
        "type": "toggle",
        "label": label,
        "device": device,
        "param": param,
    })


def button(
    label: str,
    action: Literal["trigger", "start", "stop", "snap", "zero", "arm"],
    device: str | None = None,
) -> Widget:
    """Create an action button.

    Args:
        label: Button text.
        action: Action type to perform.
        device: Device name (required for device actions).

    Returns:
        Widget for action triggering.

    Example:
        >>> b1 = button("Acquire", "trigger", "camera")
        >>> b2 = button("Emergency Stop", "stop")
    """
    if device is not None:
        _validate_device(device)

    return Widget({
        "type": "button",
        "label": label,
        "action": action,
        "device": device,
    })


def value_display(
    label: str,
    source: str,
    format: str = "{:.3f}",
    unit: str = "",
) -> Widget:
    """Create a numeric value display.

    Args:
        label: Display label.
        source: Data source in format "device.parameter".
        format: Python format string for value.
        unit: Unit string to display.

    Returns:
        Widget for value display.

    Example:
        >>> v = value_display(
        ...     "Temperature", "controller.temperature",
        ...     format="{:.2f}", unit="°C"
        ... )
    """
    _validate_source(source)

    return Widget({
        "type": "value_display",
        "label": label,
        "source": source,
        "format": format,
        "unit": unit,
    })


def text_display(label: str, source: str) -> Widget:
    """Create a text value display.

    Args:
        label: Display label.
        source: Data source in format "device.parameter".

    Returns:
        Widget for text display.

    Example:
        >>> t = text_display("Status", "device.status_message")
    """
    _validate_source(source)

    return Widget({
        "type": "text_display",
        "label": label,
        "source": source,
    })


def row(*widgets: Widget) -> Widget:
    """Create a horizontal layout of widgets.

    Args:
        *widgets: Widgets to arrange horizontally.

    Returns:
        Widget containing horizontal layout.

    Example:
        >>> r = row(
        ...     slider("Power", "laser", "power", 0, 100),
        ...     button("On", "start", "laser")
        ... )
    """
    return Widget({
        "type": "row",
        "widgets": [w.to_spec() for w in widgets],
    })


def column(*widgets: Widget) -> Widget:
    """Create a vertical layout of widgets.

    Args:
        *widgets: Widgets to arrange vertically.

    Returns:
        Widget containing vertical layout.

    Example:
        >>> c = column(
        ...     value_display("Power", "laser.power", unit="mW"),
        ...     slider("Power", "laser", "power", 0, 100)
        ... )
    """
    return Widget({
        "type": "column",
        "widgets": [w.to_spec() for w in widgets],
    })


def tabs(**named_widgets: Widget) -> Widget:
    """Create a tabbed interface.

    Args:
        **named_widgets: Keyword args of tab_name=widget pairs.

    Returns:
        Widget containing tabbed interface.

    Example:
        >>> t = tabs(
        ...     Control=column(slider(...), button(...)),
        ...     Monitor=spectrum_plot(...)
        ... )
    """
    return Widget({
        "type": "tabs",
        "tabs": {name: widget.to_spec() for name, widget in named_widgets.items()},
    })


def show(win: Window) -> None:
    """Display the window by passing spec to QtBridge.

    This must be called as the final line of AI-generated code.

    Args:
        win: Window object to display.

    Example:
        >>> w = window("My Panel")
        >>> w.add(spectrum_plot(source="spec.data"))
        >>> show(w)  # This spawns the Qt window
    """
    global _qt_bridge

    if _qt_bridge is None:
        # Import here to avoid circular imports
        from labpilot_core.qt.bridge import get_bridge
        _qt_bridge = get_bridge()

    if _qt_bridge is None:
        raise RuntimeError("Qt bridge not started. Call QtBridge.start() first.")

    import uuid

    window_id = f"dsl_{uuid.uuid4().hex[:8]}"
    spec = win.to_spec()

    # Pass to QtBridge for actual window spawning
    _qt_bridge.open_window(window_id, spec)


def _validate_source(source: str) -> None:
    """Validate source string format.

    Args:
        source: Source string to validate.

    Raises:
        ValueError: If source format is invalid.
    """
    if not isinstance(source, str):
        raise ValueError(f"Source must be string, got {type(source)}")

    if "." not in source:
        raise ValueError(f"Source must be 'device.parameter' format, got: {source}")

    parts = source.split(".")
    if len(parts) != 2:
        raise ValueError(f"Source must have exactly one dot, got: {source}")

    device, param = parts
    if not device or not param:
        raise ValueError(f"Both device and parameter must be non-empty, got: {source}")


def _validate_device(device: str) -> None:
    """Validate device name.

    Args:
        device: Device name to validate.

    Raises:
        ValueError: If device name is invalid.
    """
    if not isinstance(device, str):
        raise ValueError(f"Device must be string, got {type(device)}")

    if not device:
        raise ValueError("Device name cannot be empty")

    # TODO: Check if device exists in session registry
    # For now, just validate format
