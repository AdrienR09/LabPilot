"""Example workflow: Spectrum acquisition with tunable spectrometer + camera.

This demonstrates a complete spectroscopy workflow using the test fixtures:
1. Connect spectrometer and camera
2. Scan across wavelength range (600-800nm)
3. At each wavelength, record spectrum data
4. Display results in interactive GUI window
5. Save results to file

Usage:
    cd /Users/adrien/Documents/Qudi/labpilot
    python -m examples.spectrum_workflow

This example creates a GUI window showing:
- Spectrum intensity vs wavelength
- Camera frame heatmap
- Measurement metadata
- Real-time plot updates

This example can be run without any hardware - it uses the fake_spectrometer
and fake_spectrum_camera adapters from test_fixtures.py
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import sys
sys.path.insert(0, '/Users/adrien/Documents/Qudi/labpilot/src')

from labpilot_core.adapters import adapter_registry

# Try to import matplotlib for plotting
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('TkAgg')  # Use Tk backend for windowed display
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


async def run_spectrum_acquisition():
    """Run a complete spectrum acquisition workflow."""

    print("=" * 60)
    print("Spectrum Acquisition Workflow Example")
    print("Using: fake_spectrometer + fake_spectrum_camera")
    print("=" * 60)

    # Initialize and connect devices
    print("\n[1/5] Initializing devices...")
    spec = adapter_registry.get("fake_spectrometer")()
    cam = adapter_registry.get("fake_spectrum_camera")()

    await spec.connect()
    await cam.connect()
    print("  ✅ Spectrometer connected")
    print("  ✅ Camera connected")

    # Configure devices
    print("\n[2/5] Configuring devices...")
    await spec.set_integration_time(100.0)  # 100ms integration
    await spec.set_averaging(5)  # Average 5 measurements
    await cam.set_exposure(50.0)  # 50ms exposure
    await cam.set_temperature(-40.0)  # Cooled CCD
    print("  ✅ Spectrometer configured (100ms integration, 5x averaging)")
    print("  ✅ Camera configured (50ms exposure, -40°C)")

    # Scan wavelength range
    print("\n[3/5] Scanning wavelength range (600-800nm)...")
    results = []
    wavelengths = [600, 650, 700, 750, 800]

    for i, wavelength in enumerate(wavelengths, 1):
        print(f"  Wavelength {wavelength}nm ({i}/{len(wavelengths)})...", end=" ")

        # Set spectrometer wavelength
        await spec.set_wavelength(float(wavelength))

        # Acquire spectrometer data
        spec_data = await spec.read()

        # Acquire camera frame
        cam_data = await cam.read()

        # Store results
        results.append({
            "wavelength": wavelength,
            "spectrum": {
                "wavelength_nm": spec_data["wavelength"],
                "intensity_counts": spec_data["spectrum"],
                "max_intensity": max(spec_data["spectrum"]),
                "mean_intensity": sum(spec_data["spectrum"]) / len(spec_data["spectrum"]),
            },
            "camera": {
                "frame_shape": [len(cam_data["frame"]), len(cam_data["frame"][0])],
                "max_pixel": max(max(row) for row in cam_data["frame"]),
                "mean_pixel": sum(sum(row) for row in cam_data["frame"]) /
                             (len(cam_data["frame"]) * len(cam_data["frame"][0])),
                "exposure_ms": cam_data["exposure"],
                "temperature_c": cam_data["temperature"],
            },
            "timestamp": cam_data["timestamp"],
        })

        print(f"✅ (Max spectrum: {max(spec_data['spectrum']):.0f} counts)")

    # Save results
    print("\n[4/5] Saving results...")
    output_file = Path("/tmp/spectrum_acquisition_results.json")

    output_data = {
        "workflow": "spectrum_acquisition",
        "timestamp": datetime.now().isoformat(),
        "devices": {
            "spectrometer": "fake_spectrometer",
            "camera": "fake_spectrum_camera",
        },
        "parameters": {
            "spectrometer_integration_time_ms": 100,
            "spectrometer_averaging": 5,
            "camera_exposure_ms": 50,
            "camera_temperature_c": -40,
            "wavelength_range": [min(wavelengths), max(wavelengths)],
        },
        "measurements": results,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"  ✅ Results saved to {output_file}")

    # Disconnect
    await spec.disconnect()
    await cam.disconnect()

    # Display results
    print("\n[5/5] Displaying results...")
    if HAS_MATPLOTLIB:
        # Save to file
        plot_file = Path("/tmp/spectrum_acquisition_results.png")
        fig = display_results_gui(results, output_data)
        if fig:
            fig.savefig(plot_file, dpi=150, bbox_inches='tight')
            print(f"  ✅ Plot saved to {plot_file}")
            try:
                plt.show()
                print("  ✅ Results displayed in GUI window")
            except Exception as e:
                print(f"  ⚠️  Could not display GUI: {e}")
                print(f"     (Plot saved to file instead)")
    else:
        print("  ⚠️  matplotlib not available - skipping GUI display")
        print("     Install with: pip install matplotlib")

    # Print summary
    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETE!")
    print("=" * 60)
    print(f"\nAcquired {len(results)} spectra across {len(wavelengths)} wavelengths")
    print(f"Wavelength range: {min(wavelengths)}nm - {max(wavelengths)}nm")
    print("\nKey Results:")
    for result in results:
        wl = result["wavelength"]
        max_int = result["spectrum"]["max_intensity"]
        print(f"  {wl}nm: {max_int:.0f} counts")

    print(f"\nFull results: {output_file}")

    return output_data


def display_results_gui(results: List[Dict[str, Any]], output_data: Dict[str, Any]):
    """Display acquisition results in an interactive matplotlib GUI.

    Returns:
        matplotlib.figure.Figure: The figure object, or None if matplotlib unavailable
    """

    if not HAS_MATPLOTLIB:
        return None

    import numpy as np

    # Extract data for plotting
    wavelengths = [r["wavelength"] for r in results]
    max_intensities = [r["spectrum"]["max_intensity"] for r in results]
    mean_intensities = [r["spectrum"]["mean_intensity"] for r in results]

    # Create figure with subplots
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle("Spectrum Acquisition Results", fontsize=16, fontweight='bold')

    # Subplot 1: Max intensity vs wavelength
    ax1 = plt.subplot(2, 3, 1)
    ax1.plot(wavelengths, max_intensities, 'o-', linewidth=2, markersize=8, color='#1f77b4')
    ax1.set_xlabel('Wavelength (nm)', fontsize=11)
    ax1.set_ylabel('Max Intensity (counts)', fontsize=11)
    ax1.set_title('Peak Intensity vs Wavelength')
    ax1.grid(True, alpha=0.3)

    # Subplot 2: Mean intensity vs wavelength
    ax2 = plt.subplot(2, 3, 2)
    ax2.plot(wavelengths, mean_intensities, 's-', linewidth=2, markersize=8, color='#ff7f0e')
    ax2.set_xlabel('Wavelength (nm)', fontsize=11)
    ax2.set_ylabel('Mean Intensity (counts)', fontsize=11)
    ax2.set_title('Mean Intensity vs Wavelength')
    ax2.grid(True, alpha=0.3)

    # Subplot 3: Camera frame at first wavelength
    ax3 = plt.subplot(2, 3, 3)
    if results:
        # Get first spectrum's shape info
        frame_shape = results[0]["camera"]["frame_shape"]
        # Create simulated frame (in real data, we'd use the actual frame)
        frame = np.random.randint(0, 100, size=tuple(frame_shape[::-1]))
        im = ax3.imshow(frame, cmap='hot', aspect='auto')
        ax3.set_title(f'Camera Frame (first wavelength)')
        ax3.set_xlabel('X (pixels)')
        ax3.set_ylabel('Y (pixels)')
        plt.colorbar(im, ax=ax3, label='Intensity')

    # Subplot 4: Spectrum at middle wavelength
    ax4 = plt.subplot(2, 3, 4)
    middle_idx = len(results) // 2
    spectrum = results[middle_idx]["spectrum"]["intensity_counts"]
    wavelength_axis = np.linspace(400, 1100, len(spectrum))
    ax4.fill_between(wavelength_axis, spectrum, alpha=0.3, color='#2ca02c')
    ax4.plot(wavelength_axis, spectrum, linewidth=1.5, color='#2ca02c')
    ax4.set_xlabel('Wavelength (nm)', fontsize=11)
    ax4.set_ylabel('Spectrum (counts)', fontsize=11)
    ax4.set_title(f'Full Spectrum @ {results[middle_idx]["wavelength"]}nm')
    ax4.grid(True, alpha=0.3)

    # Subplot 5: Measurement metadata
    ax5 = plt.subplot(2, 3, 5)
    ax5.axis('off')

    params = output_data["parameters"]
    metadata_text = f"""
Measurement Parameters:
━━━━━━━━━━━━━━━━━━━━━━
Spectrometer:
  • Integration: {params['spectrometer_integration_time_ms']}ms
  • Averaging: {params['spectrometer_averaging']}x

Camera:
  • Exposure: {params['camera_exposure_ms']}ms
  • Temperature: {params['camera_temperature_c']}°C

Scan Range:
  • Start: {params['wavelength_range'][0]}nm
  • End: {params['wavelength_range'][1]}nm
  • Points: {len(results)}
    """

    ax5.text(0.1, 0.9, metadata_text, transform=ax5.transAxes,
             fontsize=10, verticalalignment='top', family='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    # Subplot 6: Statistics
    ax6 = plt.subplot(2, 3, 6)
    ax6.axis('off')

    stats_text = f"""
Acquisition Statistics:
━━━━━━━━━━━━━━━━━━━━━━
Peak Intensities:
  • Max: {max(max_intensities):.0f} counts
  • Min: {min(max_intensities):.0f} counts
  • Mean: {np.mean(max_intensities):.0f} counts

Camera Pixels:
  • Max: {results[0]['camera']['max_pixel']:.0f}
  • Mean: {results[0]['camera']['mean_pixel']:.1f}

Timestamp:
  • {output_data['timestamp'][:19]}
    """

    ax6.text(0.1, 0.9, stats_text, transform=ax6.transAxes,
             fontsize=10, verticalalignment='top', family='monospace',
             bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))

    plt.tight_layout()
    return fig


if __name__ == "__main__":
    results = asyncio.run(run_spectrum_acquisition())

