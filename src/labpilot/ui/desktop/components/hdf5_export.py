"""Saves a workflow's completed result to a real HDF5 file — closing the
gap identified in ARCHITECTURE_NOTES.md's save/export comparison: the
scanner GUI's own "Save"/"Save All Scans" only ever exported a PNG
snapshot of the current view, never the actual numbers, unlike qudi's
text/CSV/NPY storage or pyMoDAQ's HDF5 pipeline.

`core/storage/hdf5.py`'s existing `HDF5Writer` was NOT reused here on
purpose — it subscribes to `EventKind.DESCRIPTOR`/`EventKind.READING`
events, a Bluesky-inspired document model an *older*, separate
`Session.run(plan)` scan-execution path emits. The workflow engine actual
templates (omniscan.py etc.) run through today — `session.report_progress()`
— emits `EventKind.WORKFLOW_PROGRESS` instead, a structurally different,
much more free-form event shape (whatever dict keys a given template
happens to report). Adapting `HDF5Writer` to that would mean rewriting
most of its internals anyway, so this is a small, purpose-built saver
matching the *actual* current data model directly, informed by
`HDF5Writer`'s chunking/compression/attrs conventions rather than
inheriting its mismatched event plumbing.

Runs synchronously on the Qt GUI thread (h5py is not async) — acceptable
here since saving happens once, on an explicit user action (a button
click), not continuously during acquisition the way `HDF5Writer` was
designed for.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import h5py
import numpy as np

__all__ = ["save_workflow_result_hdf5"]


def save_workflow_result_hdf5(
    path: str,
    workflow_id: str,
    workflow_name: str,
    result_ui: dict,
    results: dict,
    instrument_bindings: Optional[dict] = None,
) -> None:
    """Writes one HDF5 file for a workflow's completed result.

    `result_ui` is the RESULT_UI spec (see core/workflow/instrument_roles.py)
    telling this which keys in `results` (a workflow's `last_results`,
    from GET .../execution_state) hold what. `instrument_bindings` (role ->
    real instrument id) is recorded as metadata so the file is
    self-describing about what produced it.
    """
    kind = result_ui.get("type")
    with h5py.File(path, "w") as f:
        f.attrs["created_with"] = "LabPilot"
        f.attrs["format_version"] = "1.0"
        f.attrs["workflow_id"] = workflow_id
        f.attrs["workflow_name"] = workflow_name
        f.attrs["result_type"] = kind or ""
        f.attrs["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if instrument_bindings:
            f.attrs["instrument_bindings"] = json.dumps(instrument_bindings)

        if kind == "ndscan":
            _write_ndscan(f, result_ui, results)
        elif kind == "image2d":
            _write_image2d(f, result_ui, results)
        elif kind == "spectrum":
            _write_spectrum(f, result_ui, results)
        elif kind == "odmr":
            _write_odmr(f, result_ui, results)
        else:
            # Unknown/absent RESULT_UI type — fall back to dumping every
            # plain scalar/array value present so nothing is silently lost.
            _write_generic(f, results)


def _write_ndscan(f: h5py.File, result_ui: dict, results: dict) -> None:
    value_key = result_ui.get("value_key")
    shape_key = result_ui.get("shape_key")
    axis_names_key = result_ui.get("axis_names_key")
    axis_positions_key = result_ui.get("axis_positions_key")
    actuator_axis_count_key = result_ui.get("actuator_axis_count_key")

    flat_data = results.get(value_key)
    shape = results.get(shape_key)
    axis_names = results.get(axis_names_key) or []
    axis_positions = results.get(axis_positions_key) or []
    if not flat_data or not shape:
        return

    array = np.array([np.nan if v is None else float(v) for v in flat_data], dtype=float).reshape(shape)
    f.create_dataset("data", data=array, compression="gzip")
    f.attrs["axis_names"] = json.dumps(list(axis_names))
    if actuator_axis_count_key and actuator_axis_count_key in results:
        f.attrs["actuator_axis_count"] = int(results[actuator_axis_count_key])

    axes_group = f.create_group("axes")
    for name, positions in zip(axis_names, axis_positions):
        axes_group.create_dataset(name, data=np.asarray(positions, dtype=float))


def _write_image2d(f: h5py.File, result_ui: dict, results: dict) -> None:
    value_key = result_ui.get("value_key")
    x_key = result_ui.get("x_key")
    y_key = result_ui.get("y_key")
    value_2d = results.get(value_key)
    if not value_2d:
        return
    rows = [[np.nan if v is None else float(v) for v in row] for row in value_2d]
    f.create_dataset("data", data=np.array(rows, dtype=float), compression="gzip")
    if results.get(x_key):
        f.create_dataset("x", data=np.asarray(results[x_key], dtype=float))
    if results.get(y_key):
        f.create_dataset("y", data=np.asarray(results[y_key], dtype=float))


def _write_spectrum(f: h5py.File, result_ui: dict, results: dict) -> None:
    x_key = result_ui.get("x_key")
    y_key = result_ui.get("y_key")
    if results.get(x_key):
        f.create_dataset("x", data=np.asarray(results[x_key], dtype=float))
    if results.get(y_key):
        f.create_dataset("y", data=np.asarray(results[y_key], dtype=float))

    # Optional fit overlay (see odmr_sweep.py) — dropped entirely before
    # this, even though the template already computed it.
    fit_x_key = result_ui.get("fit_x_key")
    fit_y_key = result_ui.get("fit_y_key")
    if results.get(fit_x_key):
        f.create_dataset("fit_x", data=np.asarray(results[fit_x_key], dtype=float))
    if results.get(fit_y_key):
        f.create_dataset("fit_y", data=np.asarray(results[fit_y_key], dtype=float))
    fit = results.get("fit")
    if isinstance(fit, dict):
        for key, value in fit.items():
            if isinstance(value, (int, float)):
                f.attrs[f"fit_{key}"] = value


def _write_odmr(f: h5py.File, result_ui: dict, results: dict) -> None:
    """`RESULT_UI["type"] == "odmr"` (odmr_sweep.py) — the averaged
    spectrum + fit (same as `_write_spectrum`) plus the per-repeat raw
    accumulation matrix qudi's own ODMR GUI shows below the spectrum."""
    _write_spectrum(f, result_ui, results)
    matrix_key = result_ui.get("matrix_key")
    matrix = results.get(matrix_key)
    if matrix:
        f.create_dataset("matrix", data=np.asarray(matrix, dtype=float), compression="gzip")
    repeat_key = result_ui.get("repeat_key")
    if repeat_key and results.get(repeat_key) is not None:
        f.attrs["repeats_done"] = results[repeat_key]


def _write_generic(f: h5py.File, results: dict) -> None:
    for key, value in results.items():
        if isinstance(value, (int, float, bool)):
            f.attrs[key] = value
        elif isinstance(value, str):
            f.attrs[key] = value
        elif isinstance(value, (list, tuple)) and value and isinstance(value[0], (int, float)):
            f.create_dataset(key, data=np.asarray(value, dtype=float))
        # Anything else (nested dicts/lists of non-numeric data) is
        # skipped here rather than guessed at — RESULT_UI-typed results
        # above cover every real template's actual shape.
