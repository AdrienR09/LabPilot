"""`Parameter` — one named quantity on a device, as an object.

Before this module a device's parameters were four parallel `dict`s on
`DeviceSchema` (`readable`, `settable`, `units`, `limits`) keyed by name.
Nothing tied a name's entries together, so nothing could be enforced or
even reliably asked: `limits` was declared by a handful of adapters and
checked by none of them, and "which key is the integration time" was
answered by four separate substring searches in four modules, using two
different rules.

A `Parameter` gathers those facts into one object that can answer for
itself — `validate()` enforces its own limits and choices, `role` and
`tags` say what it *means* rather than leaving callers to infer it from
its name, and `axes` records which other parameters index it (the fact
`core/workflow_templates/_common.py::detector_axes` currently has to
guess from a substring hint list plus a live `read()`).

## dtype and shape

`dtype` is the element type and `shape` is the array shape, so a
spectrometer's intensity array is `dtype="f8", shape=(None,)` rather than
the single opaque string `"ndarray1d"`. `None` in a shape means "length
known only at runtime", which is the usual case for a detector whose
pixel count depends on its configuration.

The canonical dtypes are `CANONICAL_DTYPES`, but the field is a plain
`str`, not a closed `Literal`. That is deliberate: 301 adapters construct
schemas at import time, and a closed literal would turn any dtype string
this module failed to anticipate into an ImportError that takes a whole
manufacturer's adapters offline. Unrecognised dtypes are carried verbatim
and skipped by value-coercion instead — legible, lossless, and
non-fatal. `legacy_dtype()` reconstructs the old single-string form
exactly, including for those pass-through values, which is what lets the
REST payload and the Qt widgets keep working unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from labpilot.core.errors import ChoiceError, LimitError, ParameterError

__all__ = [
    "CANONICAL_DTYPES",
    "INTEGRATION_TIME",
    "RECORD",
    "ParamRole",
    "Parameter",
    "legacy_dtype_to_parts",
]


class ParamRole(StrEnum):
    """What a parameter *means*, independent of its name.

    The one piece of metadata no adapter could previously express, and the
    reason downstream layers guess. `AXIS` in particular is the fact that
    makes a plot drawable without a hint list: a 1-D array parameter whose
    `axes` names an `AXIS` parameter has a real x-scale, and one that
    doesn't, doesn't.
    """

    VALUE = "value"
    """A measured quantity — the thing the detector is for."""

    AXIS = "axis"
    """Coordinates indexing another parameter's array (wavelengths,
    time base, frequency bins). Never itself the measurement."""

    POSITION = "position"
    """A commandable physical position — an actuator axis."""

    SETTING = "setting"
    """A configuration knob (integration time, gain, trigger mode)."""

    STATUS = "status"
    """Read-only state that is not a measurement (moving, temperature
    stable, error code)."""


CANONICAL_DTYPES = frozenset({"f8", "i8", "bool", "str", "json", "record"})
"""Element types this module can coerce and range-check. Anything else is
carried through untouched — see the module docstring."""

RECORD = "record"
"""A structured value, described by `Parameter.fields`.

`dtype="json"` was the only way to declare a setpoint that isn't a scalar,
and it describes nothing: `validate()` returns a json value untouched, the
settings tree renders it as nothing at all, and the one adapter using it
needed a hand-written widget keyed to its exact dict shape. A `record`
says what the structure *is*, in the same vocabulary as everything else —
its fields are `Parameter`s, so they carry units, limits and choices, and
they validate and render with the machinery that already exists.

With `shape=()` a record is one mapping. With `shape=(None,)` it is a
table of them — a list of rows of that shape, which is what a pulse-block
table, an AWG channel map or an NI task's channel list actually is.
"""

INTEGRATION_TIME = "integration_time"
"""Standard tag for "the parameter that sets how long one reading takes".

Adapters name it `integration_time_ms`, `integration_time_s`,
`exposure_time_ms`, `exposure`, ... — this tag is how a caller asks for it
once instead of four modules each searching for a substring."""


# Legacy dtype string -> (element dtype, shape). Covers every dtype string
# any adapter in this repo actually uses, plus the near-miss spellings
# (`int`, `float`, `int64`) that appear in hand-written schemas.
_LEGACY_SCALARS: dict[str, str] = {
    "float64": "f8", "float32": "f8", "float": "f8", "f8": "f8", "f4": "f8",
    "int32": "i8", "int64": "i8", "int": "i8", "i8": "i8", "i4": "i8",
    "uint8": "i8", "uint16": "i8", "uint32": "i8",
    "bool": "bool",
    "str": "str", "string": "str",
    "json": "json", "tuple": "json", "dict": "json", "list": "json",
    "record": "record",
}

# Reverse map, for reconstructing the legacy string. Chosen so the
# spellings the Qt widgets actually branch on survive a round trip:
# `settings_tree.py` tests for "json" and "bool", `move_controls.py` for
# the integer names, `schema_utils.py` for "ndarray1d".
_CANONICAL_TO_LEGACY: dict[str, str] = {
    "f8": "float64", "i8": "int32", "bool": "bool", "str": "str", "json": "json",
    # A record has no legacy spelling — it did not exist. "json" is the
    # honest answer for a caller reading the old flat views: structured,
    # and not something a float widget should try to render. Consumers that
    # understand records read `fields` instead.
    "record": "json",
}

# Numeric, readable-and-settable parameters that a motor has but that are
# not positions you can scan. Without this, a stage declaring both
# "position" and "speed" reports two commandable axes, and anything asking
# for its axes (a move control, a scan) offers to sweep its speed.
_MOTOR_SETTINGS = frozenset({
    "velocity", "speed", "acceleration", "deceleration", "jerk",
    "step_size", "backlash", "home_offset",
})


def legacy_dtype_to_parts(dtype: str) -> tuple[str, tuple[int | None, ...]]:
    """Split an old-style dtype string into `(element dtype, shape)`.

    `"float64"` -> `("f8", ())`; `"ndarray2d"` -> `("f8", (None, None))`.
    An unrecognised string is returned verbatim as a scalar dtype rather
    than rejected, so a schema this module has never seen still loads.
    """
    if dtype.startswith("ndarray") and dtype.endswith("d"):
        rank_text = dtype[len("ndarray"):-1]
        if rank_text.isdigit() and int(rank_text) > 0:
            return "f8", (None,) * int(rank_text)
    return _LEGACY_SCALARS.get(dtype, dtype), ()


@dataclass(frozen=True, slots=True)
class Parameter:
    """One named quantity a device can report or accept.

    Example:
        >>> Parameter("integration_time_ms", unit="ms", role=ParamRole.SETTING,
        ...           settable=True, limits=(1.0, 60000.0),
        ...           tags=frozenset({INTEGRATION_TIME}))
    """

    name: str
    dtype: str = "f8"
    shape: tuple[int | None, ...] = ()
    unit: str = ""
    role: ParamRole = ParamRole.VALUE
    readable: bool = True
    settable: bool = False
    limits: tuple[float | None, float | None] | None = None
    choices: tuple[Any, ...] | None = None
    axes: tuple[str, ...] = ()
    tags: frozenset[str] = field(default_factory=frozenset)
    description: str = ""
    fields: tuple[Parameter, ...] = ()
    """The members of a structured value — see `RECORD`. Empty for every
    ordinary parameter. Declaring any implies `dtype="record"`.

    Every declared field is required and no undeclared key is accepted: a
    partially-specified structure is almost always a typo, and there is no
    per-field default to fall back on. (If optional members are ever
    needed, a `default` on `Parameter` is the natural way to add them.)
    """

    def __post_init__(self) -> None:
        if not self.name:
            raise ParameterError("Parameter name must not be empty")
        if not self.readable and not self.settable:
            raise ParameterError(
                f"Parameter {self.name!r} is neither readable nor settable",
                parameter=self.name,
            )
        # Normalise the containers so two Parameters describing the same
        # thing compare equal and stay hashable, whichever way a caller
        # spelled them (list vs tuple, set vs frozenset).
        object.__setattr__(self, "shape", tuple(self.shape))
        object.__setattr__(self, "axes", tuple(self.axes))
        object.__setattr__(self, "tags", frozenset(self.tags))
        object.__setattr__(self, "fields", tuple(self.fields))

        if self.fields:
            if self.dtype in ("f8", RECORD):
                # `f8` is the field default, so declaring members is enough
                # to mean "this is a record" without also saying so.
                object.__setattr__(self, "dtype", RECORD)
            else:
                raise ParameterError(
                    f"Parameter {self.name!r} declares fields, so its dtype "
                    f"must be {RECORD!r}, not {self.dtype!r}",
                    parameter=self.name,
                )
            seen: set[str] = set()
            for member in self.fields:
                if member.name in seen:
                    raise ParameterError(
                        f"Parameter {self.name!r} declares the field "
                        f"{member.name!r} twice",
                        parameter=self.name,
                    )
                seen.add(member.name)
            if self.shape not in ((), (None,)):
                raise ParameterError(
                    f"Parameter {self.name!r} is a record, so its shape must "
                    f"be () for one or (None,) for a table of them, "
                    f"not {self.shape}",
                    parameter=self.name,
                )
        elif self.dtype == RECORD:
            raise ParameterError(
                f"Parameter {self.name!r} is a {RECORD!r} but declares no "
                f"fields, so nothing describes its structure",
                parameter=self.name,
            )
        if self.choices is not None:
            object.__setattr__(self, "choices", tuple(self.choices))
        if self.limits is not None:
            low, high = self.limits
            if low is not None and high is not None and low > high:
                raise ParameterError(
                    f"Parameter {self.name!r} has inverted limits ({low} > {high})",
                    parameter=self.name,
                )
            object.__setattr__(self, "limits", (low, high))

    # --- Derived facts ----------------------------------------------------

    @property
    def ndim(self) -> int:
        return len(self.shape)

    @property
    def is_array(self) -> bool:
        return bool(self.shape)

    @property
    def is_record(self) -> bool:
        """One structured value, or a table of them."""
        return bool(self.fields)

    @property
    def is_table(self) -> bool:
        """A sequence of records — a pulse-block table, a channel map."""
        return bool(self.fields) and self.shape == (None,)

    def field(self, name: str) -> Parameter | None:
        """This record's member of that name, or None."""
        return next((f for f in self.fields if f.name == name), None)

    def legacy_dtype(self) -> str:
        """The old single-string dtype, reconstructed exactly.

        This is what `DeviceSchema.readable` / `.settable` still serve, so
        the REST payload and every Qt widget reading those dicts keep
        seeing what they saw before `Parameter` existed.
        """
        if self.dtype == RECORD:
            # Before ndarray: a table of records is not an array of numbers,
            # and a caller reading the flat views must not treat it as one.
            return _CANONICAL_TO_LEGACY[RECORD]
        if self.shape:
            return f"ndarray{len(self.shape)}d"
        return _CANONICAL_TO_LEGACY.get(self.dtype, self.dtype)

    def matches(
        self,
        *,
        role: ParamRole | None = None,
        tags: frozenset[str] | set[str] | None = None,
        settable: bool | None = None,
        readable: bool | None = None,
    ) -> bool:
        """Whether this parameter satisfies every given criterion.

        `tags` matches when the parameter carries *all* of them.
        """
        if role is not None and self.role is not role:
            return False
        if tags and not set(tags).issubset(self.tags):
            return False
        if settable is not None and self.settable != settable:
            return False
        return not (readable is not None and self.readable != readable)

    # --- Validation -------------------------------------------------------

    def validate(self, value: Any, *, device: str | None = None) -> Any:
        """Check `value` against this parameter and return it coerced.

        Returns the value converted to the declared element type (so an
        integer arriving over JSON for an `f8` parameter becomes a float)
        rather than just approving it, because every caller that validates
        wants the coerced value next anyway.

        Raises:
            LimitError: value outside `limits`.
            ChoiceError: value not among `choices`.
            ParameterError: value of a type this parameter cannot hold.
        """
        if self.is_record:
            return self._validate_record(value, device=device)

        if self.is_array or self.dtype not in CANONICAL_DTYPES:
            # A numeric array setpoint (a sampled waveform) or a dtype this
            # module doesn't model: nothing to coerce, and range-checking
            # element-wise is Phase 2's job once arrays are first-class.
            # A *structured* setpoint is no longer in this bucket — that is
            # what `fields` is for.
            return value

        coerced = self._coerce(value, device=device)

        if self.choices is not None and coerced not in self.choices:
            raise ChoiceError(
                f"{coerced!r} is not a valid value for {self.name!r}"
                f"{f' on {device}' if device else ''} — "
                f"choices are {list(self.choices)}",
                device=device, parameter=self.name, value=coerced, choices=self.choices,
            )

        if self.limits is not None and self.dtype in ("f8", "i8"):
            low, high = self.limits
            if (low is not None and coerced < low) or (high is not None and coerced > high):
                shown = (
                    f"[{'-inf' if low is None else low}, "
                    f"{'inf' if high is None else high}]"
                )
                raise LimitError(
                    f"{coerced} is outside the limits {shown}"
                    + (f" {self.unit}" if self.unit else "")
                    + f" of {f'{device}.' if device else ''}{self.name}",
                    device=device, parameter=self.name, value=coerced, limits=self.limits,
                )

        return coerced

    def _validate_record(self, value: Any, *, device: str | None) -> Any:
        """Validate one structured value, or a table of them.

        Recurses through `fields`, so a limit declared on a pulse element's
        duration is enforced on every row of a pulse table by the same code
        that enforces a scalar setpoint's limit — which is the whole point
        of describing the structure rather than escaping it as json.
        """
        where = f"{f'{device}.' if device else ''}{self.name}"

        if self.is_table:
            if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
                raise ParameterError(
                    f"{where} is a table, so it needs a sequence of rows, "
                    f"not {type(value).__name__}",
                    device=device, parameter=self.name,
                )
            return [
                self._validate_row(row, device=device, index=index)
                for index, row in enumerate(value)
            ]

        return self._validate_row(value, device=device, index=None)

    def _validate_row(self, value: Any, *, device: str | None, index: int | None) -> Any:
        at = f"[{index}]" if index is not None else ""
        where = f"{f'{device}.' if device else ''}{self.name}{at}"

        if not isinstance(value, Mapping):
            raise ParameterError(
                f"{where} needs a mapping with the keys "
                f"{[f.name for f in self.fields]}, not {type(value).__name__}",
                device=device, parameter=self.name,
            )

        unknown = set(value) - {f.name for f in self.fields}
        if unknown:
            raise ParameterError(
                f"{where} has no field(s) {', '.join(sorted(unknown))} — "
                f"it declares: {', '.join(f.name for f in self.fields)}",
                device=device, parameter=self.name,
            )

        validated: dict[str, Any] = {}
        for member in self.fields:
            if member.name not in value:
                raise ParameterError(
                    f"{where} is missing the field {member.name!r}",
                    device=device, parameter=self.name,
                )
            # Reported against the nested parameter, so a bad duration on
            # row 7 names the duration and its limits, not the table.
            validated[member.name] = member.validate(value[member.name], device=device)
        return validated

    def _coerce(self, value: Any, *, device: str | None) -> Any:
        try:
            if self.dtype == "f8":
                # bool is a subclass of int and would silently become 0.0/1.0;
                # a bool reaching a float parameter is a caller mistake worth
                # reporting, not rounding away.
                if isinstance(value, bool):
                    raise TypeError("bool is not a float")
                return float(value)
            if self.dtype == "i8":
                if isinstance(value, bool):
                    raise TypeError("bool is not an integer")
                as_float = float(value)
                if as_float != int(as_float):
                    raise TypeError(f"{value!r} is not a whole number")
                return int(as_float)
            if self.dtype == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)) and value in (0, 1):
                    return bool(value)
                raise TypeError(f"{value!r} is not a boolean")
            if self.dtype == "str":
                if not isinstance(value, str):
                    raise TypeError(f"{value!r} is not a string")
                return value
        except (TypeError, ValueError) as exc:
            raise ParameterError(
                f"{value!r} is not a valid {self.dtype} value for {self.name!r}"
                f"{f' on {device}' if device else ''}: {exc}",
                device=device, parameter=self.name,
            ) from exc
        return value

    # --- Construction from legacy schema fields ---------------------------

    @classmethod
    def from_legacy(
        cls,
        name: str,
        *,
        dtype: str = "float64",
        unit: str = "",
        limits: tuple[float | None, float | None] | None = None,
        readable: bool = True,
        settable: bool = False,
        kind: str = "generic",
    ) -> Parameter:
        """Build a `Parameter` from the flat fields of an old `DeviceSchema`.

        `role` and `tags` have to be *inferred* here, because the legacy
        format had nowhere to state them. The inference is deliberately the
        same rule the code being replaced already used, so this changes no
        behaviour — it just performs the guess once, at schema
        construction, instead of at four separate call sites:

        - a readable+settable numeric axis on a motor is a `POSITION`
          (`ui/desktop/components/schema_utils.py::move_axes`);
        - anything else settable is a `SETTING`;
        - a readable-only non-numeric is `STATUS`, otherwise `VALUE`;
        - a settable name containing "integration_time" or "exposure"
          carries the `INTEGRATION_TIME` tag
          (`workflow_templates/_common.py::integration_time_key` and
          `schema_utils.py::main_config_names`).

        `AXIS` is *not* inferred. Guessing which readable is another's axis
        from its name is exactly the heuristic this work exists to remove;
        an adapter that knows must say so by declaring a `Parameter`
        directly.
        """
        element, shape = legacy_dtype_to_parts(dtype)

        if (
            settable and readable and not shape and element in ("f8", "i8")
            and kind == "motor" and name not in _MOTOR_SETTINGS
        ):
            role = ParamRole.POSITION
        elif settable:
            role = ParamRole.SETTING
        elif element in ("bool", "str") and not shape:
            role = ParamRole.STATUS
        else:
            role = ParamRole.VALUE

        tags: set[str] = set()
        if settable and ("integration_time" in name or "exposure" in name):
            tags.add(INTEGRATION_TIME)

        return cls(
            name=name, dtype=element, shape=shape, unit=unit, role=role,
            readable=readable, settable=settable, limits=limits,
            tags=frozenset(tags),
        )

    def evolve(self, **changes: Any) -> Parameter:
        """A copy with some fields replaced — `dataclasses.replace` by
        another name, so callers need not import it to refine a parameter
        an introspecting adapter built for them."""
        return replace(self, **changes)
