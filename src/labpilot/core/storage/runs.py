"""Automatic persistence: every run lands on disk, indexed.

This closes the gap `ARCHITECTURE_NOTES.md` §4.5 called "the single most
concrete, closest-to-done gap". Two components had been written and wired
to nothing:

- `storage/hdf5.py`'s `HDF5Writer` subscribed to `DESCRIPTOR`/`READING`,
  the event stream of `core/plans/scan.py` — an orphaned engine no REST
  route reaches. It had zero importers, and its `start()` never returned
  (an un-exited task group). It is deleted; this module replaces it.
- `storage/catalogue.py`'s `Catalogue`, the provenance index, was
  constructed nowhere. It is constructed here.

Meanwhile the only real persistence was a File->Save button inside the Qt
app, whose own docstring explains it could not reuse `HDF5Writer` because
the engine emits a structurally different event — and a full N-D array
JSON-encoded into a SQLite TEXT column.

What made this possible now is `Dataset`: there was previously no
self-describing object to write. A template still returns a plain dict;
`Dataset.from_result` lifts it, and what lands is real HDF5 with units,
dtypes and axis coordinates as HDF5 dimension scales.

## When a run is saved

At completion, and also on cancellation or failure, from the last
progress frame — stopping a long scan should not throw the data away. A
partial run is saved with `status` recorded and its untaken points as
NaN, which is what "not measured" means to every reader of the file.

Deliberately *not* streamed point-by-point to disk. Today's progress
frames carry the whole accumulated array, so writing each one would
rewrite the file per point; incremental writing wants `DatasetPatch` on
the run stream, which is the next step, not this one.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import h5py

from labpilot.core.config.paths import labpilot_home
from labpilot.core.storage.catalogue import Catalogue

if TYPE_CHECKING:
    from labpilot.core.data.dataset import Dataset

__all__ = ["RunStore", "run_data_dir"]


def run_data_dir() -> Path:
    """Where run files are written — `$LABPILOT_HOME/data`.

    Honours `LABPILOT_HOME` like the rest of the persistent state, so a
    test session writes into its own temporary tree instead of the
    developer's real one.
    """
    return labpilot_home() / "data"


def _safe(name: str) -> str:
    """A filename fragment from arbitrary text."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return cleaned.strip("_")[:64] or "run"


class RunStore:
    """Writes each completed run to HDF5 and indexes it in the catalogue.

    Failures never propagate to the run: a scan that acquired real data
    must not be reported as failed because the disk was full. They are
    reported and recorded instead — the previous behaviour was to save
    nothing at all, silently, which is what this replaces.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else run_data_dir()
        self.catalogue_path = self.root / "catalogue.db"
        self.last_error: str | None = None

    @asynccontextmanager
    async def _catalogue(self):
        """A catalogue connection for the duration of one operation.

        Deliberately not held open. `aiosqlite` runs each connection on its
        own **non-daemon** thread, so a connection nobody closes keeps the
        interpreter alive at exit — the process finishes its work and then
        hangs in `threading._shutdown`. One row is written per completed
        scan and listings are on request, so connecting per operation costs
        nothing measurable and removes a whole class of shutdown bug.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        catalogue = Catalogue(self.catalogue_path)
        await catalogue.connect()
        try:
            yield catalogue
        finally:
            await catalogue.disconnect()

    async def save(
        self,
        dataset: Dataset,
        *,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> Path | None:
        """Write `dataset` and index it. Returns the file path, or None if
        the run could not be saved (the reason lands in `last_error`)."""
        try:
            path = await anyio.to_thread.run_sync(self._write, dataset)
        except Exception as e:
            self.last_error = f"HDF5 write failed: {e}"
            print(f"⚠️  Run {dataset.meta.run_uid[:8]} not saved: {e}")
            return None

        try:
            await self._index(dataset, path, status, metadata or {})
        except Exception as e:
            # The data is on disk; only its index entry is missing, so the
            # run is still recoverable and this is not worth failing over.
            self.last_error = f"catalogue update failed: {e}"
            print(f"⚠️  Run {dataset.meta.run_uid[:8]} saved to {path} but not indexed: {e}")

        return path

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Most recent runs first."""
        if not self.catalogue_path.exists():
            return []
        async with self._catalogue() as catalogue:
            return await catalogue.search(limit=limit)

    async def get_run(self, run_uid: str) -> dict[str, Any] | None:
        """One run's catalogue row, including the path to its file.

        Listing was the only way in, which meant finding a run older than
        the listing's limit was impossible — and the row is what says
        where the data actually is.
        """
        if not self.catalogue_path.exists():
            return None
        async with self._catalogue() as catalogue:
            return await catalogue.get_run(run_uid)

    # --- Internals --------------------------------------------------------

    def _path_for(self, dataset: Dataset) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(dataset.meta.timestamp))
        day = time.strftime("%Y/%m", time.localtime(dataset.meta.timestamp))
        uid = dataset.meta.run_uid[:8] or "run"
        directory = self.root / day
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{stamp}_{_safe(dataset.meta.plan_name)}_{uid}.h5"

    def _write(self, dataset: Dataset) -> Path:
        """One file, written by one writer.

        The plan parameters and the device schemas used to be added here,
        after `to_hdf5` had written everything else — so an auto-saved run
        carried them and `dataset.to_hdf5("rabi.h5")` from the console did
        not. A file someone emails is exactly the one that needs to say
        what the sweep bounds were, so `to_hdf5` writes them now and this
        only chooses the path and stamps the format.
        """
        path = self._path_for(dataset)
        with h5py.File(path, "w") as f:
            f.attrs["created_with"] = "LabPilot"
            f.attrs["format_version"] = "2.0"
            dataset.to_hdf5(f.create_group("run"))
        return path

    async def _index(
        self, dataset: Dataset, path: Path, status: str, metadata: dict[str, Any]
    ) -> None:
        primary = dataset.primary() if dataset.arrays else None
        async with self._catalogue() as catalogue:
            await catalogue.add_run(
                run_uid=dataset.meta.run_uid,
                plan_name=dataset.meta.plan_name,
                metadata={
                    "status": status,
                    "shape": list(primary.shape) if primary is not None else [],
                    "arrays": list(dataset.arrays),
                    "axes": [axis.name for axis in dataset.axes()] if primary is not None else [],
                    **metadata,
                },
                data_path=path,
                timestamp=dataset.meta.timestamp,
            )
