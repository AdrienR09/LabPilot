"""`Action` — a device command that takes arguments and reports results.

`DeviceSchema.actions` was `list[str]`: bare names of zero-argument adapter
methods, invoked as `getattr(adapter, name)()`. That covers a state
transition (`cw_on`, `reset_scan`) and nothing else, and the limit was
structural rather than incidental — the name is a URL path segment and the
REST route carried no request body at all, so there was no place for an
argument to travel even if the schema had described one.

Every device that does something more interesting than reading and writing
scalars runs into it. A gated counter's `configure(bin_width_s,
record_length_s, gates)`, an AWG's `write_sequence(samples, name)`, an NI
card's task setup: each is one command with several arguments, and none of
them is a parameter write. Until now the only ways to express one were a
`dtype="json"` settable — which `Parameter.validate` returns unchecked and
the settings tree renders as nothing — or a plain adapter method reached by
`__getattr__` passthrough from a workflow script, invisible to both the UI
and REST.

## Arguments are Parameters

`params` are `Parameter` objects, not a bespoke argument type. That is the
whole point: limits, choices, units, dtype coercion and `validate()` already
exist and are already enforced on the write path, so an action's arguments
get the same treatment for free, and the settings tree can render an
action's argument form with the same widget code that renders a settings
dock. A device gets one vocabulary for "a named, typed, bounded quantity",
whether it is being written, read, or passed to a command.

## Why `returns`

Hardware quantises. A counter's bin width comes from a discrete list, a
pulser's waveform length must be a multiple of its granularity, a sample
rate snaps to what the clock can divide down to. The established answer —
qudi's `FastCounterInterface.configure()` returns the binwidth, record
length and gate count it *actually* set — is that a configure call is a
negotiation, not an assignment. `returns` declares the shape of that reply
so a caller (and the UI) can show what the hardware really did rather than
what was asked for, instead of every consumer re-reading state afterwards
and hoping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from labpilot.core.device.parameter import Parameter
from labpilot.core.errors import ParameterError

__all__ = ["Action"]


@dataclass(frozen=True, slots=True)
class Action:
    """One named device command.

    Args:
        name: The adapter method to call, and the name used over REST.
        params: Declared arguments. Each is required unless `defaults`
            supplies a value for it.
        returns: What the call reports back, for a command that negotiates
            (see the module docstring). Purely descriptive — nothing
            validates a return value.
        defaults: Values for params the caller may omit. A name here that
            is not in `params` is a declaration error.
        description: Shown as the button's tooltip.
    """

    name: str
    params: tuple[Parameter, ...] = ()
    returns: tuple[Parameter, ...] = ()
    defaults: Mapping[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("An action needs a name")
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "returns", tuple(self.returns))
        object.__setattr__(self, "defaults", dict(self.defaults))

        seen: set[str] = set()
        for parameter in self.params:
            if parameter.name in seen:
                raise ValueError(
                    f"Action {self.name!r} declares {parameter.name!r} twice"
                )
            seen.add(parameter.name)
        unknown = set(self.defaults) - seen
        if unknown:
            raise ValueError(
                f"Action {self.name!r} has defaults for undeclared "
                f"argument(s): {', '.join(sorted(unknown))}"
            )

    @property
    def takes_arguments(self) -> bool:
        return bool(self.params)

    def get(self, name: str) -> Parameter | None:
        return next((p for p in self.params if p.name == name), None)

    def bind(self, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Validate call arguments and return them coerced, ready to splat.

        Raises `ParameterError` for an unknown or missing argument, and
        whatever `Parameter.validate` raises (`LimitError`, `ChoiceError`)
        for one that is out of range. Checked here rather than in the
        adapter so a bad call fails the same way over REST, from the
        console and from a workflow script.
        """
        given = dict(arguments or {})

        unknown = set(given) - {p.name for p in self.params}
        if unknown:
            declared = ", ".join(p.name for p in self.params) or "none"
            raise ParameterError(
                f"Action {self.name!r} takes no argument(s) "
                f"{', '.join(sorted(unknown))} — it declares: {declared}"
            )

        bound: dict[str, Any] = {}
        for parameter in self.params:
            if parameter.name in given:
                value = given[parameter.name]
            elif parameter.name in self.defaults:
                value = self.defaults[parameter.name]
            else:
                raise ParameterError(
                    f"Action {self.name!r} requires {parameter.name!r}"
                )
            bound[parameter.name] = parameter.validate(value)
        return bound

    def to_dict(self) -> dict[str, Any]:
        """The wire form. `params`/`returns` are serialised through the same
        shape the settings tree already reads for a schema's parameters."""
        return {
            "name": self.name,
            "description": self.description,
            "params": [_parameter_to_dict(p) for p in self.params],
            "returns": [_parameter_to_dict(p) for p in self.returns],
            "defaults": dict(self.defaults),
        }

    @classmethod
    def from_any(cls, value: Any) -> Action:
        """Build one from a bare name, a dict, or an `Action`.

        The bare-name case is what keeps every existing adapter working:
        `actions=["cw_on", "off"]` still means two zero-argument commands.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(name=value)
        if isinstance(value, Mapping):
            data = dict(value)
            return cls(
                name=data["name"],
                params=tuple(_parameter_from_dict(p) for p in data.get("params") or ()),
                returns=tuple(
                    _parameter_from_dict(p) for p in data.get("returns") or ()
                ),
                defaults=data.get("defaults") or {},
                description=data.get("description", ""),
            )
        raise TypeError(f"Cannot read an action from {type(value).__name__}")


def _parameter_to_dict(parameter: Parameter) -> dict[str, Any]:
    return {
        "name": parameter.name,
        "dtype": parameter.legacy_dtype(),
        "unit": parameter.unit,
        "limits": list(parameter.limits) if parameter.limits else None,
        "choices": list(parameter.choices) if parameter.choices else None,
        "description": parameter.description,
    }


def _parameter_from_dict(data: Any) -> Parameter:
    if isinstance(data, Parameter):
        return data
    data = dict(data)
    limits = data.get("limits")
    choices = data.get("choices")
    return Parameter(
        name=data["name"],
        dtype=data.get("dtype", "f8"),
        unit=data.get("unit", ""),
        limits=tuple(limits) if limits else None,
        choices=tuple(choices) if choices else None,
        description=data.get("description", ""),
        settable=True,
    )
