# Instruments

The instrument adapter library. `adapter_registry` (in `_base.py`, populated by auto-discovery in `__init__.py`) is the source of truth for what's connectable; `catalog.py` adds the manufacturer/model/dimensionality metadata the UI needs to pick a window layout per instrument.

## Layout

```
instruments/
    _base.py                  AdapterBase, adapter_registry
    _generic_pymeasure.py     PyMeasureGenericAdapter — introspection-based wrapper for ANY pymeasure instrument
    catalog.py                INSTRUMENT_CATALOG + lookup helpers
    mock/                     36 simulated instruments, for development without hardware
    test_fixtures.py          9 high-fidelity simulations (used by the demo dashboard)
    <Manufacturer>/
        <type>.py             one file per (manufacturer, instrument type) — detector_0d.py, source.py, etc.
```

Organized by **manufacturer**, then **instrument type** — not by which library backs the adapter. A manufacturer folder can contain files backed by different libraries (e.g. `Thorlabs/detector_0d.py` wraps a PyMeasure class, `Thorlabs/detector_2d.py` wraps pylablib cameras); that's an implementation detail inside each file, not part of the folder structure.

`<type>` matches `catalog.InstrumentType`: `detector_0d`, `detector_1d`, `detector_2d`, `actuator_0d`, `actuator_1d`, `actuator_nd`, `source`, or `generic` (doesn't fit the taxonomy cleanly).

## Coverage

- **Mock (36)** — hand-written simulated devices, no external dependency.
- **Test fixtures (9)** — higher-fidelity simulations with realistic data generation.
- **PyMeasure (188)** — 6 dedicated adapters with hand-written schemas (Keithley 2400/2600/6221, SRS SR830/860, Thorlabs PM100), plus 182 auto-generated thin wrappers around `PyMeasureGenericAdapter`, covering every real instrument class in the installed pymeasure library (introspected, not guessed — see `_generic_pymeasure.py`'s docstring for how the wrapping works). Their `instrument_type` classification is a best-effort heuristic from the class name; treat `generic`-typed entries as unverified.
- **pylablib (25)** — dedicated adapters for cameras (Andor, Basler, Hamamatsu, PCO, Photometrics, Princeton, Thorlabs), lasers (M Squared, Laser Quantum, Toptica), stages (Attocube, Newport, PI, Thorlabs), and sensors (Ophir, Thorlabs, Pfeiffer, HighFinesse, Lakeshore).

**Not covered**: plugin-discovered instrument frameworks, where instruments are plugins discovered through the framework's own plugin-manager mechanism (`daq_move_plugins`/`daq_0Dviewer_plugins`/etc.), not a flat instrument-class list like pymeasure — integrating one means writing a new discovery backend, not just more adapter files. Flagging this as unstarted rather than attempting a partial/rushed integration.

## Adding an instrument

```python
from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema

class MyInstrumentAdapter(AdapterBase):
    @property
    def schema(self) -> DeviceSchema: ...
    def _connect_sync(self) -> None: ...
    def _disconnect_sync(self) -> None: ...
    def _read_sync(self) -> dict: ...

adapter_registry.register("my_instrument_key", MyInstrumentAdapter)
```

Then add a matching `InstrumentMetadata` entry to `catalog.py`. The catalog only lists keys that exist in `adapter_registry` — don't add speculative entries; `python -c "from instruments import adapter_registry; print(sorted(adapter_registry.list()))"` shows what's real.
