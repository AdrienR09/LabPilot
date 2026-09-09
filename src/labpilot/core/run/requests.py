"""Starting a plan from outside the server process.

Instruments live in the server, so a plan built at a console cannot be
sent as an object. Its *fields* are sent, and the server rebuilds it —
the same boundary every other console call crosses, one API over two
transports rather than two APIs.

## Why this is a registry and not another route

`POST /api/runs/scan` rebuilt a `ScanPlan` and nothing else, and
`LabPilotSession.execute` rejected anything without `axes` and
`detector`. That wall was hit once by `HardwareTimedScanPlan`, which
still cannot be started from a console, and again by
`PulsedMeasurementPlan`. Adding a third bespoke route would have been
the third time, so instead a plan type declares how it crosses the
boundary — once, in both directions — and the route, the client and the
console read that declaration.

Each transport answers three questions, and the third is the one that
makes a good error message possible: which instruments must be connected
before the run is accepted. Discovering that on the worker loop, after
the caller has been told the run started, is how a missing counter turns
into a run that reports success and measures nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "TRANSPORTS",
    "PlanTransport",
    "build_plan",
    "plan_devices",
    "plan_request",
    "register_transport",
]


@dataclass(frozen=True, slots=True)
class PlanTransport:
    """How one plan type crosses the process boundary, both ways."""

    name: str
    plan_type: type
    to_params: Callable[[Any], dict[str, Any]]
    """The plan's fields, as JSON."""
    from_params: Callable[[Mapping[str, Any]], Any]
    """Those fields, back into a plan. Runs in the server process."""
    devices: Callable[[Mapping[str, Any]], set[str]]
    """Instruments this run will drive, so a disconnected one is a 409
    rather than a failure after the caller was told it started."""


#: Every plan that can be started from a console, by name.
TRANSPORTS: dict[str, PlanTransport] = {}


def register_transport(transport: PlanTransport) -> PlanTransport:
    TRANSPORTS[transport.name] = transport
    return transport


def plan_request(plan: Any) -> tuple[str, dict[str, Any]]:
    """`(plan name, fields)` for a plan object — what to send."""
    for transport in TRANSPORTS.values():
        if type(plan) is transport.plan_type:
            return transport.name, transport.to_params(plan)
    raise TypeError(
        f"{type(plan).__name__} cannot be started from outside the server "
        f"yet — these can: {', '.join(sorted(TRANSPORTS))}. Run it from a "
        f"workflow instead (see lp.workflows)."
    )


def build_plan(name: str, params: Mapping[str, Any]) -> Any:
    """Rebuild a plan from what was sent. Server-side."""
    return _transport(name).from_params(params)


def plan_devices(name: str, params: Mapping[str, Any]) -> set[str]:
    """Which instruments must be connected for this request."""
    return _transport(name).devices(params)


def _transport(name: str) -> PlanTransport:
    if name not in TRANSPORTS:
        raise ValueError(
            f"No plan named {name!r} — known: {', '.join(sorted(TRANSPORTS))}"
        )
    return TRANSPORTS[name]


# --- The plans that can be started from a console ---------------------------


def _scan_params(plan: Any) -> dict[str, Any]:
    return {
        "axes": [
            {
                "name": axis.name, "device": axis.device,
                "start": float(axis.start), "stop": float(axis.stop),
                "points": int(axis.points), "unit": axis.unit or "",
            }
            for axis in plan.axes
        ],
        "detector": plan.detector,
        "name": plan.name,
        "hold": dict(plan.hold or {}),
        "hold_device": plan.hold_device,
    }


def _scan_plan(params: Mapping[str, Any]) -> Any:
    from labpilot.core.run.plans import ScanAxis, ScanPlan

    axes = list(params.get("axes") or ())
    if not axes:
        raise ValueError("A scan needs at least one axis")
    return ScanPlan(
        axes=[ScanAxis(**dict(axis)) for axis in axes],
        detector=params["detector"],
        name=params.get("name") or "scan",
        hold=dict(params.get("hold") or {}),
        hold_device=params.get("hold_device"),
    )


def _scan_devices(params: Mapping[str, Any]) -> set[str]:
    return {axis["device"] for axis in params.get("axes") or ()} | {
        params["detector"]
    }


def _pulsed_params(plan: Any) -> dict[str, Any]:
    return {
        # The whole sequence travels, because the server has no copy of
        # it: a console may have built it from the generator library or
        # loaded it from a file, and the run has to record which one.
        "sequence": plan.sequence.to_dict(),
        "pulser": plan.pulser,
        "counter": plan.counter,
        "microwave": plan.microwave,
        "microwave_on": plan.microwave_on,
        "microwave_off": plan.microwave_off,
        "laser": plan.laser,
        "channels": dict(plan.channels or {}),
        "sweeps": int(plan.sweeps),
        "checkpoints": int(plan.checkpoints),
        "bin_width": float(plan.bin_width),
        "record_length": float(plan.record_length),
        "extract": plan.extract,
        "extract_params": dict(plan.extract_params or {}),
        "analyse": plan.analyse,
        "analyse_params": dict(plan.analyse_params or {}),
        "name": plan.name,
    }


def _pulsed_plan(params: Mapping[str, Any]) -> Any:
    from labpilot.core.pulse.sequence import PulseSequence
    from labpilot.core.run.plans import PulsedMeasurementPlan

    fields = dict(params)
    sequence = fields.pop("sequence")
    return PulsedMeasurementPlan(
        sequence=PulseSequence.from_dict(sequence),
        **{key: value for key, value in fields.items() if value is not None},
    )


def _pulsed_devices(params: Mapping[str, Any]) -> set[str]:
    named = (params["pulser"], params["counter"], params.get("microwave"))
    return {role for role in named if role}


def _time_series_params(plan: Any) -> dict[str, Any]:
    return {
        "detector": plan.detector,
        "samples": int(plan.samples),
        "interval": float(plan.interval),
        "name": plan.name,
    }


def _time_series_plan(params: Mapping[str, Any]) -> Any:
    from labpilot.core.run.plans import TimeSeriesPlan

    return TimeSeriesPlan(**dict(params))


def _register_all() -> None:
    """Deferred so importing this module does not import every plan.

    Called at the bottom of `core/run/plans.py`, which is where the plan
    types themselves become available.
    """
    from labpilot.core.run.plans import PulsedMeasurementPlan, ScanPlan, TimeSeriesPlan

    register_transport(
        PlanTransport("scan", ScanPlan, _scan_params, _scan_plan, _scan_devices)
    )
    register_transport(
        PlanTransport(
            "pulsed", PulsedMeasurementPlan,
            _pulsed_params, _pulsed_plan, _pulsed_devices,
        )
    )
    register_transport(
        PlanTransport(
            "time_series", TimeSeriesPlan,
            _time_series_params, _time_series_plan,
            lambda params: {params["detector"]},
        )
    )
