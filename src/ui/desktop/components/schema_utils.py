"""Pure DeviceSchema-parsing helpers shared by the generic window and its
components. Relocated from instrument_windows.py unchanged.
"""

from __future__ import annotations

from typing import Optional

from backend_client import BackendClient

_AXIS_KEY_HINTS = ("wavelength", "wavelengths", "time", "times", "frequency", "frequencies", "x")


def primary_key(schema: dict) -> Optional[str]:
    """First readable key — what a single-value/image/ND window displays."""
    keys = list(schema.get("readable", {}).keys())
    return keys[0] if keys else None


def pick_1d_series(schema: dict) -> tuple:
    """(value_key, axis_key) for a 1D detector's plot. Some real spectrometer
    schemas expose both an axis array (wavelengths, time, ...) and a value
    array (intensities, ...) as separate readable keys — plotting the axis
    key against a bare sample index (what picking "the first readable key"
    would do) is a meaningless straight ramp. When both are present, plot
    the non-axis key against the axis key instead of against sample index."""
    readable = schema.get("readable", {})
    array_keys = [k for k, dtype in readable.items() if dtype == "ndarray1d"]
    if not array_keys:
        keys = list(readable.keys())
        return (keys[0] if keys else None, None)
    axis_key = next((k for k in array_keys if k.lower() in _AXIS_KEY_HINTS), None)
    value_key = next((k for k in array_keys if k != axis_key), array_keys[0])
    return value_key, axis_key


def fetch_schema(client: BackendClient, instrument_id: str) -> dict:
    """Best-effort schema fetch; returns an empty schema on failure rather
    than raising, since a window should still open (just without units/
    limits) if the backend hiccups for a moment."""
    try:
        return client.get_schema(instrument_id)
    except Exception as e:
        print(f"[InstrumentWindow] Failed to fetch schema for {instrument_id}: {e}")
        return {"readable": {}, "settable": {}, "units": {}, "limits": {}}


def config_only_names(schema: dict) -> list[str]:
    """Settable-but-not-readable param names — connection/config knobs like
    'integration_time_ms' or 'velocity', as opposed to live controls like an
    actuator's 'position'. Same heuristic as the frontend's `configNames()`
    in InstrumentSettingsModal/index.tsx, so the native Settings dock and
    the React settings modal always agree on what counts as "config"."""
    readable = schema.get("readable", {})
    return [k for k in schema.get("settable", {}) if k not in readable]


def main_config_names(kind: str, dimensionality: str, schema: dict) -> list[str]:
    """This instrument's "main" config-only names for its native Settings
    dock. A 0D detector's basic control is just its integration time
    (matched by substring — adapters name it integration_time,
    integration_time_ms, etc. — the same convention
    core/workflow_templates/_common.py's `integration_time_key` uses on
    the backend side); anything else a specific 0D adapter also declares
    settable (e.g. a mock's own simulation-tuning knobs) is manufacturer/
    fixture-specific noise, not a real detector setting, so it's left out
    here. Every other kind/dimensionality shows all of `config_only_names`
    unchanged — manufacturer-specific extras (a camera's real hardware
    settings beyond exposure/gain, say) are meant to show up here
    automatically, not just the generic ones."""
    names = config_only_names(schema)
    if kind == "detector" and dimensionality == "0D":
        return [n for n in names if "integration_time" in n]
    return names


def move_axes(schema: dict, kind: str = "motor") -> list[str]:
    """Axis names an actuator's move-control should expose: prefer
    readable+settable *continuous* axes (positions you can both read back
    and command) — a bool readable+settable key is never a continuous move
    axis, it's either a source's separate enable/output-on flag (handled by
    MoveControlComponent's own enable_key logic) or, if it's the only key
    at all, a genuine 2-state switch (handled by the states/_build_switch
    path via the fallback below). Excluding it here keeps a source's
    "power" + "enabled" pair from being mistaken for two tabbed axes.
    Falls back to whatever's readable if nothing settable+non-bool exists
    (shouldn't happen for a real actuator, but keeps the window from
    crashing on a malformed schema) — EXCEPT for a source (`kind ==
    "source"`), where that fallback would dump plain status fields (a
    microwave source's `mode`/`output_on`/`scan_index`, say) in as fake
    move targets; a source with no genuine overlapping axis just gets no
    move-control dock at all (see MoveControlComponent.build())."""
    readable = schema.get("readable", {})
    settable = schema.get("settable", {})
    axes = [k for k in readable if k in settable and settable[k] != "bool"]
    if axes:
        return axes
    if kind == "source":
        return []
    return [k for k in readable if k not in settable] or list(readable.keys())
