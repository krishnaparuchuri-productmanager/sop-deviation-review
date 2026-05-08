"""
tracer.py — SQLite trace logger for the SOP Deviation Review Assistant.

Responsibilities:
  - Resolve the database path relative to this file (works wherever the process is run from).
  - Expose log_trace(trace_data) — inserts one row into the `traces` table.
  - Never raise to callers; all errors are printed to stderr so a tracing failure
    never breaks a live review request.

Expected trace_data keys (all optional except trace_id / timestamp / user_input):
    trace_id         TEXT  — UUID v4 (caller-generated)
    timestamp        TEXT  — ISO-8601 UTC string
    user_input       TEXT  — raw deviation text
    retrieved_chunks TEXT  — JSON-serialised list of chunk IDs
    prompt_version   TEXT  — defaults to "v1"
    model_output     TEXT  — raw JSON string from the LLM tool_use response
    latency_ms       int   — wall-clock time in milliseconds
    input_tokens     int   — tokens consumed by the prompt
    output_tokens    int   — tokens produced by the completion
    error            TEXT  — None / null on success; error message on failure
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve DB path from this file's location regardless of working directory.
# This file lives at backend/tracer.py → the DB is at backend/db/sop_assistant.db
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent
_DB_PATH     = _BACKEND_DIR / "db" / "sop_assistant.db"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_trace(trace_data: dict[str, Any]) -> None:
    """
    Insert one trace record into the `traces` table.

    Args:
        trace_data: Dict containing the trace fields listed in the module docstring.
                    Unknown keys are ignored.  Missing keys fall back to safe defaults.

    Returns:
        None — this function never raises.  Any database error is printed to stderr.
    """
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO traces (
                        id,
                        timestamp,
                        user_input,
                        retrieved_chunks,
                        prompt_version,
                        model_output,
                        latency_ms,
                        input_tokens,
                        output_tokens,
                        error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace_data.get("trace_id",         ""),
                        trace_data.get("timestamp",        ""),
                        trace_data.get("user_input",       ""),
                        trace_data.get("retrieved_chunks", None),
                        trace_data.get("prompt_version",   "v1"),
                        trace_data.get("model_output",     None),
                        trace_data.get("latency_ms",       None),
                        trace_data.get("input_tokens",     None),
                        trace_data.get("output_tokens",    None),
                        trace_data.get("error",            None),
                    ),
                )
        finally:
            conn.close()

    except Exception as exc:  # noqa: BLE001 — intentional broad catch; tracing must not crash the app
        print(
            f"[tracer] WARNING: failed to log trace {trace_data.get('trace_id', '?')}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def get_recent_traces(limit: int = 20) -> list[dict[str, Any]]:
    """
    Return the most recent `limit` trace rows, newest first.

    Args:
        limit: Maximum number of rows to return. Defaults to 20.

    Returns:
        List of dicts with all traces columns.  Returns [] on error.
    """
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                """
                SELECT
                    id            AS trace_id,
                    timestamp,
                    user_input,
                    retrieved_chunks,
                    prompt_version,
                    model_output,
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    error
                FROM traces
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    except Exception as exc:  # noqa: BLE001
        print(
            f"[tracer] WARNING: failed to read traces: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return []
