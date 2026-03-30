# LabPilot Qt Frontend

**Professional Scientific Instrument Control Interface**

A desktop Qt application with pyqtgraph integration for professional laboratory automation and instrument control.

## 🎯 Features

### Professional Scientific Interface
- **Dark theme** optimized for laboratory environments
- **Native desktop performance** with Qt6
- **Advanced scientific plotting** with pyqtgraph
- **Professional layout** matching qudi and pyMoDAQ standards

### Instrument Control Windows
Each instrument type has a dedicated, full-window control interface:

#### 0D Detectors (Qudi Time Trace Style)
- Large counter display in top toolbar
- Full-window time trace with pyqtgraph
- Recording control with start/stop
- Professional spinbox for integration time
- Real-time data simulation

#### 1D Detectors (PyMoDAQ Spectrometer Style)
- Full-screen spectrum plotting
- Realistic multi-peak spectroscopy simulation
- Collapsible settings panel
- Live acquisition with professional controls

#### 2D Detectors (Camera Control)
- Full-window image display with pyqtgraph ImageView
- Viridis colormap and professional controls
- Variable resolution settings
- Live preview mode

#### Motor Control
- **0D Motors**: State switches (OFF/ON/STANDBY/LOCKED)
- **1D Motors**: Position control with real-time slider
- **Multi-axis Motors**: Grid of axis cards with individual controls

### Advanced PyQtGraph Features
- **Professional zoom/pan** with mouse controls
- **Right-click context menus** for plot settings
- **Crosshair tracking** for precise measurements
- **Grid toggles** and axis scaling
- **Scientific axis labels** with units
- **Fill-under-curve** visualizations

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- PyQt6 and pyqtgraph (auto-installed)

### Launch (Automatic Setup)

**Linux/macOS:**
```bash
./launch.sh
```

**Windows:**
```cmd
launch.bat
```

The launcher will automatically:
1. Create a Python virtual environment
2. Install all dependencies
3. Launch the application

### Manual Installation
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/mac
# or
venv\Scripts\activate.bat  # Windows

# Install dependencies
pip install -r requirements.txt

# Launch application
python main.py
```

## 📱 Interface Overview

### Main Dashboard
- **Instrument List**: Left panel showing all available instruments
- **Connection Status**: Real-time connection indicators
- **System Status**: Backend and AI availability
- **Professional Layout**: Resizable panes with splitters

### Opening Instrument Windows
1. Select an instrument from the list
2. Click **"Open UI"** button
3. Independent window opens with full instrument control
4. Multiple instruments can be controlled simultaneously

### Each Instrument Window Features:
- **Full-screen interface** optimized for data visualization
- **Professional toolbars** with integration time, exposure settings
- **Status bars** showing real-time information
- **Settings panels** for advanced configuration
- **Native desktop performance** with hardware acceleration

## 🔬 Supported Instruments

### Detectors
- **0D**: PMT detectors, photodiodes, counters
- **1D**: Spectrometers, linear detectors, gratings
- **2D**: CCD cameras, CMOS sensors, imaging arrays

### Motors & Actuators
- **0D**: Switches, relays, binary actuators
- **1D**: Linear stages, rotation mounts, single-axis
- **Multi-axis**: XY stages, 3D positioners, multi-axis systems

## 🎨 Professional Design

### Dark Scientific Theme
- **Color scheme** optimized for laboratory environments
- **High contrast** for better readability in dim conditions
- **Professional appearance** matching established scientific software

### PyQtGraph Integration
- **Hardware-accelerated** plotting for smooth real-time data
- **Scientific features** like crosshairs, grid controls, zoom/pan
- **Right-click menus** for advanced plot configuration
- **Auto-scaling** and manual axis control
- **Professional colormaps** (viridis, plasma, grayscale)

### Layout Philosophy
- **Maximum space** dedicated to data visualization
- **Minimal UI clutter** - controls only when needed
- **Professional spinboxes** with scientific notation
- **Icon-based controls** for common operations
- **Collapsible panels** to hide advanced settings

## 🔧 Technical Details

### Architecture
- **PyQt6** for native desktop UI
- **pyqtgraph** for scientific plotting
- **NumPy** for data handling and simulation
- **Requests** for backend API communication
- **Modular design** for easy extension

### Performance
- **Hardware acceleration** with OpenGL support
- **Efficient data structures** for real-time plotting
- **Threading support** for non-blocking operations
- **Memory management** for long-running acquisitions

### Data Simulation
Each instrument includes realistic data simulation:
- **0D**: Poisson noise + exponential components
- **1D**: Multi-peak spectra with realistic noise
- **2D**: Gaussian features + interference patterns
- **Motors**: Smooth motion simulation with timing

## 📊 Comparison with Web Interface

| Feature | Qt Frontend | Web Frontend |
|---------|-------------|--------------|
| Performance | Native desktop | Browser-limited |
| Plotting | pyqtgraph (professional) | Canvas-based |
| Right-click menus | Full context menus | Limited |
| Hardware acceleration | OpenGL support | WebGL limited |
| Multiple windows | Native OS windows | Browser tabs |
| Offline capability | Full offline | Requires server |
| Installation | Desktop app | Web browser |
| Updates | Manual install | Automatic |

## 🌟 Key Advantages

1. **Professional Scientific Interface** - Matches qudi/pyMoDAQ standards
2. **Native Desktop Performance** - No browser limitations
3. **Advanced PyQtGraph Features** - Professional plotting capabilities
4. **Hardware Acceleration** - Smooth real-time data visualization
5. **Independent Windows** - True multi-instrument control
6. **Offline Operation** - No web server dependency
7. **Scientific Colormaps** - Professional data visualization
8. **Right-click Context Menus** - Advanced plot controls

## 🔗 Backend Integration

The Qt frontend communicates with the same LabPilot backend API:
- **REST API** endpoints for instrument discovery
- **Mock data** for development and testing
- **Real instruments** when backend is connected
- **Automatic fallback** to simulation mode

## 🚀 Getting Started

1. **Launch the application** using the provided launcher scripts
2. **Browse instruments** in the left panel
3. **Click "Open UI"** for any instrument to launch its control window
4. **Use professional plotting controls** with right-click menus
5. **Adjust settings** via collapsible panels
6. **Control multiple instruments** simultaneously

The Qt frontend provides a professional, desktop-native interface optimized for scientific instrument control and data visualization! 🔬✨