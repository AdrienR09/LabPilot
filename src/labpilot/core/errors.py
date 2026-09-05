"""LabPilot's exception hierarchy.

Every error raised deliberately by the framework derives from
`LabPilotError`, so a script, a workflow template or the server can catch
"something LabPilot rejected" without also swallowing the `KeyError` from
its own typo.

Before this module the framework raised bare `ValueError`, `KeyError`,
`RuntimeError` and `NotImplementedError` from the device layer, which made
two things impossible: telling "you asked for an out-of-range setpoint"
apart from "a driver blew up", and reporting either one to the UI with a
machine-readable reason. The REST layer maps these to status codes (see
`core/api/dashboard.py`), so the class *is* part of the public contract:
a `ParameterError` is the caller's fault (HTTP 400), a `DeviceError` is
the instrument's (HTTP 409/503).

Naming note: `ConnectionError` and `TimeoutError` deliberately are NOT
redefined here — those are builtins with exactly the right meaning, and
shadowing them in a module people will `import *` from is a trap. Where a
LabPilot-specific connection failure matters, `NotConnectedError` names
the narrower condition (the adapter was never connected) that the builtin
does not cover.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ChoiceError",
    "DeviceError",
    "LabPilotError",
    "LimitError",
    "NotConnectedError",
    "NotSettableError",
    "ParameterError",
    "SchemaError",
    "UnknownParameterError",
    "UnsupportedOperationError",
    "WorkflowError",
]


class LabPilotError(Exception):
    """Base class for every error LabPilot raises deliberately."""


# --- Device / driver layer ------------------------------------------------


class DeviceError(LabPilotError):
    """A device could not carry out a request.

    Carries the device name so a message assembled several layers up
    (a workflow, the REST layer) can still say *which* instrument failed.
    """

    def __init__(self, message: str, *, device: str | None = None) -> None:
        super().__init__(message)
        self.device = device


class NotConnectedError(DeviceError):
    """An operation needing hardware was attempted before `connect()`."""


class UnsupportedOperationError(DeviceError):
    """The device genuinely cannot do this.

    Distinct from `NotImplementedError`, which in this codebase has meant
    both "this adapter is unfinished" and "this hardware has no such
    capability" — a distinction the UI needs, since the first is a bug to
    report and the second is a control to hide.
    """


# --- Parameter layer ------------------------------------------------------


class ParameterError(LabPilotError):
    """Base for anything wrong with a parameter name or value.

    Always the *caller's* fault, never the hardware's — which is what lets
    the REST layer map this subtree, and only this subtree, to HTTP 400.
    """

    def __init__(self, message: str, *, device: str | None = None,
                 parameter: str | None = None) -> None:
        super().__init__(message)
        self.device = device
        self.parameter = parameter


class UnknownParameterError(ParameterError):
    """No parameter of that name exists on this device."""


class NotSettableError(ParameterError):
    """The parameter exists but is read-only."""


class LimitError(ParameterError):
    """A value fell outside the parameter's declared limits.

    Keeps the offending value and the bounds as attributes rather than
    only in the message, so a UI can highlight the field and clamp to the
    nearest legal value without re-parsing English.
    """

    def __init__(self, message: str, *, device: str | None = None,
                 parameter: str | None = None, value: Any = None,
                 limits: tuple[float | None, float | None] | None = None) -> None:
        super().__init__(message, device=device, parameter=parameter)
        self.value = value
        self.limits = limits


class ChoiceError(ParameterError):
    """A value was not one of the parameter's declared choices."""

    def __init__(self, message: str, *, device: str | None = None,
                 parameter: str | None = None, value: Any = None,
                 choices: tuple[Any, ...] | None = None) -> None:
        super().__init__(message, device=device, parameter=parameter)
        self.value = value
        self.choices = choices


class SchemaError(LabPilotError):
    """A `DeviceSchema` is internally inconsistent.

    Raised at schema-construction time (an adapter bug), not at call time.
    """


# --- Orchestration --------------------------------------------------------


class WorkflowError(LabPilotError):
    """A workflow could not be loaded, bound or run."""
