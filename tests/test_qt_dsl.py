"""
Comprehensive tests for LabPilot Qt DSL system.

Tests all 15 DSL functions and the window specification generation.
Uses mock objects to avoid requiring actual Qt/pyqtgraph installation for CI.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import uuid
import sys
from typing import Any, Dict

# Mock Qt modules for testing without Qt installation
class MockQtModule:
    """Mock Qt module for testing."""
    def __getattr__(self, name):
        return Mock()

# Install Qt mocks before importing DSL
sys.modules['PyQt6'] = MockQtModule()
sys.modules['PyQt6.QtWidgets'] = MockQtModule()
sys.modules['PyQt6.QtCore'] = MockQtModule()
sys.modules['PyQt6.QtGui'] = MockQtModule()
sys.modules['pyqtgraph'] = MockQtModule()

# Now import DSL components
from labpilot_core.qt.dsl import (
    Window, Widget, window, spectrum_plot, waveform_plot, image_view,
    scatter_plot, volume_view, slider, dropdown, toggle, button,
    value_display, text_display, row, column, tabs, show,
    _validate_source, _validate_device
)


class TestWidget:
    """Test Widget class."""

    def test_widget_creation(self):
        """Test Widget creation with spec."""
        spec = {"type": "test", "param": "value"}
        widget = Widget(spec)

        # Should store spec and allow retrieval
        assert widget.to_spec() == spec
        assert widget.to_spec() is not widget._spec  # Should be a copy

    def test_widget_spec_copy(self):
        """Test that to_spec returns a copy, not reference."""
        spec = {"type": "test", "mutable": ["list"]}
        widget = Widget(spec)

        returned_spec = widget.to_spec()
        returned_spec["new_key"] = "new_value"
        # Note: to_spec() does a shallow copy, so nested objects are still references

        # Original spec should be unchanged for top-level keys
        assert "new_key" not in widget._spec
        # But nested objects are still references (this is expected behavior)
        assert widget._spec["mutable"] == spec["mutable"]


class TestWindow:
    """Test Window class."""

    def test_window_creation(self):
        """Test Window creation."""
        win = Window("Test Window", "vertical")

        assert win.title == "Test Window"
        assert win.layout == "vertical"
        assert len(win._widgets) == 0

    def test_window_add_widget(self):
        """Test adding widgets to window."""
        win = Window("Test", "horizontal")
        widget1 = Widget({"type": "test1"})
        widget2 = Widget({"type": "test2"})

        # Should support method chaining
        result = win.add(widget1).add(widget2)
        assert result is win
        assert len(win._widgets) == 2
        assert win._widgets[0] is widget1
        assert win._widgets[1] is widget2

    def test_window_to_spec(self):
        """Test window spec generation."""
        win = Window("My Window", "grid")
        widget1 = Widget({"type": "plot", "source": "device.param"})
        widget2 = Widget({"type": "control", "device": "device"})

        win.add(widget1).add(widget2)

        spec = win.to_spec()
        expected = {
            "type": "window",
            "title": "My Window",
            "layout": "grid",
            "widgets": [
                {"type": "plot", "source": "device.param"},
                {"type": "control", "device": "device"}
            ]
        }

        assert spec == expected


class TestDSLFunctions:
    """Test all DSL functions for correct spec generation."""

    def test_window_function(self):
        """Test window() function."""
        # Default layout
        win = window("Test Window")
        assert isinstance(win, Window)
        assert win.title == "Test Window"
        assert win.layout == "vertical"

        # Custom layout
        win2 = window("Test", "horizontal")
        assert win2.layout == "horizontal"

        # Invalid layout should raise error
        with pytest.raises(ValueError, match="Invalid layout"):
            window("Test", "invalid")

    def test_spectrum_plot(self):
        """Test spectrum_plot() function."""
        # Default parameters
        widget = spectrum_plot("device.intensities")
        spec = widget.to_spec()

        expected = {
            "type": "spectrum_plot",
            "source": "device.intensities",
            "xlabel": "Wavelength (nm)",
            "ylabel": "Intensity (counts)",
            "show_peak": False,
            "log_y": False
        }
        assert spec == expected

        # Custom parameters
        widget2 = spectrum_plot(
            "spec.data",
            xlabel="Frequency (Hz)",
            ylabel="Power (dB)",
            show_peak=True,
            log_y=True
        )
        spec2 = widget2.to_spec()

        assert spec2["source"] == "spec.data"
        assert spec2["xlabel"] == "Frequency (Hz)"
        assert spec2["ylabel"] == "Power (dB)"
        assert spec2["show_peak"] == True
        assert spec2["log_y"] == True

    def test_waveform_plot(self):
        """Test waveform_plot() function."""
        widget = waveform_plot("lockin.signal", n_samples=500, channels=["X", "Y"])
        spec = widget.to_spec()

        expected = {
            "type": "waveform_plot",
            "source": "lockin.signal",
            "n_samples": 500,
            "channels": ["X", "Y"],
            "xlabel": "Time (s)"
        }
        assert spec == expected

    def test_image_view(self):
        """Test image_view() function."""
        widget = image_view("camera.frame", colormap="grays", show_roi=True)
        spec = widget.to_spec()

        expected = {
            "type": "image_view",
            "source": "camera.frame",
            "colormap": "grays",
            "show_histogram": True,
            "show_roi": True
        }
        assert spec == expected

    def test_scatter_plot(self):
        """Test scatter_plot() function."""
        widget = scatter_plot("stage.x", "detector.y", "Position", "Signal")
        spec = widget.to_spec()

        expected = {
            "type": "scatter_plot",
            "x_source": "stage.x",
            "y_source": "detector.y",
            "xlabel": "Position",
            "ylabel": "Signal"
        }
        assert spec == expected

    def test_volume_view(self):
        """Test volume_view() function."""
        widget = volume_view("scanner.volume", "viridis")
        spec = widget.to_spec()

        expected = {
            "type": "volume_view",
            "source": "scanner.volume",
            "colormap": "viridis"
        }
        assert spec == expected

    def test_slider(self):
        """Test slider() function."""
        widget = slider("Power", "laser", "power_mw", 0.0, 100.0, 0.1)
        spec = widget.to_spec()

        expected = {
            "type": "slider",
            "label": "Power",
            "device": "laser",
            "param": "power_mw",
            "min": 0.0,
            "max": 100.0,
            "step": 0.1
        }
        assert spec == expected

        # Test without step (should be None)
        widget2 = slider("Voltage", "supply", "voltage", -10, 10)
        assert widget2.to_spec()["step"] is None

    def test_dropdown(self):
        """Test dropdown() function."""
        options = ["Low", "Medium", "High"]
        widget = dropdown("Gain", "amplifier", "gain_setting", options)
        spec = widget.to_spec()

        expected = {
            "type": "dropdown",
            "label": "Gain",
            "device": "amplifier",
            "param": "gain_setting",
            "options": options
        }
        assert spec == expected

    def test_toggle(self):
        """Test toggle() function."""
        widget = toggle("Enable", "device", "enabled")
        spec = widget.to_spec()

        expected = {
            "type": "toggle",
            "label": "Enable",
            "device": "device",
            "param": "enabled"
        }
        assert spec == expected

    def test_button(self):
        """Test button() function."""
        # With device
        widget1 = button("Start", "trigger", "camera")
        spec1 = widget1.to_spec()

        expected1 = {
            "type": "button",
            "label": "Start",
            "action": "trigger",
            "device": "camera"
        }
        assert spec1 == expected1

        # Without device
        widget2 = button("Emergency Stop", "stop")
        spec2 = widget2.to_spec()

        expected2 = {
            "type": "button",
            "label": "Emergency Stop",
            "action": "stop",
            "device": None
        }
        assert spec2 == expected2

    def test_value_display(self):
        """Test value_display() function."""
        widget = value_display("Temp", "sensor.temperature", "{:.2f}", "°C")
        spec = widget.to_spec()

        expected = {
            "type": "value_display",
            "label": "Temp",
            "source": "sensor.temperature",
            "format": "{:.2f}",
            "unit": "°C"
        }
        assert spec == expected

    def test_text_display(self):
        """Test text_display() function."""
        widget = text_display("Status", "device.status")
        spec = widget.to_spec()

        expected = {
            "type": "text_display",
            "label": "Status",
            "source": "device.status"
        }
        assert spec == expected

    def test_row(self):
        """Test row() layout function."""
        widget1 = Widget({"type": "a"})
        widget2 = Widget({"type": "b"})

        row_widget = row(widget1, widget2)
        spec = row_widget.to_spec()

        expected = {
            "type": "row",
            "widgets": [{"type": "a"}, {"type": "b"}]
        }
        assert spec == expected

    def test_column(self):
        """Test column() layout function."""
        widget1 = Widget({"type": "x"})
        widget2 = Widget({"type": "y"})

        col_widget = column(widget1, widget2)
        spec = col_widget.to_spec()

        expected = {
            "type": "column",
            "widgets": [{"type": "x"}, {"type": "y"}]
        }
        assert spec == expected

    def test_tabs(self):
        """Test tabs() function."""
        widget1 = Widget({"type": "control"})
        widget2 = Widget({"type": "monitor"})

        tabs_widget = tabs(Control=widget1, Monitor=widget2)
        spec = tabs_widget.to_spec()

        expected = {
            "type": "tabs",
            "tabs": {
                "Control": {"type": "control"},
                "Monitor": {"type": "monitor"}
            }
        }
        assert spec == expected


class TestValidation:
    """Test DSL validation functions."""

    def test_validate_source_valid(self):
        """Test valid source strings."""
        # Should not raise
        _validate_source("device.parameter")
        _validate_source("spectrometer.intensities")
        _validate_source("camera.frame")

    def test_validate_source_invalid(self):
        """Test invalid source strings."""
        # No dot
        with pytest.raises(ValueError, match="must be 'device.parameter' format"):
            _validate_source("deviceparameter")

        # Multiple dots
        with pytest.raises(ValueError, match="must have exactly one dot"):
            _validate_source("device.sub.parameter")

        # Empty parts
        with pytest.raises(ValueError, match="must be non-empty"):
            _validate_source(".parameter")
        with pytest.raises(ValueError, match="must be non-empty"):
            _validate_source("device.")
        with pytest.raises(ValueError, match="must be non-empty"):
            _validate_source(".")

        # Wrong type
        with pytest.raises(ValueError, match="must be string"):
            _validate_source(123)

    def test_validate_device_valid(self):
        """Test valid device names."""
        # Should not raise
        _validate_device("spectrometer")
        _validate_device("camera_1")
        _validate_device("laser-controller")

    def test_validate_device_invalid(self):
        """Test invalid device names."""
        # Empty string
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_device("")

        # Wrong type
        with pytest.raises(ValueError, match="must be string"):
            _validate_device(None)


class TestShowFunction:
    """Test the show() function that spawns windows."""

    def setup_method(self):
        """Reset the Qt bridge cache before each test."""
        import labpilot_core.qt.dsl
        labpilot_core.qt.dsl._qt_bridge = None

    @patch('labpilot_core.qt.bridge.get_bridge')
    def test_show_with_bridge(self, mock_get_bridge):
        """Test show() function with active Qt bridge."""
        # Setup mock bridge
        mock_bridge = Mock()
        mock_get_bridge.return_value = mock_bridge

        # Create window
        win = window("Test Window")
        win.add(spectrum_plot("device.data"))

        # Call show
        show(win)

        # Verify bridge was called
        mock_bridge.open_window.assert_called_once()
        call_args = mock_bridge.open_window.call_args
        window_id, spec = call_args[0]

        # Check window ID format
        assert window_id.startswith("dsl_")
        assert len(window_id) == 12  # "dsl_" + 8 hex chars

        # Check spec
        assert spec["type"] == "window"
        assert spec["title"] == "Test Window"
        assert len(spec["widgets"]) == 1

    @patch('labpilot_core.qt.bridge.get_bridge')
    def test_show_no_bridge(self, mock_get_bridge):
        """Test show() function when Qt bridge not available."""
        # Setup mock to return None
        mock_get_bridge.return_value = None

        win = window("Test")

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Qt bridge not started"):
            show(win)

    @patch('labpilot_core.qt.bridge.get_bridge')
    def test_show_bridge_lazy_import(self, mock_get_bridge):
        """Test that show() lazily imports and caches bridge."""
        mock_bridge = Mock()
        mock_get_bridge.return_value = mock_bridge

        win = window("Test")

        # First call should import bridge
        show(win)
        mock_get_bridge.assert_called_once()

        # Second call should use cached bridge
        mock_get_bridge.reset_mock()
        show(win)
        mock_get_bridge.assert_not_called()


class TestDSLIntegration:
    """Test complete DSL usage patterns."""

    def test_simple_gui_generation(self):
        """Test a simple GUI generation pattern."""
        # This is the kind of code AI would generate
        win = window("Spectrometer Control", "vertical")
        win.add(spectrum_plot("spec.intensities", show_peak=True))
        win.add(row(
            slider("Integration", "spec", "integration_time", 1, 10000),
            button("Acquire", "trigger", "spec")
        ))
        win.add(value_display("Peak Position", "spec.peak_wavelength", "{:.2f}", "nm"))

        spec = win.to_spec()

        # Verify structure
        assert spec["type"] == "window"
        assert spec["title"] == "Spectrometer Control"
        assert spec["layout"] == "vertical"
        assert len(spec["widgets"]) == 3

        # Check spectrum plot
        plot_spec = spec["widgets"][0]
        assert plot_spec["type"] == "spectrum_plot"
        assert plot_spec["show_peak"] == True

        # Check row layout with controls
        row_spec = spec["widgets"][1]
        assert row_spec["type"] == "row"
        assert len(row_spec["widgets"]) == 2
        assert row_spec["widgets"][0]["type"] == "slider"
        assert row_spec["widgets"][1]["type"] == "button"

        # Check value display
        value_spec = spec["widgets"][2]
        assert value_spec["type"] == "value_display"
        assert value_spec["unit"] == "nm"

    def test_complex_gui_with_tabs(self):
        """Test complex GUI with tabbed interface."""
        # Control tab
        control_tab = column(
            slider("Power", "laser", "power", 0, 100),
            dropdown("Mode", "laser", "mode", ["CW", "Pulsed"]),
            toggle("Enable", "laser", "enabled")
        )

        # Monitor tab
        monitor_tab = column(
            value_display("Power", "laser.power", "{:.1f}", "mW"),
            value_display("Current", "laser.current", "{:.0f}", "mA"),
            text_display("Status", "laser.status")
        )

        # Main window with tabs
        win = window("Laser Control Panel", "vertical")
        win.add(tabs(Control=control_tab, Monitor=monitor_tab))

        spec = win.to_spec()

        # Verify tabs structure
        tabs_spec = spec["widgets"][0]
        assert tabs_spec["type"] == "tabs"
        assert "Control" in tabs_spec["tabs"]
        assert "Monitor" in tabs_spec["tabs"]

        # Check control tab contents
        control_spec = tabs_spec["tabs"]["Control"]
        assert control_spec["type"] == "column"
        assert len(control_spec["widgets"]) == 3

        # Check monitor tab contents
        monitor_spec = tabs_spec["tabs"]["Monitor"]
        assert monitor_spec["type"] == "column"
        assert len(monitor_spec["widgets"]) == 3

    def test_error_handling_in_dsl_chain(self):
        """Test that validation errors are caught during DSL construction."""
        # Invalid source format should be caught immediately
        with pytest.raises(ValueError):
            spectrum_plot("invalid_source")  # No dot

        # Invalid device should be caught
        with pytest.raises(ValueError):
            slider("Test", "", "param", 0, 10)  # Empty device name

        # But valid construction should work
        try:
            win = window("Test")
            win.add(spectrum_plot("device.param"))
            win.add(slider("Control", "device", "param", 0, 100))
            spec = win.to_spec()  # Should not raise
            assert len(spec["widgets"]) == 2
        except Exception as e:
            pytest.fail(f"Valid DSL construction raised exception: {e}")


if __name__ == "__main__":
    pytest.main([__file__])