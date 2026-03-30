"""WindowFactory - Maps DSL specifications to Qt window types.

Routes window specifications from DSL to appropriate window implementations.
Factory pattern allows easy addition of new window types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow

__all__ = ["WindowFactory", "WindowFactoryError"]


class WindowFactoryError(Exception):
    """Raised when window creation fails."""


class WindowFactory:
    """Factory for creating Qt windows from DSL specifications."""

    @staticmethod
    def create_window(window_id: str, spec: dict[str, Any]) -> QMainWindow:
        """Create Qt window from DSL specification.

        Args:
            window_id: Unique window identifier.
            spec: Window specification dictionary from DSL.

        Returns:
            Qt window instance.

        Raises:
            WindowFactoryError: If window creation fails.
        """
        try:
            window_type = spec.get("type")
            if window_type != "window":
                raise WindowFactoryError(f"Invalid window type: {window_type}")

            title = spec.get("title", "LabPilot Window")
            layout = spec.get("layout", "vertical")
            widgets = spec.get("widgets", [])

            # Determine window type from widgets
            if len(widgets) == 1:
                widget_spec = widgets[0]
                widget_type = widget_spec.get("type")

                # Single-widget windows - specialized implementations
                if widget_type == "spectrum_plot":
                    return WindowFactory._create_spectrum_window(window_id, title, widget_spec)
                elif widget_type == "image_view":
                    return WindowFactory._create_image_window(window_id, title, widget_spec)
                elif widget_type == "waveform_plot":
                    return WindowFactory._create_waveform_window(window_id, title, widget_spec)
                elif widget_type == "volume_view":
                    return WindowFactory._create_volume_window(window_id, title, widget_spec)

            # Multi-widget windows - composite implementation
            return WindowFactory._create_composite_window(window_id, title, layout, widgets)

        except Exception as e:
            raise WindowFactoryError(f"Failed to create window {window_id}: {e}") from e

    @staticmethod
    def _create_spectrum_window(
        window_id: str, title: str, spec: dict[str, Any]
    ) -> QMainWindow:
        """Create spectrum plot window.

        Args:
            window_id: Window identifier.
            title: Window title.
            spec: Spectrum plot specification.

        Returns:
            SpectrumWindow instance.
        """
        from labpilot_core.qt.windows.spectrum import SpectrumWindow

        source = spec["source"]
        xlabel = spec.get("xlabel", "Wavelength (nm)")
        ylabel = spec.get("ylabel", "Intensity (counts)")
        show_peak = spec.get("show_peak", False)
        log_y = spec.get("log_y", False)

        return SpectrumWindow(
            window_id=window_id,
            title=title,
            source=source,
            xlabel=xlabel,
            ylabel=ylabel,
            show_peak=show_peak,
            log_y=log_y,
        )

    @staticmethod
    def _create_image_window(
        window_id: str, title: str, spec: dict[str, Any]
    ) -> QMainWindow:
        """Create image view window.

        Args:
            window_id: Window identifier.
            title: Window title.
            spec: Image view specification.

        Returns:
            ImageWindow instance.
        """
        from labpilot_core.qt.windows.image import ImageWindow

        source = spec["source"]
        colormap = spec.get("colormap", "inferno")
        show_histogram = spec.get("show_histogram", True)
        show_roi = spec.get("show_roi", False)

        return ImageWindow(
            window_id=window_id,
            title=title,
            source=source,
            colormap=colormap,
            show_histogram=show_histogram,
            show_roi=show_roi,
        )

    @staticmethod
    def _create_waveform_window(
        window_id: str, title: str, spec: dict[str, Any]
    ) -> QMainWindow:
        """Create waveform plot window.

        Args:
            window_id: Window identifier.
            title: Window title.
            spec: Waveform plot specification.

        Returns:
            WaveformWindow instance.
        """
        from labpilot_core.qt.windows.waveform import WaveformWindow

        source = spec["source"]
        n_samples = spec.get("n_samples", 1000)
        channels = spec.get("channels", [])
        xlabel = spec.get("xlabel", "Time (s)")

        return WaveformWindow(
            window_id=window_id,
            title=title,
            source=source,
            n_samples=n_samples,
            channels=channels,
            xlabel=xlabel,
        )

    @staticmethod
    def _create_volume_window(
        window_id: str, title: str, spec: dict[str, Any]
    ) -> QMainWindow:
        """Create volume view window.

        Args:
            window_id: Window identifier.
            title: Window title.
            spec: Volume view specification.

        Returns:
            VolumeWindow instance.
        """
        from labpilot_core.qt.windows.volume import VolumeWindow

        source = spec["source"]
        colormap = spec.get("colormap", "grays")

        return VolumeWindow(
            window_id=window_id,
            title=title,
            source=source,
            colormap=colormap,
        )

    @staticmethod
    def _create_composite_window(
        window_id: str, title: str, layout: str, widgets: list[dict[str, Any]]
    ) -> QMainWindow:
        """Create composite window with multiple widgets.

        Args:
            window_id: Window identifier.
            title: Window title.
            layout: Layout type ("vertical", "horizontal", "grid").
            widgets: List of widget specifications.

        Returns:
            CompositeWindow instance.
        """
        from labpilot_core.qt.windows.composite import CompositeWindow

        return CompositeWindow(
            window_id=window_id,
            title=title,
            layout=layout,
            widgets=widgets,
        )
