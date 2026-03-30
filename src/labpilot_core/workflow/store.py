"""Workflow persistence and versioning store.

SQLite-based append-only storage for workflows with full version history.
Every workflow mutation creates a new version row - this provides complete
audit trail and enables workflow rollback/diff functionality.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from labpilot_core.workflow.graph import WorkflowGraph

__all__ = ["WorkflowStore", "WorkflowSummary", "WorkflowVersion"]


class WorkflowSummary:
    """Summary information about a workflow."""

    def __init__(
        self,
        id: str,
        name: str,
        current_version: int,
        created_at: float,
        updated_at: float,
        deleted: bool = False,
    ):
        self.id = id
        self.name = name
        self.current_version = current_version
        self.created_at = created_at
        self.updated_at = updated_at
        self.deleted = deleted


class WorkflowVersion:
    """A specific version of a workflow."""

    def __init__(
        self,
        workflow_id: str,
        version: int,
        created_at: float,
        graph_json: str,
        comment: str = "",
    ):
        self.workflow_id = workflow_id
        self.version = version
        self.created_at = created_at
        self.graph_json = graph_json
        self.comment = comment

    @property
    def graph(self) -> WorkflowGraph:
        """Parse JSON back to WorkflowGraph."""
        return WorkflowGraph.from_json(self.graph_json)


class WorkflowStore:
    """SQLite-based workflow storage with versioning.

    Features:
    - Append-only storage (workflows are never actually deleted)
    - Full version history with diffs
    - Atomic transactions
    - Workflow code file preservation

    Database schema:
        workflows: id, current_version, name, created_at, updated_at, deleted
        workflow_versions: workflow_id, version, created_at, graph_json, comment
        execution_logs: workflow_id, version, started_at, completed_at, status, results

    Code files are stored separately in workflows/code/ directory and never deleted.
    """

    def __init__(self, db_path: str | Path, code_dir: str | Path | None = None):
        """Initialize workflow store.

        Args:
            db_path: SQLite database file path.
            code_dir: Directory for storing generated code files.
        """
        self.db_path = Path(db_path)
        self.code_dir = Path(code_dir) if code_dir else self.db_path.parent / "workflows" / "code"

        # Create directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.code_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    current_version INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    deleted BOOLEAN NOT NULL DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_versions (
                    workflow_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    graph_json TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (workflow_id, version),
                    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    status TEXT NOT NULL,
                    results_json TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
                )
            """)

            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_versions_workflow_id
                ON workflow_versions (workflow_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_execution_logs_workflow_id
                ON execution_logs (workflow_id)
            """)

    def save(self, graph: WorkflowGraph, comment: str = "") -> int:
        """Save workflow graph and return new version number.

        Args:
            graph: WorkflowGraph to save.
            comment: Optional version comment.

        Returns:
            New version number.
        """
        now = time.time()
        graph_json = graph.to_json()

        with sqlite3.connect(self.db_path) as conn:
            # Check if workflow exists
            cursor = conn.execute(
                "SELECT current_version FROM workflows WHERE id = ?",
                (graph.id,)
            )
            result = cursor.fetchone()

            if result is None:
                # New workflow
                version = 1
                conn.execute("""
                    INSERT INTO workflows (id, current_version, name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (graph.id, version, graph.name, now, now))
            else:
                # Update existing workflow
                version = result[0] + 1
                conn.execute("""
                    UPDATE workflows
                    SET current_version = ?, name = ?, updated_at = ?
                    WHERE id = ?
                """, (version, graph.name, now, graph.id))

            # Insert new version
            conn.execute("""
                INSERT INTO workflow_versions (workflow_id, version, created_at, graph_json, comment)
                VALUES (?, ?, ?, ?, ?)
            """, (graph.id, version, now, graph_json, comment))

            # Save AnalyseNode code to files
            self._save_code_files(graph, version)

            return version

    def load(self, workflow_id: str, version: int | None = None) -> WorkflowGraph:
        """Load workflow graph by ID and optional version.

        Args:
            workflow_id: Workflow ID to load.
            version: Specific version (default: latest).

        Returns:
            WorkflowGraph instance.

        Raises:
            ValueError: If workflow not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            if version is None:
                # Load latest version
                cursor = conn.execute("""
                    SELECT wv.graph_json
                    FROM workflow_versions wv
                    JOIN workflows w ON wv.workflow_id = w.id
                    WHERE w.id = ? AND wv.version = w.current_version AND w.deleted = 0
                """, (workflow_id,))
            else:
                # Load specific version
                cursor = conn.execute("""
                    SELECT graph_json
                    FROM workflow_versions
                    WHERE workflow_id = ? AND version = ?
                """, (workflow_id, version))

            result = cursor.fetchone()
            if result is None:
                raise ValueError(f"Workflow {workflow_id} version {version} not found")

            return WorkflowGraph.from_json(result[0])

    def list_all(self, include_deleted: bool = False) -> list[WorkflowSummary]:
        """List all workflows.

        Args:
            include_deleted: Include deleted workflows.

        Returns:
            List of workflow summaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT id, name, current_version, created_at, updated_at, deleted
                FROM workflows
            """
            if not include_deleted:
                query += " WHERE deleted = 0"
            query += " ORDER BY updated_at DESC"

            cursor = conn.execute(query)
            return [
                WorkflowSummary(
                    id=row[0],
                    name=row[1],
                    current_version=row[2],
                    created_at=row[3],
                    updated_at=row[4],
                    deleted=bool(row[5]),
                )
                for row in cursor.fetchall()
            ]

    def history(self, workflow_id: str) -> list[WorkflowVersion]:
        """Get version history for a workflow.

        Args:
            workflow_id: Workflow ID.

        Returns:
            List of versions ordered by version number.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT workflow_id, version, created_at, graph_json, comment
                FROM workflow_versions
                WHERE workflow_id = ?
                ORDER BY version ASC
            """, (workflow_id,))

            return [
                WorkflowVersion(
                    workflow_id=row[0],
                    version=row[1],
                    created_at=row[2],
                    graph_json=row[3],
                    comment=row[4],
                )
                for row in cursor.fetchall()
            ]

    def delete(self, workflow_id: str) -> None:
        """Mark workflow as deleted (soft delete).

        Args:
            workflow_id: Workflow ID to delete.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE workflows
                SET deleted = 1, updated_at = ?
                WHERE id = ?
            """, (time.time(), workflow_id))

    def diff(self, workflow_id: str, v1: int, v2: int) -> dict[str, Any]:
        """Get diff between two workflow versions.

        Args:
            workflow_id: Workflow ID.
            v1: First version number.
            v2: Second version number.

        Returns:
            Diff information dict.
        """
        graph1 = self.load(workflow_id, v1)
        graph2 = self.load(workflow_id, v2)

        # Simple diff - compare node counts and names
        nodes1 = set(graph1.nodes.keys())
        nodes2 = set(graph2.nodes.keys())

        return {
            "added_nodes": list(nodes2 - nodes1),
            "removed_nodes": list(nodes1 - nodes2),
            "modified_nodes": [
                nid for nid in (nodes1 & nodes2)
                if graph1.nodes[nid] != graph2.nodes[nid]
            ],
            "edge_count_change": len(graph2.edges) - len(graph1.edges),
        }

    def _save_code_files(self, graph: WorkflowGraph, version: int) -> None:
        """Save AnalyseNode code to permanent files.

        Code files are never deleted and provide permanent audit trail.
        """
        workflow_code_dir = self.code_dir / graph.id
        workflow_code_dir.mkdir(parents=True, exist_ok=True)

        for node_id, node_data in graph.nodes.items():
            if node_data.get("kind") == "analyse" and "code" in node_data:
                timestamp = int(time.time())
                filename = f"{node_id}_v{version}_{timestamp}.py"
                code_path = workflow_code_dir / filename

                with open(code_path, "w") as f:
                    f.write(f'"""AnalyseNode code for workflow {graph.name}\n')
                    f.write(f'Node: {node_id}\n')
                    f.write(f'Version: {version}\n')
                    f.write(f'Generated: {time.ctime()}\n')
                    f.write('"""\n\n')
                    f.write(node_data["code"])

    def log_execution(
        self,
        workflow_id: str,
        version: int,
        status: str,
        results: dict[str, Any] | None = None,
        execution_id: str | None = None,
    ) -> str:
        """Log workflow execution.

        Args:
            workflow_id: Workflow ID.
            version: Workflow version.
            status: Execution status (started, completed, failed).
            results: Execution results dict.
            execution_id: Optional execution ID (auto-generated if not provided).

        Returns:
            Execution ID.
        """
        if execution_id is None:
            execution_id = str(uuid.uuid4())

        now = time.time()
        results_json = json.dumps(results) if results else None

        with sqlite3.connect(self.db_path) as conn:
            if status == "started":
                conn.execute("""
                    INSERT INTO execution_logs (id, workflow_id, version, started_at, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (execution_id, workflow_id, version, now, status))
            else:
                conn.execute("""
                    UPDATE execution_logs
                    SET completed_at = ?, status = ?, results_json = ?
                    WHERE id = ?
                """, (now, status, results_json, execution_id))

        return execution_id
