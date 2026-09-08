"""Device schema — what a device is and what it can do.

A `DeviceSchema` is built on a tuple of `Parameter` objects (see
`parameter.py`). It used to be built on four parallel dicts keyed by
parameter name (`readable`, `settable`, `units`, `limits`), which is why
nothing could enforce a limit or ask what a parameter *meant*.

Those four dicts still exist, as **computed views** over `parameters`.
That is what makes this a non-event for the 301 adapters in this repo and
for every consumer downstream:

- every adapter that constructs `DeviceSchema(readable={...},
  settable={...}, units={...}, limits={...})` keeps working verbatim —
  `_from_legacy_fields` below turns those kwargs into `Parameter`s at
  construction time;
- every reader of `schema.readable[name]` keeps getting the same dtype
  string back, because `Parameter.legacy_dtype()` reconstructs it exactly;
- the REST payload is unchanged apart from one added `parameters` key,
  because the views are `computed_field`s and so still appear in
  `model_dump()`.

New adapters should pass `parameters=(...)` directly and get limits
enforcement, roles, tags and per-parameter axes. Both forms may be mixed;
explicit `Parameter`s win over a legacy entry of the same name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from labpilot.core.device.action import Action
from labpilot.core.device.parameter import INTEGRATION_TIME, Parameter, ParamRole
from labpilot.core.errors import UnknownParameterError

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["DeviceSchema"]

# The legacy per-parameter fields, in the order the before-validator
# consumes them. Named once so `_LEGACY_FIELDS` and the docstring above
# cannot drift apart.
_LEGACY_FIELDS = ("readable", "settable", "units", "limits")


class DeviceSchema(BaseModel):
    """Structured description of a device's capabilities and metadata.

    Used for auto-GUI generation, write validation, run metadata, and
    runtime introspection.

    Example (new form):
        >>> DeviceSchema(
        ...     name="ocean_insight_usb2000",
        ...     kind="detector",
        ...     parameters=(
        ...         Parameter("wavelengths", shape=(None,), unit="nm",
        ...                   role=ParamRole.AXIS),
        ...         Parameter("intensities", shape=(None,), unit="counts",
        ...                   axes=("wavelengths",)),
        ...         Parameter("integration_time_ms", unit="ms", settable=True,
        ...                   role=ParamRole.SETTING, limits=(1.0, 60000.0),
        ...                   tags=frozenset({INTEGRATION_TIME})),
        ...     ),
        ...     tags=["spectroscopy", "VISA"],
        ... )

    Example (legacy form, still accepted verbatim):
        >>> DeviceSchema(
        ...     name="ocean_insight_usb2000",
        ...     kind="detector",
        ...     readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
        ...     settable={"integration_time_ms": "float64"},
        ...     units={"wavelengths": "nm", "intensities": "counts"},
        ...     limits={"integration_time_ms": (1.0, 60000.0)},
        ... )
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        description="Unique device identifier (e.g., 'thorlabs_mdt693b_x')"
    )
    kind: Literal["detector", "motor", "source", "counter", "generic"] = Field(
        description="Device category for semantic grouping"
    )
    parameters: tuple[Parameter, ...] = Field(
        default=(),
        description="Every quantity this device reports or accepts",
    )
    trigger_modes: list[str] = Field(
        default_factory=list,
        description="Supported trigger modes (e.g., ['software', 'hardware'])",
    )
    actions: tuple[Action, ...] = Field(
        default=(),
        description=(
            "Adapter methods callable as commands, beyond the settable/"
            "set_<key> write contract — state transitions like 'cw_on' or "
            "'reset_scan', and parameterised commands like a gated counter's "
            "configure(bin_width_s, record_length_s, gates). A bare name is "
            "still accepted and means a zero-argument action."
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags (e.g., ['spectroscopy', 'NI', 'VISA'])",
    )

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: Any) -> Any:
        """Accept `["cw_on", "off"]`, dicts, or `Action`s, in any mix.

        Every adapter in this repo declares actions as a list of bare
        names, and a `model_dump()` round trip brings them back as dicts.
        Both mean the same thing as an `Action`, so both are read as one
        rather than made into a migration.
        """
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            raise TypeError("actions must be a sequence, not a single string")
        return tuple(Action.from_any(item) for item in value)

    # --- Legacy construction ---------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _from_legacy_fields(cls, data: Any) -> Any:
        """Accept the pre-`Parameter` keyword form.

        This validator is the entire migration strategy for the 301
        adapters in this repo: they keep constructing schemas exactly as
        they do today, and get `Parameter` objects out. It also lets a
        `model_dump()` round-trip back into a schema, by ignoring the
        computed views whenever `parameters` is present.
        """
        if not isinstance(data, dict):
            return data
        if "action_names" in data:
            # A computed view, like the four below: it comes back in a
            # `model_dump()` round trip and `actions` already carries it.
            data = dict(data)
            data.pop("action_names")
        if not any(key in data for key in _LEGACY_FIELDS):
            return data

        data = dict(data)
        readable = data.pop("readable", None) or {}
        settable = data.pop("settable", None) or {}
        units = data.pop("units", None) or {}
        limits = data.pop("limits", None) or {}

        explicit = tuple(data.get("parameters") or ())
        if explicit:
            # `parameters` was given as well — the legacy keys are then the
            # computed views coming back from a model_dump() round trip, or
            # a partial hand-written overlay. Either way the explicit
            # objects are authoritative; only fill in names they omit.
            known = {
                p.name if isinstance(p, Parameter) else p.get("name")
                for p in explicit
            }
        else:
            known = set()

        built: list[Parameter] = []
        for name in dict.fromkeys((*readable, *settable)):
            if name in known:
                continue
            is_readable = name in readable
            is_settable = name in settable
            built.append(
                Parameter.from_legacy(
                    name,
                    # A key that is both readable and settable takes its
                    # dtype from `settable`: that is the one the write path
                    # coerces against, and where the two disagree (a couple
                    # of adapters declare "float64" readable / "bool"
                    # settable) the settable spelling is the actionable one.
                    dtype=settable.get(name) or readable.get(name) or "float64",
                    unit=units.get(name, ""),
                    limits=tuple(limits[name]) if name in limits else None,
                    readable=is_readable,
                    settable=is_settable,
                    kind=data.get("kind", "generic"),
                )
            )

        data["parameters"] = (*explicit, *built)
        return data

    # --- Computed legacy views -------------------------------------------
    #
    # `computed_field` rather than a plain `@property` so these still appear
    # in `model_dump()` / `model_dump_json()`. The Qt settings tree, the Qt
    # move controls and the React instrument modal all read these keys off
    # the serialised schema; making them properties would have emptied all
    # three silently.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def readable(self) -> dict[str, str]:
        """Readable parameter names -> legacy dtype string."""
        return {p.name: p.legacy_dtype() for p in self.parameters if p.readable}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def settable(self) -> dict[str, str]:
        """Settable parameter names -> legacy dtype string."""
        return {p.name: p.legacy_dtype() for p in self.parameters if p.settable}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def units(self) -> dict[str, str]:
        """Parameter names -> unit string, for those that declare one."""
        return {p.name: p.unit for p in self.parameters if p.unit}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def limits(self) -> dict[str, tuple[float, float]]:
        """Parameter names -> (min, max).

        Only two-sided limits appear here, because that is what the legacy
        field meant and what the UI's spin-box range expects. A parameter
        bounded on one side only is still fully described by its own
        `Parameter.limits`, and is still enforced on write.
        """
        return {
            p.name: (p.limits[0], p.limits[1])
            for p in self.parameters
            if p.limits is not None and p.limits[0] is not None and p.limits[1] is not None
        }

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action_names(self) -> list[str]:
        """Just the names, for the many callers that only ask "is `stop` one
        of this device's actions?" — and so `model_dump()` keeps carrying a
        plain name list beside the richer `actions`."""
        return [a.name for a in self.actions]

    # --- Lookup -----------------------------------------------------------

    def action(self, name: str) -> Action | None:
        """This device's action of that name, or None."""
        return next((a for a in self.actions if a.name == name), None)

    def __iter__(self) -> Iterator[Parameter]:  # type: ignore[override]
        return iter(self.parameters)

    def get(self, name: str) -> Parameter | None:
        """This device's parameter of that name, or None."""
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        return None

    def require(self, name: str) -> Parameter:
        """This device's parameter of that name.

        Raises:
            UnknownParameterError: if the device has no such parameter.
        """
        parameter = self.get(name)
        if parameter is None:
            raise UnknownParameterError(
                f"{self.name!r} has no parameter {name!r} "
                f"(has: {sorted(p.name for p in self.parameters)})",
                device=self.name, parameter=name,
            )
        return parameter

    def find(
        self,
        *,
        role: ParamRole | None = None,
        tags: frozenset[str] | set[str] | None = None,
        settable: bool | None = None,
        readable: bool | None = None,
    ) -> tuple[Parameter, ...]:
        """Every parameter matching all the given criteria, in declaration order.

        Replaces the ad-hoc searches that used to be spread across
        `instruments/mixins.py`, `core/device/kinds.py`,
        `core/workflow_templates/_common.py` and
        `ui/desktop/components/schema_utils.py` — e.g. the four separate
        "which key is the integration time" implementations are now
        `schema.find(settable=True, tags={INTEGRATION_TIME})`.
        """
        return tuple(
            p for p in self.parameters
            if p.matches(role=role, tags=tags, settable=settable, readable=readable)
        )

    def first(self, **criteria: Any) -> Parameter | None:
        """The first parameter matching `find()`'s criteria, or None."""
        found = self.find(**criteria)
        return found[0] if found else None

    @property
    def integration_time(self) -> Parameter | None:
        """This device's integration-time parameter, if it has one."""
        return self.first(settable=True, tags={INTEGRATION_TIME})

    @property
    def primary(self) -> Parameter | None:
        """The parameter this device is *about* — its measurement.

        The highest-rank readable parameter that is not itself an axis,
        earliest declaration winning a tie. The schema-level counterpart of
        `Dataset.primary()`, for a caller that must choose before taking a
        reading; it replaces `spectrum_key()`, which excluded any key
        containing "wavelength" and took whatever was left, and so returned
        the *axis* for a Raman spectrometer reporting `shift`/`intensity`.
        """
        candidates = [
            p for p in self.parameters
            if p.readable and p.role is not ParamRole.AXIS
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.ndim)

    @property
    def position_axes(self) -> tuple[str, ...]:
        """Names of the continuous, commandable axes — what a move control
        should offer. Previously recomputed by name/dtype inspection in
        both `core/device/kinds.py` and `ui/.../schema_utils.py`."""
        return tuple(p.name for p in self.parameters if p.role is ParamRole.POSITION)

    @property
    def dimensionality(self) -> int:
        """Rank of this device's largest readable array — 0 for a scalar
        detector, 1 for a spectrometer, 2 for a camera.

        Derived, rather than the separate 0D/1D/2D/ND classification the
        catalog used to carry as its own enum variants and which nothing
        kept in sync with the actual schema.
        """
        return max((p.ndim for p in self.parameters if p.readable), default=0)
