"""SQLite metadata catalogue for scan runs.

Provides searchable index of all scans with metadata (sample, user, timestamps,
parameters) for easy data discovery and provenance tracking.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

__all__ = ["Catalogue"]


class Catalogue:
    """SQLite-based metadata catalogue for scan runs.

    Stores run metadata in searchable database separate from HDF5 files.
    Enables fast queries across many runs without opening data files.

    Example:
        >>> cat = Catalogue("data/catalogue.db")
        >>> await cat.connect()
        >>> await cat.add_run(
        ...     run_uid="abc123",
        ...     plan_name="wavelength_scan",
        ...     metadata={"sample": "fiber_01", "user": "alice"},
        ... )
        >>> results = await cat.search(sample="fiber_01")
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize catalogue.

        Args:
            path: Path to SQLite database file.
        """
        self.path = Path(path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to database and create schema if needed.

        Creates 'runs' table with columns:
        - run_uid (TEXT PRIMARY KEY)
        - timestamp (REAL)
        - plan_name (TEXT)
        - metadata (TEXT, JSON-encoded dict)
        - data_path (TEXT, path to HDF5 file)
        """
        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self.path)

        # Create schema
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_uid TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                plan_name TEXT,
                metadata TEXT,
                data_path TEXT
            )
            """
        )

        # Create indices for fast queries
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON runs(timestamp)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_name ON runs(plan_name)"
        )

        await self._db.commit()

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def add_run(
        self,
        run_uid: str,
        plan_name: str,
        metadata: dict[str, Any] | None = None,
        data_path: str | Path | None = None,
        timestamp: float | None = None,
    ) -> None:
        """Add run to catalogue.

        Args:
            run_uid: Run UUID string.
            plan_name: Name of scan plan executed.
            metadata: User-defined metadata dict.
            data_path: Path to HDF5 data file.
            timestamp: Unix timestamp (defaults to current time).

        Raises:
            RuntimeError: If not connected to database.
        """
        if self._db is None:
            raise RuntimeError("Not connected to database")

        if timestamp is None:
            timestamp = time.time()

        metadata_json = json.dumps(metadata or {})
        data_path_str = str(data_path) if data_path else None

        await self._db.execute(
            """
            INSERT OR REPLACE INTO runs
            (run_uid, timestamp, plan_name, metadata, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_uid, timestamp, plan_name, metadata_json, data_path_str),
        )
        await self._db.commit()

    async def get_run(self, run_uid: str) -> dict[str, Any] | None:
        """Retrieve run metadata by UID.

        Args:
            run_uid: Run UUID string.

        Returns:
            Dict with run metadata, or None if not found.

        Raises:
            RuntimeError: If not connected to database.
        """
        if self._db is None:
            raise RuntimeError("Not connected to database")

        async with self._db.execute(
            "SELECT * FROM runs WHERE run_uid = ?", (run_uid,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        return {
            "run_uid": row[0],
            "timestamp": row[1],
            "plan_name": row[2],
            "metadata": json.loads(row[3]),
            "data_path": row[4],
        }

    async def search(
        self,
        plan_name: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 100,
        **metadata_filters: Any,
    ) -> list[dict[str, Any]]:
        """Search runs by metadata.

        Args:
            plan_name: Filter by plan name (exact match).
            start_time: Minimum timestamp (Unix time).
            end_time: Maximum timestamp (Unix time).
            limit: Maximum number of results to return.
            **metadata_filters: Metadata key-value pairs to filter on.

        Returns:
            List of run metadata dicts, newest first.

        Raises:
            RuntimeError: If not connected to database.

        Example:
            >>> results = await cat.search(
            ...     plan_name="wavelength_scan",
            ...     start_time=time.time() - 86400,  # Last 24 hours
            ...     sample="fiber_01",  # Custom metadata filter
            ... )
        """
        if self._db is None:
            raise RuntimeError("Not connected to database")

        # Build query
        conditions = []
        params = []

        if plan_name is not None:
            conditions.append("plan_name = ?")
            params.append(plan_name)

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)

        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT * FROM runs
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        # Parse results and apply metadata filters
        results = []
        for row in rows:
            run_data = {
                "run_uid": row[0],
                "timestamp": row[1],
                "plan_name": row[2],
                "metadata": json.loads(row[3]),
                "data_path": row[4],
            }

            # Filter by metadata key-value pairs
            if metadata_filters:
                metadata = run_data["metadata"]
                if all(
                    metadata.get(key) == value
                    for key, value in metadata_filters.items()
                ):
                    results.append(run_data)
            else:
                results.append(run_data)

        return results

    async def delete_run(self, run_uid: str) -> None:
        """Delete run from catalogue.

        Args:
            run_uid: Run UUID string.

        Raises:
            RuntimeError: If not connected to database.

        Note:
            This only removes the catalogue entry, not the HDF5 data file.
        """
        if self._db is None:
            raise RuntimeError("Not connected to database")

        await self._db.execute("DELETE FROM runs WHERE run_uid = ?", (run_uid,))
        await self._db.commit()

    async def count(self) -> int:
        """Count total number of runs in catalogue.

        Returns:
            Number of runs.

        Raises:
            RuntimeError: If not connected to database.
        """
        if self._db is None:
            raise RuntimeError("Not connected to database")

        async with self._db.execute("SELECT COUNT(*) FROM runs") as cursor:
            row = await cursor.fetchone()

        return row[0] if row else 0
