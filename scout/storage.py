"""
storage.py — SQLite persistence for Scout pipeline runs.

DB file: runs.db in the project root (one level above this package).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Place the DB next to main.py, not inside the package directory
_DB_PATH = Path(__file__).resolve().parent.parent / "runs.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the runs table if it doesn't already exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT    NOT NULL,
                source_url   TEXT,
                model_key    TEXT,
                config_json  TEXT,
                snippet      TEXT,
                reasoning    TEXT,
                errors       TEXT
            )
        """)
    logger.info("DB initialised at %s", _DB_PATH)


def save_run(
    source_url: str | None,
    model_key: str,
    config_json: str,
    snippet: str,
    reasoning: str,
    errors: str,
) -> int:
    """
    Persist a completed (or partial) pipeline run.
    Returns the new row id.
    """
    # Pull generated_at from the config JSON if available, otherwise use NOW
    generated_at = _extract_generated_at(config_json)

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs (generated_at, source_url, model_key, config_json, snippet, reasoning, errors)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (generated_at, source_url, model_key, config_json, snippet, reasoning, errors),
        )
        run_id: int = cur.lastrowid  # type: ignore[assignment]

    logger.info("Saved run id=%d", run_id)
    return run_id


def list_runs() -> list[dict[str, Any]]:
    """
    Return all runs newest-first.
    Only returns lightweight fields (no config_json / snippet / reasoning).
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, generated_at, source_url, model_key, errors FROM runs ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: int) -> dict[str, Any] | None:
    """Return the full row for *run_id*, or None if not found."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def delete_run(run_id: int) -> bool:
    """Delete a run by id. Returns True if a row was deleted."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_generated_at(config_json: str) -> str:
    """Pull generated_at from the config JSON string, or return an ISO timestamp."""
    from datetime import datetime, timezone
    try:
        data = json.loads(config_json)
        ts = data.get("generated_at")
        if ts:
            return ts
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()
