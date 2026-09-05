"""Pure numpy computation for NDScanResultView's projections — no Qt or
pyqtgraph dependency, deliberately, so it's safe to call from a background
QThread (see workflow_result.py's _NDProjectionWorker).

Extracted from what used to be inline logic directly inside update_data()/
_refresh_projections()/_compute_1d_projection() on NDScanResultView. Those
ran on the Qt GUI thread — for a large ND scan (tens of millions of
elements), the flat-list-to-ndarray conversion alone measured ~0.1-0.2s
per ~5M elements even in the fast (no-None) case, and every 2D panel and
every Channels-dock tab each additionally does a full np.take/nanmean
reduction over the whole array. None of that logic changed here — it's
copied verbatim from the original methods — only moved to plain functions
that take/return numpy arrays and plain Python containers, nothing Qt-
owned, so a worker thread can run it while numpy has released the GIL
without ever touching a widget off the GUI thread.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def parse_flat_data(flat_data, shape) -> Optional[np.ndarray]:
    """Flat list (floats and/or None, row-major) -> reshaped float64
    ndarray (NaN wherever the source had None). None if the list's length
    doesn't match `shape`'s product (a mid-scan partial frame whose size
    doesn't match its own declared shape yet) or it isn't parseable at
    all.

    `None not in flat_data` is a fast, single vectorizable-ish scan (still
    O(n) but implemented in C, not a Python loop) — when it's False (the
    common case once a scan is mostly/fully complete), skips straight to
    np.array() instead of building an intermediate generator/list, which
    is the single biggest cost in this function for a large array.
    """
    try:
        if None not in flat_data:
            values = np.array(flat_data, dtype=float)
        else:
            values = np.fromiter(
                (np.nan if v is None else v for v in flat_data), dtype=float, count=len(flat_data)
            )
    except (TypeError, ValueError):
        return None
    if values.size != int(np.prod(shape)):
        return None
    return values.reshape(shape)


def _select_indices(positions: list, selection: Optional[tuple]) -> list[int]:
    """Indices of `positions` inside `selection` (lo, hi) — every index if
    `selection` is None (no explicit range yet) or nothing falls inside
    it. Same fallback semantics the original inline code used."""
    lo, hi = selection if selection is not None else (min(positions), max(positions))
    keep = [k for k, p in enumerate(positions) if lo <= p <= hi]
    return keep or list(range(len(positions)))


def compute_panel_projection(
    array: np.ndarray,
    active: list[str],
    name_i: str,
    name_j: str,
    axis_positions: dict[str, list],
    selections: dict[str, tuple],
) -> Optional[np.ndarray]:
    """One 2D axis-pair projection (a single `_ScanImagePanel`'s image) —
    `array` sliced to every OTHER axis's current selection, then
    nanmean-reduced over everything except `name_i`/`name_j`. None if
    either axis isn't part of `active` (this pair wasn't in the most
    recent run)."""
    if name_i not in active or name_j not in active:
        return None
    pos_i, pos_j = active.index(name_i), active.index(name_j)
    sliced = array
    for axis_idx, name in enumerate(active):
        if name in (name_i, name_j):
            continue
        positions = axis_positions.get(name) or list(range(array.shape[axis_idx]))
        sliced = np.take(sliced, _select_indices(positions, selections.get(name)), axis=axis_idx)
    other_axes = tuple(k for k in range(len(active)) if k not in (pos_i, pos_j))
    projected = np.nanmean(sliced, axis=other_axes) if other_axes else sliced
    # `active`'s order (not necessarily name_i-before-name_j) determines
    # which of the two remaining axes np.nanmean left first — transpose
    # back to the (name_i, name_j) = (rows, cols) convention the panel's
    # x/y labels and set_extent() call assume.
    if pos_i > pos_j:
        projected = projected.T
    return projected


def compute_1d_projection(
    array: np.ndarray,
    active: list[str],
    name: str,
    axis_positions: dict[str, list],
    selections: dict[str, tuple],
) -> tuple[list[float], list[float]]:
    """`name`'s own data, averaged over every OTHER axis's current
    selection — same slice-then-nanmean logic as compute_panel_projection,
    just leaving one axis unreduced instead of two. Empty lists if `name`
    isn't part of `active`."""
    if name not in active:
        return [], []
    axis_idx = active.index(name)
    sliced = array
    for idx, other_name in enumerate(active):
        if other_name == name:
            continue
        positions = axis_positions.get(other_name) or list(range(array.shape[idx]))
        sliced = np.take(sliced, _select_indices(positions, selections.get(other_name)), axis=idx)
    other_axes = tuple(k for k in range(len(active)) if k != axis_idx)
    projected = np.nanmean(sliced, axis=other_axes) if other_axes else sliced
    return axis_positions.get(name, list(range(array.shape[axis_idx]))), projected.tolist()
