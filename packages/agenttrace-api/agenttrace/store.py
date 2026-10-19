from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from commsfail import Trace
from .models import now


class Store:
    """Durable local trace and analysis storage for a single API worker."""

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = directory / "agenttrace.sqlite3"
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, trace_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    FOREIGN KEY(trace_id) REFERENCES traces(id)
                );
                CREATE INDEX IF NOT EXISTS runs_trace ON runs(trace_id);
                CREATE TABLE IF NOT EXISTS trace_evidence (
                    trace_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    FOREIGN KEY(trace_id) REFERENCES traces(id)
                );
                """
            )
        self.database.chmod(0o600)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def save_trace(self, trace_id: str, trace: Trace):
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO traces VALUES (?, ?)",
                (trace_id, json.dumps(trace.to_dict(), ensure_ascii=False)),
            )

    def get_trace(self, trace_id: str) -> Trace | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content FROM traces WHERE id = ?", (trace_id,)
            ).fetchone()
        return Trace(**json.loads(row[0])) if row else None

    def save_run(self, run: dict):
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(id) "
                "DO UPDATE SET content = excluded.content",
                (run["id"], run["trace_id"], json.dumps(run, ensure_ascii=False)),
            )

    def save_evidence(self, trace_id: str, evidence: dict):
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO trace_evidence VALUES (?, ?) ON CONFLICT(trace_id) "
                "DO UPDATE SET content = excluded.content",
                (trace_id, json.dumps(evidence, ensure_ascii=False)),
            )

    def get_evidence(self, trace_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT content FROM trace_evidence WHERE trace_id = ?", (trace_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list_runs(self, trace_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT content FROM runs WHERE trace_id = ? ORDER BY rowid",
                (trace_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def interrupt_pending(self):
        with self._connect() as connection:
            rows = connection.execute("SELECT content FROM runs").fetchall()
        for row in rows:
            run = json.loads(row[0])
            if run["status"] in ("queued", "running"):
                run["status"] = "failed"
                run["error"] = "API stopped before this analysis completed. Start a new run."
                run["provenance"]["completed_at"] = now()
                self.save_run(run)
