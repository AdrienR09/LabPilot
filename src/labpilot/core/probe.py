"""`labpilot probe <adapter>` — ask one instrument to answer for itself.

This is the first thing to run on a newly wired instrument, and it is how
an adapter stops being theoretical. Every adapter in this repo declares a
`DeviceSchema`: which quantities it reports, their units, their shapes,
what may be set and within what limits. For most of the 308 registered
adapters that declaration has never been checked against hardware — it
was written from a manual, and it is exactly as reliable as hand-entered
data ever is.

So the probe does four things and nothing else:

1. prints the schema the adapter declares with no hardware present;
2. connects, and says plainly why if it cannot;
3. prints the schema *again* — some adapters only learn their real
   channel count, pixel count or travel once the device answers;
4. reads **once**, and reports every place the reading disagrees with the
   declaration.

**It moves nothing and writes nothing.** No setter, no action, no
`stage()`, no `self_test()` — only `connect`, `schema`, `read`,
`disconnect`. That restraint is the whole reason this is safe to point at
a stage with a sample under an objective, and it is why the probe is a
separate command rather than a flag on something that drives hardware.

It generalises `scripts/ni_probe.py`, which does the same job for one
vendor and prints a `models.toml` block to paste into the user override.
That script stays: a DAQ card's inventory is table data, not a schema.

`--all` does the same for every instrument in a saved instrument set,
which is what bring-up actually looks like: eight instruments, one
command, and a table at the end saying which agreed. It uses each
instrument's saved connection parameters, so the config is the single
place an address is written down.

Exit codes are meant for a shell: 0 when the hardware agrees with the
declaration, 1 when it disagrees (the schema needs correcting, and the
output says how), 2 when the probe could not get far enough to tell. For
`--all` it is the worst of them, so one unreachable instrument fails the
run.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.device.parameter import ParamRole

if TYPE_CHECKING:
    from labpilot.core.data.dataset import Dataset
    from labpilot.core.device.schema import DeviceSchema

__all__ = [
    "Finding",
    "compare_reading",
    "compare_schemas",
    "describe_schema",
    "probe",
    "probe_rig",
]

OK, DISAGREES, CANNOT_TELL = 0, 1, 2


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the hardware and the declaration do not agree about.

    `fatal` separates "the schema is wrong" from "worth knowing": a
    declared parameter the device never returns breaks every consumer that
    trusts the schema, while an undeclared extra key only means the
    adapter is reporting more than it admits to.
    """

    text: str
    fatal: bool = True

    def __str__(self) -> str:
        return f"{'✗' if self.fatal else '·'} {self.text}"


# --- The comparisons, as pure functions -----------------------------------


def compare_schemas(declared: DeviceSchema, live: DeviceSchema) -> list[Finding]:
    """What changed in the schema once the device answered.

    Nothing here is a fault — an adapter that fills in its real pixel
    count on connect is doing the right thing. It is reported because it
    tells you which parts of the declaration are guesses, and because a
    *shrinking* schema (a parameter that disappears on connect) means
    anything built from the offline description will break.
    """
    findings: list[Finding] = []
    before = {p.name: p for p in declared}
    after = {p.name: p for p in live}

    for name in before.keys() - after.keys():
        findings.append(Finding(f"{name}: declared offline, gone once connected"))
    for name in after.keys() - before.keys():
        findings.append(Finding(f"{name}: appeared only once connected", fatal=False))

    for name in sorted(before.keys() & after.keys()):
        was, now = before[name], after[name]
        for field, old, new in (
            ("shape", was.shape, now.shape),
            ("unit", was.unit, now.unit),
            ("limits", was.limits, now.limits),
            ("settable", was.settable, now.settable),
        ):
            if old != new:
                findings.append(
                    Finding(f"{name}.{field}: {old!r} declared, {new!r} live", fatal=False)
                )
    return findings


def compare_reading(schema: DeviceSchema, dataset: Dataset) -> list[Finding]:
    """Where one real reading disagrees with what the schema promised."""
    findings: list[Finding] = []
    arrays = dict(dataset.arrays)
    declared = {p.name: p for p in schema.find(readable=True)}

    for name in sorted(declared.keys() - arrays.keys()):
        findings.append(
            Finding(f"{name}: declared readable, absent from the reading")
        )
    for name in sorted(arrays.keys() - declared.keys()):
        findings.append(
            Finding(f"{name}: returned but not declared", fatal=False)
        )

    for name in sorted(declared.keys() & arrays.keys()):
        parameter, values = declared[name], arrays[name].values
        findings.extend(_compare_shape(name, parameter.shape, values))
        findings.extend(_compare_limits(name, parameter, values))
        for axis in parameter.axes:
            if axis not in arrays:
                findings.append(
                    Finding(f"{name}: indexed by {axis!r}, which was not returned")
                )
    return findings


def _compare_shape(
    name: str, shape: tuple[int | None, ...], values: np.ndarray
) -> list[Finding]:
    """Rank first, then any dimension the schema pinned to a number.

    Rank is the one that matters: a parameter declared scalar and
    returning an array (or the reverse) breaks view selection, HDF5
    axis-scale attachment and every plan that preallocates a grid.
    """
    if len(shape) != values.ndim:
        return [
            Finding(
                f"{name}: declared {_rank(len(shape))}, read {_rank(values.ndim)} "
                f"{values.shape}"
            )
        ]
    fixed = [
        f"axis {index}: {want} declared, {got} read"
        for index, (want, got) in enumerate(zip(shape, values.shape, strict=False))
        if want is not None and want != got
    ]
    return [Finding(f"{name}: {'; '.join(fixed)}")] if fixed else []


def _compare_limits(name: str, parameter: Any, values: np.ndarray) -> list[Finding]:
    """A reading outside its own declared limits means the limits are wrong.

    Worth saying because `validate_write` enforces exactly these numbers:
    a stage that reports 12.4 mm while its schema says the travel ends at
    10 refuses a perfectly legal move.
    """
    if not parameter.limits or values.size == 0:
        return []
    numbers = np.asarray(values, dtype=float).ravel()
    numbers = numbers[np.isfinite(numbers)]
    if numbers.size == 0:
        return []
    low, high = parameter.limits
    out: list[Finding] = []
    if low is not None and numbers.min() < low:
        out.append(Finding(f"{name}: read {numbers.min():g}, below the declared {low:g}"))
    if high is not None and numbers.max() > high:
        out.append(Finding(f"{name}: read {numbers.max():g}, above the declared {high:g}"))
    return out


def _rank(ndim: int) -> str:
    return {0: "a scalar", 1: "a 1-D array"}.get(ndim, f"a {ndim}-D array")


# --- Rendering -------------------------------------------------------------


def describe_schema(schema: DeviceSchema) -> list[str]:
    """The schema as lines, which is also what makes it reviewable."""
    lines = [
        f"   kind            {schema.kind}  ({schema.dimensionality}-D)",
        f"   capabilities    {', '.join(sorted(schema.capabilities)) or '—'}",
        f"   tags            {', '.join(schema.tags) or '—'}",
    ]
    readable = schema.find(readable=True)
    settable = schema.find(settable=True)
    lines.append("")
    lines.append(f"   reads           {len(readable)}")
    for parameter in readable:
        lines.append(f"     {_parameter_line(parameter)}")
    lines.append(f"   sets            {len(settable)}")
    for parameter in settable:
        lines.append(f"     {_parameter_line(parameter)}")
    names = schema.action_names
    lines.append(f"   actions         {', '.join(names) or '—'}")
    return lines


def _parameter_line(parameter: Any) -> str:
    shape = "scalar" if not parameter.shape else str(
        tuple("n" if size is None else size for size in parameter.shape)
    ).replace("'", "")
    parts = [f"{parameter.name:<24} {shape:<12} {parameter.unit or '—':<10}"]
    if parameter.role is not ParamRole.VALUE:
        parts.append(str(parameter.role))
    if parameter.axes:
        parts.append(f"of {', '.join(parameter.axes)}")
    bounds = _bounds(parameter.limits)
    if bounds:
        parts.append(bounds)
    if parameter.choices:
        parts.append("one of " + ", ".join(str(choice) for choice in parameter.choices))
    return "  ".join(parts)


def _bounds(limits: tuple[float | None, float | None] | None) -> str:
    """A one-sided limit reads as one, not as an interval with a hole in it.

    `(1, None)` is a real and common declaration — an averaging count has
    a floor and no ceiling — and `[1 … ]` looks like a bug in the printer.
    """
    if not limits:
        return ""
    low, high = limits
    if low is not None and high is not None:
        return f"[{low:g} … {high:g}]"
    if low is not None:
        return f"≥ {low:g}"
    if high is not None:
        return f"≤ {high:g}"
    return ""


def _reading_lines(dataset: Dataset) -> list[str]:
    lines = []
    for name, array in dataset.arrays.items():
        values = np.asarray(array.values)
        lines.append(
            f"     {name:<24} {values.dtype!s:<10} {values.shape!s:<12} "
            f"{_span(values)}  {array.unit}"
        )
    return lines


def _span(values: np.ndarray) -> str:
    if values.size == 0:
        return "empty"
    try:
        numbers = np.asarray(values, dtype=float).ravel()
    except (TypeError, ValueError):
        # `.item()` rather than `repr`: a numpy string reprs as
        # `np.str_('rabi')`, which is about numpy and not about the
        # instrument.
        first = values.ravel()[0]
        return repr(first.item() if hasattr(first, "item") else first)[:40]
    finite = numbers[np.isfinite(numbers)]
    if finite.size == 0:
        return "all non-finite"
    if finite.size == 1 or finite.min() == finite.max():
        return f"{finite[0]:g}"
    return f"{finite.min():g} … {finite.max():g}"


# --- The command -----------------------------------------------------------


def probe(args: Any) -> int:
    """`labpilot probe` — see the module docstring."""
    from labpilot.instruments import adapter_registry

    say = _printer(args)
    if getattr(args, "all", False) or getattr(args, "config", ""):
        return probe_rig(args)
    if not getattr(args, "adapter_key", ""):
        say(
            "❌ Name an adapter to probe, or use --all to probe every "
            "instrument in your saved instrument set."
        )
        return CANNOT_TELL
    try:
        adapter_cls = adapter_registry.get(args.adapter_key)
    except KeyError:
        say(_unknown_adapter(args.adapter_key))
        return CANNOT_TELL

    try:
        kwargs = _kwargs(args)
    except ValueError as error:
        say(f"❌ {error}")
        return CANNOT_TELL

    try:
        adapter = adapter_cls(**kwargs)
    except TypeError as error:
        # The argument *names* are wrong.
        say(f"❌ {args.adapter_key} rejected those arguments: {error}")
        say(_required(adapter_cls))
        return CANNOT_TELL
    except Exception as error:
        # The argument *values* are wrong — a card model that is not in
        # the table, an axis that does not exist. Just as much "cannot
        # tell" as a bad name, and catching only `TypeError` meant a
        # `--all` run died on the first such instrument instead of
        # reporting it and carrying on.
        say(f"❌ {args.adapter_key} could not be built: "
            f"{type(error).__name__}: {error}")
        if getattr(args, "offline", False):
            # Reviewing a rig on a laptop should not be blocked by an
            # address nobody has filled in yet, so fall back to the
            # schema the adapter describes with placeholder arguments.
            return _describe_only(args, adapter_cls, say)
        return CANNOT_TELL

    return asyncio.run(_probe(adapter, args, say))


async def _probe(adapter: Any, args: Any, say: Any) -> int:
    from labpilot.core.device.capabilities import with_capabilities

    declared = with_capabilities(adapter.schema, adapter)
    report: dict[str, Any] = {
        "adapter_key": args.adapter_key,
        "declared": declared.model_dump(mode="json"),
    }
    say(f"🔎 {args.adapter_key}  —  {type(adapter).__module__}.{type(adapter).__name__}")
    say("")
    say("── declared, with no hardware ──")
    say("\n".join(describe_schema(declared)))

    if getattr(args, "offline", False):
        say("")
        for key, value in kwargs_shown(args):
            say(f"   would connect with {key} = {value!r}")
        say("   (--offline: nothing was connected)")
        return _finish(args, say, report, [], connected=False)

    say("")
    say("── connecting ──")
    for key, value in kwargs_shown(args):
        say(f"   {key} = {value!r}")
    started = time.monotonic()
    try:
        await adapter.connect()
    except Exception as error:
        say(f"   ❌ {type(error).__name__}: {error}")
        say(_connect_hint(error))
        report["error"] = f"{type(error).__name__}: {error}"
        _emit_json(args, say, report)
        return CANNOT_TELL
    say(f"   ✓ connected in {time.monotonic() - started:.2f} s")

    findings: list[Finding] = []
    try:
        live = with_capabilities(adapter.schema, adapter)
        report["live"] = live.model_dump(mode="json")
        changes = compare_schemas(declared, live)
        say("")
        say("── the schema once connected ──")
        if changes:
            say("\n".join(f"   {finding}" for finding in changes))
        else:
            say("   ✓ unchanged")
        findings += changes

        if not getattr(args, "no_read", False):
            say("")
            say("── one reading (nothing is written, nothing moves) ──")
            dataset = await adapter.read()
            say("\n".join(_reading_lines(dataset)))
            report["reading"] = {
                name: np.asarray(array.values).tolist()
                for name, array in dataset.arrays.items()
            }
            mismatches = compare_reading(live, dataset)
            findings += mismatches
            if mismatches:
                say("")
                say("\n".join(f"   {finding}" for finding in mismatches))
            else:
                say("   ✓ every declared readable parameter came back, as declared")
    finally:
        await adapter.disconnect()

    return _finish(args, say, report, findings, connected=True)


def _finish(args, say, report, findings, *, connected: bool) -> int:
    fatal = [f for f in findings if f.fatal]
    report["findings"] = [{"text": f.text, "fatal": f.fatal} for f in findings]
    report["agrees"] = not fatal
    say("")
    if not connected:
        say("── verdict: not tested against hardware ──")
    elif fatal:
        say(f"── verdict: {len(fatal)} disagreement(s) — the schema needs correcting ──")
    else:
        say("── verdict: ✓ the hardware agrees with the declared schema ──")
    _emit_json(args, say, report)
    if not connected:
        return OK
    return DISAGREES if fatal else OK


def _describe_only(args: Any, adapter_cls: type, say: Any) -> int:
    """The schema an adapter describes with no arguments at all.

    `AdapterBase.describe()` constructs a throwaway instance with
    placeholder arguments, which is how all 314 adapters appear in the
    catalogue without hardware. It is the right fallback when the saved
    arguments are not usable yet — the declaration is still worth reading,
    and it is what `--offline` was asked for.
    """
    schema = adapter_cls.describe()
    if schema is None:
        say("   ...and cannot describe itself without arguments either.")
        return CANNOT_TELL
    say("")
    say("── declared, with placeholder arguments ──")
    say("\n".join(describe_schema(schema)))
    say("")
    say("   (--offline: nothing was connected)")
    say("")
    say("── verdict: not tested against hardware ──")
    _emit_json(
        args, say,
        {"adapter_key": args.adapter_key, "declared": schema.model_dump(mode="json")},
    )
    return OK


# --- A whole rig ------------------------------------------------------------


def probe_rig(args: Any) -> int:
    """Probe every instrument in a saved instrument set.

    Each one gets the connection parameters the config holds, so an
    address is written down once — in the config the Devices dialog and
    `labpilot rig-init` both produce — rather than retyped per probe.

    One instrument's failure never stops the others: the point of this
    command is the table at the end, and an unreachable spectrometer
    should not hide a disagreeing counter.
    """
    from labpilot.core.config.instrument_sets import (
        InstrumentSetError,
        InstrumentSetPersistence,
    )

    say = _printer(args)
    store = InstrumentSetPersistence()
    name = getattr(args, "config", "") or store.get_active_name()
    if not name:
        say(
            "❌ No instrument set to probe. Set one up in the Devices tab, or "
            "install a ready-made one:\n"
            "     labpilot rig-templates\n"
            "     labpilot rig-init nv_confocal"
        )
        return CANNOT_TELL
    try:
        specs = store.load(name)
    except InstrumentSetError as error:
        say(f"❌ {error}")
        return CANNOT_TELL
    if not specs:
        say(f"❌ The instrument set {name!r} has no instruments in it.")
        return CANNOT_TELL

    say(f"🔎 Probing every instrument in {name!r} — {len(specs)} of them")
    say("")

    outcomes: list[tuple[str, str, int]] = []
    report: dict[str, Any] = {"config": name, "instruments": {}}
    for spec in specs:
        say("=" * 70)
        one = _for_spec(args, spec)
        try:
            code = probe(one)
        except Exception as error:
            # Belt and braces around the whole point of this command: an
            # unreachable spectrometer must not hide a disagreeing
            # counter, whatever shape its failure takes.
            say(f"❌ {spec.id}: {type(error).__name__}: {error}")
            code = CANNOT_TELL
        outcomes.append((spec.id, spec.adapter_key, code))
        report["instruments"][spec.id] = {"adapter_key": spec.adapter_key, "exit": code}
        say("")

    # An offline run tested nothing, so it must not report agreement.
    # Saying "every instrument agrees" after connecting to none of them
    # is the exact false reassurance this command exists to avoid.
    offline = bool(getattr(args, "offline", False))
    verdicts = _OFFLINE_VERDICT if offline else _VERDICT

    say("=" * 70)
    say(f"── {name}: {len(outcomes)} instruments ──")
    width = max(len(identifier) for identifier, _, _ in outcomes)
    for identifier, adapter_key, code in outcomes:
        say(f"   {verdicts[code]}  {identifier:<{width}}  {adapter_key}")
    worst = max(code for _, _, code in outcomes)
    say("")
    if offline:
        say("   Nothing was connected. Drop --offline to check these against "
            "the hardware.")
    elif worst == OK:
        say("   ✓ every instrument agrees with its declared schema")
    else:
        say("   Nothing was written and nothing moved.")
    report["offline"] = offline
    _emit_json(args, say, report)
    return worst


_VERDICT = {OK: "✓ agrees    ", DISAGREES: "✗ disagrees ", CANNOT_TELL: "· unreachable"}
_OFFLINE_VERDICT = {
    OK: "· declared  ",
    DISAGREES: "✗ disagrees ",
    CANNOT_TELL: "· unreadable",
}


def _for_spec(args: Any, spec: Any) -> Any:
    """One instrument's probe arguments, from its saved spec.

    `--param` on a `--all` run is deliberately not merged in: it would
    apply the same value to every instrument, which is never what was
    meant.
    """
    import argparse

    connection = dict(spec.connection or {})
    return argparse.Namespace(
        adapter_key=spec.adapter_key,
        resource=connection.pop("resource", None),
        param=[f"{key}={value}" for key, value in connection.items()],
        offline=getattr(args, "offline", False),
        no_read=getattr(args, "no_read", False),
        json=False,
        quiet=getattr(args, "json", False),
        all=False,
        config="",
    )


# --- Arguments --------------------------------------------------------------


def _kwargs(args: Any) -> dict[str, Any]:
    """`--resource` plus any `--param name=value`, each coerced if it parses.

    A bare string is the fallback rather than an error: VISA resource
    strings, serial ports and camera indices all arrive as text, and
    guessing wrong about an int is worse than passing the text an adapter
    already knows how to read.
    """
    kwargs: dict[str, Any] = {}
    if getattr(args, "resource", None):
        kwargs["resource"] = args.resource
    for item in getattr(args, "param", None) or []:
        name, sep, raw = item.partition("=")
        if not sep:
            raise ValueError(f"--param wants name=value, got {item!r}")
        kwargs[name.strip()] = _coerce(raw)
    return kwargs


def kwargs_shown(args: Any) -> list[tuple[str, Any]]:
    return sorted(_kwargs(args).items())


def _coerce(raw: str) -> Any:
    text = raw.strip()
    for parse in (int, float):
        try:
            return parse(text)
        except ValueError:
            continue
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered == "none":
        return None
    return text


def _required(adapter_cls: type) -> str:
    import inspect

    try:
        signature = inspect.signature(adapter_cls.__init__)
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return ""
    needed = [
        name
        for name, parameter in signature.parameters.items()
        if name != "self"
        and parameter.default is inspect.Parameter.empty
        and parameter.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    if not needed:
        return "   It takes no required arguments."
    pairs = " ".join(
        "--resource …" if name == "resource" else f"--param {name}=…" for name in needed
    )
    return f"   It needs: {', '.join(needed)}\n   e.g.  {pairs}"


def _unknown_adapter(key: str) -> str:
    import difflib

    from labpilot.instruments import adapter_registry

    keys = sorted(adapter_registry.list())
    close = difflib.get_close_matches(key, keys, n=5, cutoff=0.4)
    hint = f"\n   Did you mean: {', '.join(close)}" if close else ""
    return (
        f"❌ No adapter registered as {key!r} on this machine.{hint}\n"
        f"   {len(keys)} are available — `labpilot list-adapters` lists them."
    )


def _connect_hint(error: Exception) -> str:
    """Separate "the driver isn't installed" from "the device isn't there".

    Every adapter here imports its vendor SDK inside `_connect_sync`, not
    at module level, so a missing package surfaces exactly here and is by
    far the most common first failure on a fresh lab PC.
    """
    text = str(error).lower()
    missing = isinstance(error, ImportError) or any(
        phrase in text
        for phrase in ("no module named", "install", "visa implementation", "not installed")
    )
    if missing:
        return (
            "   This reads as a missing driver package rather than a missing\n"
            "   instrument — nothing was reached. Install what the message names\n"
            "   and probe again; `--offline` works without it."
        )
    return (
        "   The adapter was built and then refused the connection, so the\n"
        "   address is the thing to check first. `--offline` prints the\n"
        "   declared schema without connecting."
    )


def _printer(args: Any):
    # `quiet` and `json` are separate: on a `--all` run the parent emits
    # one JSON report and the children must stay silent, so they are told
    # to be quiet without being told to emit anything.
    quiet = getattr(args, "json", False) or getattr(args, "quiet", False)

    def say(text: str) -> None:
        if not quiet:
            print(text, flush=True)

    return say


def _emit_json(args: Any, say: Any, report: dict[str, Any]) -> None:
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2, default=str))
