"""
routes/traces.py — GET /api/traces endpoint for the SOP Deviation Review Assistant.

Returns the 20 most recent trace records from the SQLite traces table, newest first.
Primarily used for observability, debugging, and confirming that /api/review calls
are being logged correctly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from tracer import get_recent_traces         # uvicorn from backend/
except ImportError:
    from backend.tracer import get_recent_traces  # pytest from project root

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class TraceRecord(BaseModel):
    """One row from the traces table."""

    trace_id:         str
    timestamp:        str
    user_input:       str
    retrieved_chunks: str | None = None   # JSON array string of chunk IDs
    prompt_version:   str | None = None
    model_output:     str | None = None   # Raw JSON from the LLM tool_use block
    latency_ms:       int | None = None
    input_tokens:     int | None = None
    output_tokens:    int | None = None
    error:            str | None = None   # None on success


class TracesResponse(BaseModel):
    """Wrapper returned by GET /api/traces."""

    count:  int
    traces: list[TraceRecord]


# ---------------------------------------------------------------------------
# GET /api/traces
# ---------------------------------------------------------------------------

@router.get(
    "/traces",
    response_model=TracesResponse,
    summary="List recent trace records",
    description=(
        "Returns the 20 most recent /api/review trace records, newest first. "
        "Each record includes the full input, retrieved chunk IDs, raw model output, "
        "token counts, latency, and any error that occurred."
    ),
    responses={
        200: {"description": "List of trace records"},
        500: {"description": "Internal server error"},
    },
)
def list_traces() -> TracesResponse:
    """Fetch the 20 most recent trace rows from SQLite and return them."""
    rows: list[dict[str, Any]] = get_recent_traces(limit=20)
    return TracesResponse(
        count  = len(rows),
        traces = [TraceRecord(**row) for row in rows],
    )
