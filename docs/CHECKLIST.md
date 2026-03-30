# LabPilot Usage Checklist

## ✅ Installation Complete
- [x] Package installed (`pip install -e .`)
- [x] Dependencies resolved (anyio, pydantic, numpy, xarray, h5py, aiosqlite)
- [x] Examples tested successfully

---

## 🎯 Quick Start Checklist

### Day 1: Get Familiar
- [ ] Read `QUICK_START.md`
- [ ] Run `python examples/simple_scan.py` (already done ✓)
- [ ] Run `python my_first_scan.py`
- [ ] Run `python advanced_example.py` (already done ✓)
- [ ] Examine generated files:
  - [ ] `data/advanced_scan.h5` (HDF5 data)
  - [ ] `data/catalogue.db` (SQLite metadata)
  - [ ] `my_custom_scan.toml` (TOML plan)

### Day 2: Add Your Hardware
- [ ] Identify your instruments (motor, detector, etc.)
- [ ] Find communication protocol:
  - [ ] Serial? → Use `SerialDriver` base
  - [ ] VISA? → Use `VISADriver` base
  - [ ] NI-DAQ? → Use `NIAnalogInput`/`NIAnalogOutput`
- [ ] Copy `labpilot/drivers/custom/my_motor.py` as template
- [ ] Edit commands for YOUR instrument protocol
- [ ] Test with `driver.self_test()`

### Day 3: First Real Scan
- [ ] Edit `my_first_scan.py`:
  - [ ] Import your custom driver
  - [ ] Replace mock devices with real ones
  - [ ] Update device names in plan
  - [ ] Set correct start/stop/num values
  - [ ] Add metadata (sample name, user, etc.)
- [ ] Test connection (without scan first)
- [ ] Run scan
- [ ] Verify data saved correctly

### Week 1: Build Your Workflow
- [ ] Add second device driver (if needed)
- [ ] Test 2D grid scan (if applicable)
- [ ] Set up automatic data storage
- [ ] Create analysis scripts for HDF5 files
- [ ] Share TOML plans with team members

---

## 📋 Device Driver Checklist

When creating a new driver, implement:

### Required Methods
- [ ] `__init__(self, ...)` - Constructor with connection params
- [ ] `async def connect(self) -> None` - Open connection
- [ ] `async def disconnect(self) -> None` - Close connection
- [ ] `async def stage(self) -> None` - Pre-scan setup
- [ ] `async def unstage(self) -> None` - Post-scan cleanup
- [ ] `async def read(self) -> dict` - Get current values
- [ ] `async def self_test(self) -> bool` - Test communication

### For Movable Devices (motors)
- [ ] `async def set(self, value, *, timeout=10.0) -> None`
- [ ] `async def stop(self) -> None`
- [ ] `async def where(self) -> float`

### For Triggerable Devices (cameras)
- [ ] `async def trigger(self) -> None`
- [ ] `async def arm(self, mode: str) -> None`

### Device Schema
- [ ] `schema = DeviceSchema(...)` with:
  - [ ] `name` - Unique identifier
  - [ ] `kind` - "motor", "detector", "source", etc.
  - [ ] `readable` - Dict of readable axes + dtypes
  - [ ] `settable` - Dict of settable params + dtypes
  - [ ] `units` - Physical units
  - [ ] `limits` - Min/max bounds
  - [ ] `trigger_modes` - Supported modes
  - [ ] `tags` - Searchable tags

---

## 🧪 Testing Checklist

### Before Deployment
- [ ] Run unit tests: `pytest tests/`
- [ ] Test with mock devices (no hardware)
- [ ] Test with real hardware
- [ ] Verify FSM transitions work
- [ ] Test error handling (disconnect during scan)
- [ ] Test pause/resume (if needed)
- [ ] Verify data storage (HDF5 + catalogue)

### Integration Tests
- [ ] Scan completes successfully
- [ ] Data saved to HDF5 correctly
- [ ] Metadata indexed in catalogue
- [ ] TOML plan saves/loads correctly
- [ ] Event bus handles multiple subscribers
- [ ] Devices unstage on error

---

## 📊 Data Management Checklist

### Setup
- [ ] Create `data/` directory structure
- [ ] Choose HDF5 naming convention (date, run number, etc.)
- [ ] Set up catalogue database
- [ ] Define metadata fields (sample, user, temperature, etc.)

### During Scans
- [ ] HDF5Writer subscribed to bus
- [ ] Data flushed periodically
- [ ] Catalogue updated after each run
- [ ] Plans saved to TOML

### Analysis
- [ ] Scripts to read HDF5 files
- [ ] Query catalogue by metadata
- [ ] Export to other formats if needed
- [ ] Backup critical data

---

## 🎨 GUI Development Checklist (Future)

If building a GUI:
- [ ] Subscribe to `session.bus` for live updates
- [ ] Listen to `EventKind.READING` for live plots
- [ ] Listen to `EventKind.PROGRESS` for progress bar
- [ ] Listen to `EventKind.STATE_CHANGE` for status
- [ ] Button to start/pause/stop scans
- [ ] Display current device positions
- [ ] Show scan plan parameters
- [ ] Live matplotlib/plotly plots

---

## 🐛 Troubleshooting Checklist

### Import Errors
- [ ] Check dependencies: `pip list | grep labpilot`
- [ ] Reinstall: `pip install -e .`
- [ ] Check Python version: `python --version` (need ≥3.11)

### Hardware Not Found
- [ ] Check port/address: `ls /dev/tty*` or Device Manager
- [ ] Verify permissions: `sudo usermod -a -G dialout $USER`
- [ ] Test with manufacturer software first
- [ ] Check driver timeout settings
- [ ] Run `driver.self_test()`

### Scan Fails
- [ ] Check FSM state: `session.state`
- [ ] Verify device registered: `session.devices.keys()`
- [ ] Check device names match plan
- [ ] Test device.read() independently
- [ ] Check limits in DeviceSchema
- [ ] Look at error traceback in ERROR event

### Data Storage Issues
- [ ] Check disk space
- [ ] Verify write permissions on `data/`
- [ ] Check HDF5 file opens: `h5py.File('data/scan.h5')`
- [ ] Check catalogue DB: `sqlite3 data/catalogue.db`

---

## 📚 Learning Resources

### Framework Concepts
- [ ] Read README.md architecture section
- [ ] Study event system in `test_events.py`
- [ ] Understand FSM in `test_fsm.py`
- [ ] Review scan patterns in `test_scan.py`

### Examples to Study
- [ ] `examples/simple_scan.py` - Basic pattern
- [ ] `my_first_scan.py` - Customizable template
- [ ] `advanced_example.py` - Parallel subscribers
- [ ] `labpilot/drivers/visa/ocean_insight.py` - Full driver
- [ ] `labpilot/drivers/ni/daq.py` - NI-DAQmx async
- [ ] `labpilot/plans/scan.py` - Scan generators

---

## 🚀 Production Deployment Checklist

### Code Quality
- [ ] All functions have type hints
- [ ] All public APIs have docstrings
- [ ] Run `ruff check .` (no errors)
- [ ] Run `pytest` (all pass)
- [ ] Test edge cases (device disconnect, timeout, etc.)

### Documentation
- [ ] Driver documentation updated
- [ ] Metadata fields documented
- [ ] Example scan scripts provided
- [ ] Troubleshooting guide written

### Safety
- [ ] Hardware limits enforced in schema
- [ ] Emergency stop implemented
- [ ] Safe defaults for all drivers
- [ ] Unstage always runs (even on error)
- [ ] No blocking operations in async code

---

## ✨ Next Features to Add

### Short Term
- [ ] Live plotting with matplotlib
- [ ] More hardware drivers
- [ ] Adaptive scan patterns
- [ ] Scan queue management

### Medium Term
- [ ] Web-based GUI (React + FastAPI)
- [ ] ZMQ bridge for remote monitoring
- [ ] Real-time data analysis pipeline
- [ ] Simulation mode for testing

### Long Term
- [ ] Bayesian optimization
- [ ] Machine learning integration
- [ ] Distributed scanning (multiple instruments)
- [ ] Cloud storage integration

---

**Current Status**: ✅ Framework complete and ready for customization!

**Next Action**: Edit `my_first_scan.py` with your hardware details.
