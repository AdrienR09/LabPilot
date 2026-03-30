# LabPilot Quick Reference Guide

## 🚀 Getting Started (3 steps)

### 1. Installation
```bash
cd /Users/adrien/Documents/Qudi
pip install -e .                    # Core only
pip install -e ".[visa]"            # + VISA instruments
pip install -e ".[ni]"              # + NI-DAQmx
pip install -e ".[serial]"          # + Serial devices
pip install -e ".[all-drivers]"     # Everything
```

### 2. Run Example
```bash
python examples/simple_scan.py      # Basic scan with mock devices
python my_first_scan.py             # Your customizable template
python advanced_example.py          # With data storage
```

### 3. View Data
```bash
# HDF5 files
python -c "import h5py; f = h5py.File('data/advanced_scan.h5'); print(list(f.keys()))"

# SQLite catalogue
sqlite3 data/catalogue.db "SELECT run_uid, plan_name FROM runs;"
```

---

## 📝 Basic Scan Pattern

```python
import anyio
from labpilot import Session
from labpilot.plans import ScanPlan
from labpilot.plans.scan import scan

async def main():
    # 1. Create session
    session = Session()

    # 2. Connect hardware
    motor = YourMotorDriver(port="/dev/ttyUSB0")
    detector = YourDetectorDriver(resource="USB0::...")
    await motor.connect()
    await detector.connect()

    # 3. Register devices
    session.register(motor)
    session.register(detector)

    # 4. Create plan
    plan = ScanPlan(
        name="my_scan",
        motor="motor_name",      # Must match motor.schema.name
        detector="detector_name", # Must match detector.schema.name
        start=0.0,
        stop=100.0,
        num=50,
        dwell=0.1,
        metadata={"sample": "test"}
    )

    # 5. Run scan
    async for event in scan(plan, motor, detector, session.bus):
        if event.kind == EventKind.READING:
            print(event.data)

    # 6. Cleanup
    await motor.disconnect()
    await detector.disconnect()

anyio.run(main)
```

---

## 🔧 Creating a Custom Driver

### For Serial Devices
```python
from labpilot.drivers.serial._base import SerialDriver
from labpilot.device.schema import DeviceSchema

class MyMotor(SerialDriver):
    schema = DeviceSchema(
        name="my_motor",
        kind="motor",
        readable={"position": "float64"},
        settable={"position": "float64"},
        units={"position": "mm"},
        limits={"position": (-10.0, 10.0)},
        trigger_modes=["software"],
        tags=["serial", "custom"],
    )

    async def connect(self) -> None:
        await super().connect()
        # Your init commands

    async def stage(self) -> None:
        # Setup before scan
        pass

    async def unstage(self) -> None:
        # Cleanup after scan
        pass

    async def set(self, value: float, *, timeout: float = 10.0) -> None:
        # Move to position
        await self._write(f"MOVE {value}\n".encode())
        # Wait for completion

    async def where(self) -> float:
        # Read position
        await self._write(b"POS?\n")
        response = await self._readline()
        return float(response)

    async def read(self) -> dict:
        return {"position": await self.where()}

    async def stop(self) -> None:
        await self._write(b"STOP\n")
```

### For VISA Devices
```python
from labpilot.drivers.visa._base import VISADriver

class MySpectrometer(VISADriver):
    schema = DeviceSchema(
        name="my_spec",
        kind="detector",
        readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
        ...
    )

    async def read(self) -> dict:
        # Query spectrum
        data = await self._query("READ?")
        # Parse and return
        return {"wavelengths": wl, "intensities": intensities}
```

---

## 📊 Event Types

```python
from labpilot.core.events import EventKind

EventKind.DESCRIPTOR   # Scan metadata (emitted once at start)
EventKind.READING      # Data point (emitted per position)
EventKind.PROGRESS     # Progress update (fraction + ETA)
EventKind.WARNING      # Non-fatal warning
EventKind.ERROR        # Fatal error
EventKind.STOP         # Scan finished cleanly
EventKind.STATE_CHANGE # FSM state transition
```

---

## 🎯 Common Tasks

### Save/Load Plans
```python
# Save
plan.to_toml("my_scan.toml")

# Load
plan = ScanPlan.from_toml("my_scan.toml")
```

### Parallel Event Subscribers
```python
# Subscribe to specific events
async for event in session.bus.subscribe(EventKind.READING, EventKind.PROGRESS):
    if event.kind == EventKind.READING:
        # Process data
        pass
```

### Data Storage
```python
from labpilot.storage.hdf5 import HDF5Writer
from labpilot.storage.catalogue import Catalogue

# Start HDF5 writer
writer = HDF5Writer("data/scan.h5")
await writer.start(session.bus)

# Run scan...

# Stop writer
await writer.stop()

# Index in catalogue
catalogue = Catalogue("data/catalogue.db")
await catalogue.connect()
await catalogue.add_run(run_uid, "scan_name", metadata)
```

### Search Catalogue
```python
# Search by metadata
results = await catalogue.search(
    plan_name="wavelength_scan",
    start_time=time.time() - 86400,  # Last 24 hours
    sample="fiber_01"  # Custom metadata fields
)

for result in results:
    print(result["run_uid"], result["metadata"])
```

---

## 🔍 Available Scan Types

```python
from labpilot.plans.scan import scan, grid_scan, time_scan

# 1D scan
async for event in scan(plan, motor, detector, bus):
    pass

# 2D grid scan (snake pattern)
async for event in grid_scan(
    motor_x, motor_y, detector,
    x_start=0, x_stop=10, x_num=20,
    y_start=0, y_stop=10, y_num=20,
    dwell=0.1, bus=bus
):
    pass

# Time series (fixed interval)
async for event in time_scan(
    detector,
    duration=60.0,   # 60 seconds
    interval=0.5,    # Sample every 0.5s
    bus=bus
):
    pass
```

---

## 🐛 Troubleshooting

### Import errors
```bash
# Missing dependencies
pip install -e ".[all-drivers]"

# Check installation
python -c "import labpilot; print(labpilot.__version__)"
```

### Hardware not found
```python
# Test driver connectivity
if await motor.self_test():
    print("✓ Connected")
else:
    print("✗ Not found")
```

### View scan data
```python
import h5py
import numpy as np

with h5py.File("data/scan.h5", "r") as f:
    run_uid = list(f.keys())[0]
    positions = f[run_uid]["data"]["motor_position"][:]
    intensities = f[run_uid]["data"]["intensity"][:]

    import matplotlib.pyplot as plt
    plt.plot(positions, intensities)
    plt.show()
```

---

## 📚 File Locations

- **Your scans**: `my_first_scan.py`, `advanced_example.py`
- **Custom drivers**: `labpilot/drivers/custom/my_motor.py`
- **Examples**: `examples/simple_scan.py`
- **Tests**: `pytest tests/`
- **Data**: `data/*.h5`, `data/catalogue.db`
- **Plans**: `*.toml` files

---

## 🎨 Next Steps

1. **Replace mock devices** with your real hardware
2. **Add custom drivers** in `labpilot/drivers/custom/`
3. **Build a GUI** that subscribes to `session.bus`
4. **Add live plotting** with matplotlib
5. **Run tests**: `pytest tests/`
6. **Share plans** via TOML files with collaborators

---

## 💡 Tips

- ✅ Always use `async/await` for hardware I/O
- ✅ Test drivers with `self_test()` before scans
- ✅ Save plans to TOML for reproducibility
- ✅ Use EventBus for parallel data consumers
- ✅ Check FSM state before operations
- ✅ Handle errors in scan try/except blocks
- ✅ Use `anyio.sleep()` not `time.sleep()`

---

## 📖 Full Documentation

See `README.md` for complete documentation and architecture details.
