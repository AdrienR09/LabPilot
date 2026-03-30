"""HDF5 writer for streaming scan data storage.

Subscribes to EventBus and writes data to chunked HDF5 files using h5py.
Supports xarray integration for labeled arrays with coordinate axes.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import anyio
import h5py
import numpy as np

from labpilot_core.core.events import EventBus, EventKind

__all__ = ["HDF5Writer"]


class HDF5Writer:
    """Event-driven HDF5 writer with xarray metadata support.

    Subscribes to EventBus and writes READING events to HDF5 file in real-time.
    Creates datasets with chunking for efficient streaming and compression.

    Example:
        >>> writer = HDF5Writer(path="data/scan_001.h5")
        >>> await writer.start(bus)
        >>> # Scan runs, writer receives events automatically
        >>> await writer.stop()
    """

    def __init__(
        self,
        path: str | Path,
        compression: str = "gzip",
        chunk_size: int = 100,
    ) -> None:
        """Initialize HDF5 writer.

        Args:
            path: Output HDF5 file path.
            compression: HDF5 compression filter ("gzip", "lzf", None).
            chunk_size: Number of points per chunk (for streaming writes).
        """
        self.path = Path(path)
        self.compression = compression
        self.chunk_size = chunk_size
        self._file: h5py.File | None = None
        self._run_group: h5py.Group | None = None
        self._datasets: dict[str, h5py.Dataset] = {}
        self._point_count = 0
        self._task: anyio.abc.CancelScope | None = None

    async def start(self, bus: EventBus) -> None:
        """Start listening to event bus and writing data.

        Opens HDF5 file and subscribes to DESCRIPTOR and READING events.

        Args:
            bus: EventBus to subscribe to.

        Raises:
            RuntimeError: If already started.
        """
        if self._file is not None:
            raise RuntimeError("Writer already started")

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Open HDF5 file in thread (h5py is not async-safe)
        await anyio.to_thread.run_sync(self._open_file)

        # Start event subscription task
        async def _subscription_loop() -> None:
            """Subscribe to events and write data."""
            async for event in bus.subscribe(EventKind.DESCRIPTOR, EventKind.READING):
                try:
                    if event.kind == EventKind.DESCRIPTOR:
                        await self._handle_descriptor(event.data, event.run_uid)
                    elif event.kind == EventKind.READING:
                        await self._handle_reading(event.data)
                except Exception as e:
                    # Log error but continue listening
                    print(f"HDF5 writer error: {e}")

        # Run subscription in background task group
        async with anyio.create_task_group() as tg:
            tg.start_soon(_subscription_loop)
            self._task = tg.cancel_scope

    async def stop(self) -> None:
        """Stop listening to events and close HDF5 file.

        Flushes all pending writes and closes file handle.
        """
        if self._task is not None:
            self._task.cancel()
            self._task = None

        if self._file is not None:
            await anyio.to_thread.run_sync(self._close_file)

    def _open_file(self) -> None:
        """Open HDF5 file (blocking, runs in thread)."""
        self._file = h5py.File(self.path, "w")

        # Write root-level metadata
        self._file.attrs["created_with"] = "LabPilot"
        self._file.attrs["format_version"] = "1.0"

    def _close_file(self) -> None:
        """Close HDF5 file (blocking, runs in thread)."""
        if self._file is not None:
            self._file.close()
            self._file = None

    async def _handle_descriptor(self, data: dict[str, Any], run_uid: str | None) -> None:
        """Handle DESCRIPTOR event - create run group and datasets.

        Args:
            data: Descriptor event data dict.
            run_uid: Run UUID string.
        """
        if run_uid is None:
            run_uid = str(uuid.uuid4())

        await anyio.to_thread.run_sync(self._create_run_group, data, run_uid)

    def _create_run_group(self, data: dict[str, Any], run_uid: str) -> None:
        """Create HDF5 group for this run (blocking, runs in thread).

        Args:
            data: Descriptor event data dict.
            run_uid: Run UUID string.
        """
        if self._file is None:
            return

        # Create run group
        self._run_group = self._file.create_group(run_uid)
        self._run_group.attrs["run_uid"] = run_uid

        # Store plan metadata
        if "plan" in data:
            plan_group = self._run_group.create_group("plan")
            for key, value in data["plan"].items():
                if isinstance(value, dict):
                    # Store nested dicts as JSON string
                    import json

                    plan_group.attrs[key] = json.dumps(value)
                else:
                    plan_group.attrs[key] = value

        # Store device schemas
        if "motor_schema" in data:
            motor_group = self._run_group.create_group("motor_schema")
            for key, value in data["motor_schema"].items():
                if isinstance(value, (dict, list)):
                    import json

                    motor_group.attrs[key] = json.dumps(value)
                else:
                    motor_group.attrs[key] = value

        if "detector_schema" in data:
            detector_group = self._run_group.create_group("detector_schema")
            for key, value in data["detector_schema"].items():
                if isinstance(value, (dict, list)):
                    import json

                    detector_group.attrs[key] = json.dumps(value)
                else:
                    detector_group.attrs[key] = value

        # Create data group for readings
        self._data_group = self._run_group.create_group("data")
        self._datasets = {}
        self._point_count = 0

    async def _handle_reading(self, data: dict[str, Any]) -> None:
        """Handle READING event - write data to datasets.

        Args:
            data: Reading event data dict.
        """
        await anyio.to_thread.run_sync(self._write_reading, data)

    def _write_reading(self, data: dict[str, Any]) -> None:
        """Write reading data to HDF5 datasets (blocking, runs in thread).

        Args:
            data: Reading event data dict with various data fields.
        """
        if self._run_group is None:
            return

        # Create datasets on first reading (now know data shapes/types)
        if not self._datasets:
            for key, value in data.items():
                if isinstance(value, np.ndarray):
                    # Create resizeable dataset for arrays
                    maxshape = (None,) + value.shape  # Infinite first dim
                    self._datasets[key] = self._data_group.create_dataset(
                        key,
                        shape=(0,) + value.shape,
                        maxshape=maxshape,
                        dtype=value.dtype,
                        chunks=(self.chunk_size,) + value.shape,
                        compression=self.compression,
                    )
                else:
                    # Create resizeable dataset for scalars
                    dtype = np.array(value).dtype
                    self._datasets[key] = self._data_group.create_dataset(
                        key,
                        shape=(0,),
                        maxshape=(None,),
                        dtype=dtype,
                        chunks=(self.chunk_size,),
                        compression=self.compression,
                    )

        # Write data to datasets
        for key, value in data.items():
            if key not in self._datasets:
                continue  # Skip unknown keys

            dataset = self._datasets[key]

            # Resize dataset to accommodate new point
            current_size = dataset.shape[0]
            dataset.resize(current_size + 1, axis=0)

            # Write data
            if isinstance(value, np.ndarray):
                dataset[current_size] = value
            else:
                dataset[current_size] = value

        self._point_count += 1

        # Flush to disk periodically (every 10 points)
        if self._point_count % 10 == 0 and self._file is not None:
            self._file.flush()
