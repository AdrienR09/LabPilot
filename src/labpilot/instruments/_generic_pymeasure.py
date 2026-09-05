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
import inspect
import re
from typing import Any

try:
    from pymeasure.instruments import Instrument
except ImportError:
    # pymeasure not installed - this adapter won't be available
    Instrument = None

if Instrument is not None:
    from labpilot.core.device.parameter import INTEGRATION_TIME, Parameter, ParamRole
    from labpilot.core.device.schema import DeviceSchema
    from labpilot.core.errors import NotConnectedError
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

    # --- Introspection of pymeasure's own property descriptors -----------
    #
    # `Instrument.control()` builds its getter and setter as closures whose
    # *default arguments* carry every fact the property was declared with —
    # the SCPI commands, the validator, the legal `values`, whether those
    # values are a map. Reading those defaults back (they are ordinary
    # function defaults, so `inspect.signature` sees them) turns the
    # declaration into a `Parameter` with real limits and choices.
    #
    # What this replaces was guesswork: every property was typed "float64"
    # regardless, units were scraped by taking whatever sat between the
    # first "(" and ")" anywhere in the docstring, and — the significant
    # one — a property was called settable whenever `attr.fset` was not
    # None. `fset` is *never* None for a pymeasure control: a read-only
    # measurement gets a setter closure whose `set_command` default is
    # None, and raises LookupError when called. So every one of the 183
    # generated adapters advertised each of its read-only measurements as a
    # writable setting, and the UI drew a control for it.

    def _descriptor_defaults(func: Any) -> dict[str, Any]:
        """Every declared fact a pymeasure accessor closure carries.

        `control()` passes some of them as default arguments (`values`,
        `validator`, `set_command`) and captures the rest as closure
        variables (`cast`, `separator`); both are read here, since which
        is which is an implementation detail of pymeasure's and has moved
        between releases.
        """
        if func is None:
            return {}
        facts: dict[str, Any] = {}
        for name, cell in zip(
            getattr(func.__code__, "co_freevars", ()), func.__closure__ or (), strict=False
        ):
            try:
                facts[name] = cell.cell_contents
            except ValueError:  # empty cell, still being defined
                continue
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return facts
        facts.update({
            name: parameter.default
            for name, parameter in signature.parameters.items()
            if parameter.default is not inspect.Parameter.empty
        })
        return facts

    # pymeasure validators that mean "values is a (min, max) range" vs
    # "values enumerates the legal settings". Matched by name because they
    # are plain module-level functions in pymeasure.instruments.validators
    # and stay identifiable through `functools.partial`-free composition.
    _RANGE_VALIDATORS = frozenset({
        "strict_range", "truncated_range", "modular_range",
        "modular_range_bidirectional",
    })
    _DISCRETE_VALIDATORS = frozenset({
        "strict_discrete_set", "truncated_discrete_set", "strict_discrete_range",
    })

    _DTYPE_BY_PYTHON_TYPE = {float: "f8", int: "i8", bool: "bool", str: "str"}

    # Unit words pymeasure docstrings actually use, mapped to symbols. A
    # closed vocabulary on purpose: the previous "text inside the first
    # parentheses" rule produced units like "float, strictly from -210 to
    # 210" and "V or A", which then rendered as axis labels.
    _UNIT_WORDS = {
        "volts": "V", "volt": "V", "millivolts": "mV", "microvolts": "µV",
        "amps": "A", "amperes": "A", "ampere": "A", "milliamps": "mA",
        "seconds": "s", "second": "s", "milliseconds": "ms",
        "microseconds": "µs", "nanoseconds": "ns",
        "hertz": "Hz", "hz": "Hz", "kilohertz": "kHz", "megahertz": "MHz",
        "ohms": "Ω", "ohm": "Ω", "watts": "W", "watt": "W",
        "degrees": "deg", "degree": "deg", "kelvin": "K", "celsius": "°C",
        "meters": "m", "metres": "m", "millimeters": "mm", "micrometers": "µm",
        "percent": "%", "decibels": "dB", "dbm": "dBm",
    }
    _UNIT_PATTERN = re.compile(r"\bin ([A-Za-zµΩ°%]+)\b")

    def _unit_from_doc(doc: str) -> str:
        """The physical unit a pymeasure docstring states, or "".

        Only the "... in <unit>" phrasing pymeasure's own style guide uses,
        and only for words in `_UNIT_WORDS` — an unrecognised word yields
        no unit rather than a wrong one.

        Every occurrence is tried, not just the first: a hyphen is a word
        boundary, so "the lock-in frequency in Hz" matches at "in
        frequency" before it reaches the real "in Hz".
        """
        for match in _UNIT_PATTERN.finditer(doc or ""):
            unit = _UNIT_WORDS.get(match.group(1).lower())
            if unit:
                return unit
        return ""

    def _dtype_for(values: Any, choices: tuple[Any, ...] | None, cast: Any) -> str:
        """Element dtype implied by a property's legal values.

        Takes the *values*' own types over `cast`, because `cast` describes
        how the instrument's reply string is parsed (it defaults to `float`
        even for a property whose legal settings are the strings 'current'
        and 'voltage') rather than what the property holds.
        """
        if choices:
            return _DTYPE_BY_PYTHON_TYPE.get(type(choices[0]), "str")
        if isinstance(cast, type):
            mapped = _DTYPE_BY_PYTHON_TYPE.get(cast)
            if mapped is not None:
                return mapped
        if isinstance(values, (list, tuple)) and values and all(
            isinstance(v, int) and not isinstance(v, bool) for v in values
        ):
            return "i8"
        return "f8"

    def _parameter_from_property(name: str, prop: Any) -> Parameter | None:
        """One `Parameter` describing a pymeasure property, or None if the
        attribute isn't a property at all."""
        fget = getattr(prop, "fget", None)
        fset = getattr(prop, "fset", None)
        if fget is None and fset is None:
            return None

        get_defaults = _descriptor_defaults(fget)
        set_defaults = _descriptor_defaults(fset)

        # A pymeasure control always has both closures; the *_command
        # defaults say which directions actually work. A plain Python
        # @property has neither key, and is readable/settable by whether
        # its accessors exist at all.
        if "get_command" in get_defaults:
            readable = get_defaults["get_command"] is not None
        else:
            readable = fget is not None
        if "set_command" in set_defaults:
            settable = set_defaults["set_command"] is not None
        else:
            settable = fset is not None

        if not readable and not settable:
            return None

        source = set_defaults or get_defaults
        values = source.get("values", ())
        validator_name = getattr(source.get("validator"), "__name__", "")

        limits: tuple[float | None, float | None] | None = None
        choices: tuple[Any, ...] | None = None

        if source.get("map_values") and isinstance(values, dict):
            # Mapped values: the dict keys are what a user sets, the
            # values are the instrument's wire encoding.
            choices = tuple(values.keys())
        elif validator_name in _DISCRETE_VALIDATORS and isinstance(
            values, (list, tuple, range)
        ):
            choices = tuple(values)
        elif validator_name in _RANGE_VALIDATORS and isinstance(
            values, (list, tuple, range)
        ) and len(values) == 2:
            try:
                limits = (float(values[0]), float(values[1]))
            except (TypeError, ValueError):
                limits = None
        elif source.get("map_values") and isinstance(values, (list, tuple, range)):
            choices = tuple(values)

        # A mapped discrete set can be large (SR830's sensitivity has 27
        # entries); that is fine for a combo box but not as a limits pair,
        # so choices and limits stay mutually exclusive above.
        if choices is not None and not choices:
            choices = None

        doc = inspect.getdoc(prop) or ""
        dtype = _dtype_for(values, choices, get_defaults.get("cast"))
        unit = _unit_from_doc(doc)

        tags = set()
        if settable and ("integration_time" in name or "exposure" in name):
            tags.add(INTEGRATION_TIME)

        return Parameter(
            name=name,
            dtype=dtype,
            unit=unit,
            role=ParamRole.SETTING if settable else ParamRole.VALUE,
            readable=readable,
            settable=settable,
            limits=limits,
            choices=choices,
            tags=frozenset(tags),
            description=doc.strip().split("\n")[0][:200],
        )

    def introspect_parameters(cls: type) -> tuple[Parameter, ...]:
        """Every `Parameter` a pymeasure Instrument class declares."""
        parameters: list[Parameter] = []
        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue
            try:
                attr = inspect.getattr_static(cls, attr_name)
            except AttributeError:
                continue
            if attr is None:
                continue
            try:
                parameter = _parameter_from_property(attr_name, attr)
            except Exception:
                # One malformed property must not cost the whole
                # instrument its schema.
                continue
            if parameter is not None:
                parameters.append(parameter)
        return tuple(parameters)

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

            self._schema = DeviceSchema(
                name=self._name,
                kind=_kind_for_pymeasure_class(cls.__name__),
                parameters=introspect_parameters(cls),
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
                raise NotConnectedError(
                    f"{self._name} is not connected", device=self._name
                )

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
            """Set one or more already-validated properties on the wrapped
            instrument. Assignment goes straight to the pymeasure property,
            whose own validator is the final authority — this adapter's
            introspected limits mirror that validator, so a value rejected
            here would have been rejected there too, just later and with a
            message naming a SCPI command instead of a parameter."""
            if self._instrument is None:
                raise NotConnectedError(
                    f"{self._name} is not connected", device=self._name
                )
            for name, value in values.items():
                setattr(self._instrument, name, value)

        async def write(self, values: dict[str, Any]) -> None:
            """Set one or more settable properties (async wrapper).

            Overrides the base `set_<key>` dispatch — a pymeasure
            instrument's settings are properties, not methods — so it calls
            `validate_write()` explicitly, which is what the base class
            would otherwise have done.
            """
            await self._to_thread(self._write_sync, self.validate_write(values))

        def _self_test_sync(self) -> None:
            """Test instrument connectivity.

            Most pymeasure instruments have an 'id' property we can read.
            """
            if self._instrument is None:
                raise NotConnectedError(
                    f"{self._name} is not connected", device=self._name
                )

            # Try to read ID
            try:
                _ = self._instrument.id
            except AttributeError:
                # No id property - just do a regular read
                self._read_sync()

    # Register in global registry
    adapter_registry.register("pymeasure_generic", PyMeasureGenericAdapter)
