#!/usr/bin/env python3
"""
Hybrid Instrument Windows - React Controls + PyQtGraph Plots
Combines the best of both:
- React for UI controls (buttons, sliders, etc.)
- PyQtGraph for real-time plotting
"""

import sys
import numpy as np
from typing import Dict, Any
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, QUrl, QObject, pyqtSlot
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
import pyqtgraph as pg


class InstrumentControlBridge(QObject):
    """Bridge for instrument-specific React controls"""

    def __init__(self, instrument: dict, plot_widget, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.plot_widget = plot_widget
        self.running = False

    @pyqtSlot(str, str)
    def setParameter(self, param_name: str, value: str):
        """Set instrument parameter from React"""
        print(f"[Instrument] Set {param_name} = {value}")
        self.instrument["parameters"][param_name] = float(value) if value.replace('.', '').isdigit() else value

    @pyqtSlot(result=str)
    def getParameters(self) -> str:
        """Get current parameters as JSON"""
        import json
        return json.dumps(self.instrument["parameters"])

    @pyqtSlot()
    def startAcquisition(self):
        """Start data acquisition"""
        print("[Instrument] Start acquisition")
        self.running = True

    @pyqtSlot()
    def stopAcquisition(self):
        """Stop data acquisition"""
        print("[Instrument] Stop acquisition")
        self.running = False

    @pyqtSlot()
    def saveData(self):
        """Save current data"""
        print("[Instrument] Save data")


class HybridInstrumentWindow(QMainWindow):
    """Hybrid window with React controls + PyQtGraph plot"""

    def __init__(self, instrument: dict):
        super().__init__()
        self.instrument = instrument
        self.setup_ui()
        self.setup_simulation()

    def setup_ui(self):
        """Setup window layout"""
        print(f"[HybridWindow] Setting up UI for: {self.instrument.get('name', 'Unknown')}")
        self.setWindowTitle(f"{self.instrument['name']} - Control Interface")
        self.resize(1200, 700)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter for plot and controls
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # PyQtGraph plot widget (left side - 70%)
        self.plot_widget = self.create_plot_widget()
        splitter.addWidget(self.plot_widget)

        # React controls (right side - 30%)
        self.controls_view = self.create_controls_view()
        splitter.addWidget(self.controls_view)

        # Set initial sizes (70% plot, 30% controls)
        splitter.setSizes([840, 360])

        layout.addWidget(splitter)
        print(f"[HybridWindow] UI setup complete for: {self.instrument.get('name', 'Unknown')}")

    def create_plot_widget(self):
        """Create PyQtGraph plot widget based on instrument dimensionality"""
        dimensionality = self.instrument.get("dimensionality", "0D")
        instrument_type = self.instrument.get("type", "")
        category = self.instrument.get("category", "")

        print(f"[HybridWindow] Creating plot for dimensionality: {dimensionality}, type: {instrument_type}, category: {category}")

        try:
            if dimensionality == "2D":
                # For 2D data: cameras, images, heatmaps
                print("[HybridWindow] Creating 2D ImageView")
                from pyqtgraph import ImageView
                plot_widget = ImageView()
                plot_widget.ui.histogram.hide()
                plot_widget.ui.roiBtn.hide()
                plot_widget.ui.menuBtn.hide()
                return plot_widget

            elif dimensionality == "1D":
                # For 1D data: spectra, traces, scans
                print("[HybridWindow] Creating 1D PlotWidget")
                plot_widget = pg.PlotWidget()
                plot_widget.setBackground('w')
                plot_widget.showGrid(x=True, y=True, alpha=0.3)

                # Determine axis labels based on category/type
                if any(x in category.lower() for x in ['spectrometer', 'spectrum', 'optical']):
                    plot_widget.setLabel('left', 'Intensity', units='a.u.')
                    plot_widget.setLabel('bottom', 'Wavelength', units='nm')
                elif any(x in category.lower() for x in ['oscilloscope', 'signal']):
                    plot_widget.setLabel('left', 'Voltage', units='V')
                    plot_widget.setLabel('bottom', 'Time', units='s')
                else:
                    plot_widget.setLabel('left', 'Intensity', units='a.u.')
                    plot_widget.setLabel('bottom', 'Position', units='mm')

                return plot_widget

            else:  # 0D
                # For scalar data: power meters, temperature, voltage
                print("[HybridWindow] Creating 0D PlotWidget (time series)")
                plot_widget = pg.PlotWidget()
                plot_widget.setBackground('w')
                plot_widget.showGrid(x=True, y=True, alpha=0.3)

                # Determine axis labels based on category/type
                if any(x in category.lower() for x in ['power', 'meter']):
                    plot_widget.setLabel('left', 'Power', units='mW')
                elif any(x in category.lower() for x in ['lock', 'amplifier']):
                    plot_widget.setLabel('left', 'Signal', units='mV')
                else:
                    plot_widget.setLabel('left', 'Value', units='')

                plot_widget.setLabel('bottom', 'Time', units='s')
                return plot_widget

        except Exception as e:
            print(f"[HybridWindow] Error creating plot: {e}")
            # Fallback to basic PlotWidget
            plot_widget = pg.PlotWidget()
            plot_widget.setBackground('w')
            plot_widget.showGrid(x=True, y=True, alpha=0.3)
            return plot_widget

    def create_controls_view(self):
        """Create React controls view"""
        controls_view = QWebEngineView()

        # Create bridge for React-Qt communication
        self.bridge = InstrumentControlBridge(self.instrument, self.plot_widget)
        channel = QWebChannel()
        channel.registerObject("instrumentBridge", self.bridge)
        controls_view.page().setWebChannel(channel)

        # Load controls HTML
        controls_html = self.generate_controls_html()
        controls_view.setHtml(controls_html)

        return controls_view

    def generate_controls_html(self) -> str:
        """Generate HTML with professional controls (pyMoDAQ/Qudi style)"""
        params = self.instrument.get("parameters", {})

        # Generate parameter controls grouped and organized
        param_controls = ""
        if params:
            for i, (param_name, param_value) in enumerate(params.items()):
                param_label = param_name.replace('_', ' ').title()
                # Convert value to string safely
                value_str = str(param_value) if param_value is not None else ""
                param_controls += f"""
            <div class="param-row">
                <label class="param-label">{param_label}</label>
                <input
                    type="text"
                    value="{value_str}"
                    onchange="setParameter('{param_name}', this.value)"
                    class="param-input"
                />
            </div>
            """
        else:
            param_controls = '<div style="color: #94a3b8; font-size: 12px;">No parameters available</div>'

        # Determine appropriate buttons based on dimensionality
        button_label = "Start Scan" if self.instrument.get("dimensionality") == "1D" else \
                      "Capture Image" if self.instrument.get("dimensionality") == "2D" else \
                      "Start Measurement"

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{self.instrument['name']} - Control Interface</title>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}

                body {{
                    font-family: 'Segoe UI', 'Roboto', sans-serif;
                    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                    color: #e2e8f0;
                    padding: 16px;
                    height: 100vh;
                    overflow-y: auto;
                }}

                .container {{
                    max-width: 100%;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                }}

                .header {{
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                    padding: 16px;
                    margin-bottom: 16px;
                    backdrop-filter: blur(10px);
                }}

                .device-title {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #f1f5f9;
                    margin-bottom: 8px;
                }}

                .device-info {{
                    font-size: 12px;
                    color: #94a3b8;
                    display: flex;
                    gap: 16px;
                }}

                .status-badge {{
                    display: inline-block;
                    padding: 4px 12px;
                    background: rgba(34, 197, 94, 0.1);
                    border: 1px solid rgba(34, 197, 94, 0.3);
                    border-radius: 6px;
                    color: #86efac;
                    font-size: 11px;
                    font-weight: 600;
                    text-transform: uppercase;
                }}

                .status-badge.offline {{
                    background: rgba(239, 68, 68, 0.1);
                    border-color: rgba(239, 68, 68, 0.3);
                    color: #fca5a5;
                }}

                .panel {{
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                    padding: 16px;
                    margin-bottom: 16px;
                    backdrop-filter: blur(10px);
                    flex: 1;
                    overflow-y: auto;
                }}

                .panel-title {{
                    font-size: 13px;
                    font-weight: 600;
                    color: #cbd5e1;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 12px;
                    padding-bottom: 8px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}

                .param-row {{
                    display: grid;
                    grid-template-columns: 120px 1fr;
                    gap: 12px;
                    margin-bottom: 12px;
                    align-items: center;
                }}

                .param-label {{
                    font-size: 12px;
                    color: #cbd5e1;
                    font-weight: 500;
                    word-break: break-word;
                }}

                .param-input {{
                    background: rgba(0, 0, 0, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: #f1f5f9;
                    font-size: 12px;
                    font-family: 'Courier New', monospace;
                    transition: all 0.2s;
                }}

                .param-input:hover {{
                    border-color: rgba(255, 255, 255, 0.2);
                    background: rgba(0, 0, 0, 0.3);
                }}

                .param-input:focus {{
                    outline: none;
                    border-color: #3b82f6;
                    background: rgba(59, 130, 246, 0.1);
                    box-shadow: 0 0 8px rgba(59, 130, 246, 0.2);
                }}

                .actions {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                    margin-top: 16px;
                    padding-top: 16px;
                    border-top: 1px solid rgba(255, 255, 255, 0.1);
                }}

                button {{
                    padding: 10px 16px;
                    border: none;
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}

                .btn-primary {{
                    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                    color: white;
                    grid-column: 1 / -1;
                }}

                .btn-primary:hover {{
                    transform: translateY(-1px);
                    box-shadow: 0 8px 16px rgba(59, 130, 246, 0.3);
                }}

                .btn-primary:active {{
                    transform: translateY(0);
                }}

                .btn-secondary {{
                    background: rgba(107, 114, 128, 0.2);
                    color: #cbd5e1;
                    border: 1px solid rgba(107, 114, 128, 0.3);
                }}

                .btn-secondary:hover {{
                    background: rgba(107, 114, 128, 0.3);
                    border-color: rgba(107, 114, 128, 0.5);
                }}

                .btn-danger {{
                    background: rgba(239, 68, 68, 0.2);
                    color: #fca5a5;
                    border: 1px solid rgba(239, 68, 68, 0.3);
                }}

                .btn-danger:hover {{
                    background: rgba(239, 68, 68, 0.3);
                    border-color: rgba(239, 68, 68, 0.5);
                }}

                ::-webkit-scrollbar {{
                    width: 6px;
                }}

                ::-webkit-scrollbar-track {{
                    background: transparent;
                }}

                ::-webkit-scrollbar-thumb {{
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 3px;
                }}

                ::-webkit-scrollbar-thumb:hover {{
                    background: rgba(255, 255, 255, 0.2);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="device-title">{self.instrument['name']}</div>
                    <div class="device-info">
                        <span>Type: <strong>{self.instrument['type']}</strong></span>
                        <span>Dimensionality: <strong>{self.instrument['dimensionality']}</strong></span>
                        <span class="status-badge {'offline' if not self.instrument['connected'] else ''}">
                            {'Disconnected' if not self.instrument['connected'] else 'Connected'}
                        </span>
                    </div>
                </div>

                <div class="panel">
                    <div class="panel-title">📊 Parameters</div>
                    {param_controls}

                    <div class="actions">
                        <button class="btn-primary" onclick="startAcquisition()">{button_label}</button>
                        <button class="btn-secondary" onclick="stopAcquisition()">Stop</button>
                        <button class="btn-secondary" onclick="saveData()">💾 Save Data</button>
                        <button class="btn-danger" onclick="resetDevice()">⟲ Reset</button>
                    </div>
                </div>
            </div>

            <script>
                let instrumentBridge = null;

                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    instrumentBridge = channel.objects.instrumentBridge;
                    console.log('✅ Instrument bridge connected');
                }});

                function setParameter(name, value) {{
                    if (instrumentBridge) {{
                        instrumentBridge.setParameter(name, value);
                    }}
                }}

                function startAcquisition() {{
                    if (instrumentBridge) {{
                        console.log('Starting acquisition...');
                        instrumentBridge.startAcquisition();
                    }}
                }}

                function stopAcquisition() {{
                    if (instrumentBridge) {{
                        console.log('Stopping acquisition...');
                        instrumentBridge.stopAcquisition();
                    }}
                }}

                function saveData() {{
                    if (instrumentBridge) {{
                        console.log('Saving data...');
                        instrumentBridge.saveData();
                    }}
                }}

                function resetDevice() {{
                    if (confirm('Reset device to default state?')) {{
                        console.log('Resetting device...');
                        location.reload();
                    }}
                }}
            </script>
        </body>
        </html>
        """

    def setup_simulation(self):
        """Setup data simulation timer"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100)  # Update every 100ms

        self.time_data = []
        self.value_data = []
        self.t = 0

    def update_plot(self):
        """Update plot with simulated data"""
        if not hasattr(self.bridge, 'running') or not self.bridge.running:
            return

        # Generate simulation data based on instrument type
        if self.instrument["dimensionality"] == "1D":
            self.update_1d_plot()
        elif self.instrument["dimensionality"] == "2D":
            self.update_2d_plot()
        elif self.instrument["dimensionality"] == "0D":
            self.update_0d_plot()

    def update_1d_plot(self):
        """Update 1D plot (e.g., spectrum)"""
        params = self.instrument.get("parameters", {})

        try:
            if "Spectrometer" in self.instrument.get("type", ""):
                # Simulate spectrum
                wavelengths = np.linspace(
                    params.get("wavelength_min", params.get("wavelength", 400)),
                    params.get("wavelength_max", params.get("wavelength", 800) + 200),
                    1000
                )
                # Gaussian peak
                center = (wavelengths[0] + wavelengths[-1]) / 2
                spectrum = np.exp(-((wavelengths - center) ** 2) / (50 ** 2))
                spectrum += np.random.normal(0, 0.02, len(wavelengths))

                self.plot_widget.clear()
                self.plot_widget.plot(wavelengths, spectrum, pen='b')
            else:
                # Simulate position scan or other 1D data
                positions = np.linspace(0, 10, 100)
                signal = np.sin(positions) + np.random.normal(0, 0.1, len(positions))

                self.plot_widget.clear()
                self.plot_widget.plot(positions, signal, pen='r')
        except Exception as e:
            print(f"[HybridWindow] Error updating 1D plot: {e}")

    def update_2d_plot(self):
        """Update 2D plot (e.g., camera image)"""
        try:
            # Generate simulated 2D image
            size = 512
            x = np.linspace(-5, 5, size)
            y = np.linspace(-5, 5, size)
            X, Y = np.meshgrid(x, y)

            # Gaussian beam profile with noise
            image = np.exp(-(X**2 + Y**2) / 2)
            image += np.random.normal(0, 0.05, image.shape)
            image = np.clip(image, 0, 1)

            if isinstance(self.plot_widget, pg.ImageView):
                self.plot_widget.setImage(image, autoLevels=False)
            else:
                self.plot_widget.clear()
                self.plot_widget.imshow(image, cmap='viridis')
        except Exception as e:
            print(f"[HybridWindow] Error updating 2D plot: {e}")
        image += np.random.normal(0, 0.05, image.shape)

        self.plot_widget.setImage(image, autoRange=False, autoLevels=False, levels=(0, 1))

    def update_0d_plot(self):
        """Update 0D plot (e.g., time series)"""
        self.t += 0.1
        self.time_data.append(self.t)

        # Simulate noisy sine wave
        params = self.instrument["parameters"]
        freq = params.get("frequency", 1000) / 1000
        amplitude = params.get("amplitude", 1.0)

        value = amplitude * np.sin(2 * np.pi * freq * self.t)
        value += np.random.normal(0, 0.05)
        self.value_data.append(value)

        # Keep only last 100 points
        if len(self.time_data) > 100:
            self.time_data = self.time_data[-100:]
            self.value_data = self.value_data[-100:]

        self.plot_widget.clear()
        self.plot_widget.plot(self.time_data, self.value_data, pen='g')


def create_hybrid_instrument_window(instrument: dict) -> QMainWindow:
    """Factory function to create appropriate hybrid window"""
    return HybridInstrumentWindow(instrument)


# Required import
from PyQt6.QtCore import QObject, pyqtSlot
