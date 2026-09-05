"""Generic PyMeasure adapter - wraps ANY pymeasure instrument.

This adapter uses introspection to auto-build a DeviceSchema from pymeasure
Instrument properties and provides async wrapper methods via anyio.

Usage in lab_config.toml:
    [[devices]]
    name = "lockin"
    adapter = "pymeasure_generic"
    instrument_class = "pymeasure.instruments.srs.SR830"
    resource = "GPIB::8"

The adapter will:
1. Import the instrument class dynamically
2. Introspect its pymeasure properties
3. Generate a DeviceSchema automatically
4. Wrap all methods with anyio.to_thread.run_sync()
"""

from __future__ import annotations

import importlib
from typing import Any

try:
    from pymeasure.instruments import Instrument
except ImportError:
    # pymeasure not installed - this adapter won't be available
    Instrument = None

if Instrument is not None:
    from labpilot.core.device.schema import DeviceSchema
    from labpilot.instruments._base import AdapterBase, adapter_registry
    from labpilot.instruments.catalog import (
        INSTRUMENT_CATALOG,
        InstrumentBackend,
        InstrumentType,
    )

    # DeviceSchema.kind is the flat Literal["detector","motor","source","counter","generic"]
    # (see core/device/schema.py) — coarser than catalog.InstrumentType. Map down to it
    # so live instruments report something more useful than an unconditional "generic".
    _CATALOG_TYPE_TO_KIND = {
        InstrumentType.DETECTOR_0D: "detector",
        InstrumentType.DETECTOR_1D: "detector",
        InstrumentType.DETECTOR_2D: "detector",
        InstrumentType.ACTUATOR_0D: "motor",
        InstrumentType.ACTUATOR_1D: "motor",
        InstrumentType.ACTUATOR_ND: "motor",
        InstrumentType.SOURCE: "source",
        InstrumentType.GENERIC: "generic",
    }

    def _kind_for_pymeasure_class(cls_name: str) -> str:
        """Look up the catalog's classification for this pymeasure class and
        map it down to a DeviceSchema.kind. Falls back to "generic" only if
        the class truly isn't catalogued."""
        for entry in INSTRUMENT_CATALOG:
            if entry.backend == InstrumentBackend.PYMEASURE and entry.model == cls_name:
                return _CATALOG_TYPE_TO_KIND.get(entry.instrument_type, "generic")
        return "generic"

    class PyMeasureGenericAdapter(AdapterBase):
        """Generic adapter for any pymeasure Instrument.

        Dynamically wraps pymeasure instruments without needing typed adapters.
        Introspects pymeasure Instrument properties to build DeviceSchema.

        Args:
            instrument_class: Dotted import path (str) or class itself.
                             Examples: "pymeasure.instruments.srs.SR830"
                                      "pymeasure.instruments.keithley.Keithley2400"
            resource: VISA resource string (e.g., "GPIB::24", "USB0::0x1234::...")
            **kwargs: Additional kwargs passed to instrument constructor.

        Example:
            >>> adapter = PyMeasureGenericAdapter(
            ...     instrument_class="pymeasure.instruments.srs.SR830",
            ...     resource="GPIB::8"
            ... )
            >>> await adapter.connect()
            >>> data = await adapter.read()
            >>> print(data)  # {"x": 1.23, "y": 4.56, "phase": 45.6, ...}
        """

        def __init__(
            self,
            instrument_class: str | type[Instrument],
            resource: str,
            name: str | None = None,
            **kwargs: Any,
        ) -> None:
            """Initialize generic adapter.

            Args:
                instrument_class: Dotted path or class.
                resource: VISA resource string.
                name: Optional custom name (auto-generated if not provided).
                **kwargs: Passed to pymeasure Instrument constructor.
            """
            super().__init__()
            self._instrument_class = instrument_class
            self._resource = resource
            self._kwargs = kwargs
            self._instrument: Instrument | None = None
            self._name = name
            self._schema: DeviceSchema | None = None

        @property
        def schema(self) -> DeviceSchema:
            """Generate schema from pymeasure Instrument properties.

            Introspects the instrument class to find all pymeasure properties
            (measurable values) and builds a DeviceSchema.

            Returns:
                DeviceSchema with auto-detected readable axes.
            """
            if self._schema is not None:
                return self._schema

            # Import instrument class if string
            if isinstance(self._instrument_class, str):
                module_path, class_name = self._instrument_class.rsplit(".", 1)
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
            else:
                cls = self._instrument_class

            # Auto-generate name from class if not provided
            if self._name is None:
                self._name = f"pymeasure_{cls.__name__.lower()}"

            # Introspect pymeasure properties
            readable = {}
            settable = {}
            units = {}

            # Get all class attributes that are pymeasure properties
            for attr_name in dir(cls):
                attr = getattr(cls, attr_name, None)
                if attr is None or attr_name.startswith("_"):
                    continue

                # Check if it's a pymeasure property (has fget/fset)
                if hasattr(attr, "fget"):
                    # Readable property
                    readable[attr_name] = "float64"  # Default type

                    # Check if settable
                    if hasattr(attr, "fset") and attr.fset is not None:
                        settable[attr_name] = "float64"

                    # Try to extract units from docstring
                    doc = attr.__doc__ or ""
                    if "(" in doc and ")" in doc:
                        # Extract units from docstring like "Voltage (V)"
                        unit_start = doc.find("(")
                        unit_end = doc.find(")", unit_start)
                        unit = doc[unit_start + 1 : unit_end].strip()
                        if unit and len(unit) < 10:  # Sanity check
                            units[attr_name] = unit

            # Build schema
            self._schema = DeviceSchema(
                name=self._name,
                kind=_kind_for_pymeasure_class(cls.__name__),
                readable=readable,
                settable=settable,
                units=units,
                tags=[
                    "PyMeasure",
                    cls.__name__,
                    "VISA",  # Most pymeasure instruments use VISA
                ],
            )

            return self._schema

        def _connect_sync(self) -> None:
            """Connect to instrument via VISA."""
            # Import instrument class if needed
            if isinstance(self._instrument_class, str):
                module_path, class_name = self._instrument_class.rsplit(".", 1)
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
            else:
                cls = self._instrument_class

            # Instantiate pymeasure instrument
            self._instrument = cls(self._resource, **self._kwargs)

        def _disconnect_sync(self) -> None:
            """Disconnect from instrument."""
            if self._instrument is not None:
                try:
                    self._instrument.shutdown()
                except Exception:
                    pass  # Ignore errors during shutdown
                self._instrument = None

        def _read_sync(self) -> dict[str, Any]:
            """Read all readable properties.

            Returns:
                Dict mapping property names to values.
            """
            if self._instrument is None:
                raise RuntimeError("Adapter not connected")

            data = {}
            for axis_name in self.schema.readable.keys():
                try:
                    value = getattr(self._instrument, axis_name)
                    data[axis_name] = value
                except Exception as e:
                    # Skip properties that error on read
                    print(f"Warning: Failed to read {axis_name}: {e}")

            return data

        def _write_sync(self, values: dict[str, Any]) -> None:
            """Set one or more settable properties on the wrapped instrument."""
            if self._instrument is None:
                raise RuntimeError("Adapter not connected")

            settable = self.schema.settable
            for name, value in values.items():
                if name not in settable:
                    raise ValueError(f"{name!r} is not settable on this instrument")
                setattr(self._instrument, name, value)

        async def write(self, values: dict[str, Any]) -> None:
            """Set one or more settable properties (async wrapper)."""
            await self._to_thread(self._write_sync, values)

        def _self_test_sync(self) -> None:
            """Test instrument connectivity.

            Most pymeasure instruments have an 'id' property we can read.
            """
            if self._instrument is None:
                raise RuntimeError("Adapter not connected")

            # Try to read ID
            try:
                _ = self._instrument.id
            except AttributeError:
                # No id property - just do a regular read
                self._read_sync()

    # Register in global registry
    adapter_registry.register("pymeasure_generic", PyMeasureGenericAdapter)
