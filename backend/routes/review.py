"""
routes/review.py — POST /api/review endpoint for the SOP Deviation Review Assistant.

Responsibilities:
  - Accept a deviation description (and optional case_id) from the caller.
  - Retrieve the top-3 most relevant SOP chunks via TF-IDF search.
  - Call assess_deviation_traced() — Haiku call, validation, and retry.
  - Persist a full trace record via log_trace() before returning.
  - Return a fixed-schema JSON response that always includes retrieved_sources.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    # Running via uvicorn from inside backend/
    from retrieval import search_sop
    from prompts import assess_deviation_traced, SAFE_FALLBACK
    from tracer import log_trace
except ImportError:
    # Running tests / import from project root
    from backend.retrieval import search_sop
    from backend.prompts import assess_deviation_traced, SAFE_FALLBACK
    from backend.tracer import log_trace

router = APIRouter()

# Current prompt version — increment when SYSTEM_PROMPT or tool schema changes.
_PROMPT_VERSION = "v1"


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    """Body accepted by POST /api/review."""

    user_input: str = Field(
        ...,
        min_length=10,
        description="Free-text description of the deviation to be reviewed.",
        examples=["A cold storage unit was found reading +8°C against a limit of +5°C."],
    )
    case_id: str | None = Field(
        default=None,
        description="Optional case identifier for trace correlation.",
        examples=["CASE-0042"],
    )


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class RetrievedSource(BaseModel):
    """A single SOP chunk returned as a cited source."""

    chunk_id:      str | None = None
    section_title: str | None = None
    source_file:   str | None = None
    score:         float | None = None
    text_excerpt:  str = ""      # First 300 chars of the chunk text


class ReviewResponse(BaseModel):
    """Fixed-schema response returned by POST /api/review."""

    # Core assessment fields
    classification:   str
    severity:         str
    impact:           str
    immediate_action: str
    qa_escalation:    bool
    missing_info:     str
    draft_summary:    str

    # Retrieval provenance
    retrieved_sources: list[RetrievedSource]

    # Trace correlation
    trace_id: str

    # Optional metadata
    case_id:     str | None = None
    latency_ms:  int        = 0
    is_fallback: bool       = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _shape_sources(chunks: list[dict]) -> list[RetrievedSource]:
    """Convert raw search-result dicts into RetrievedSource Pydantic objects."""
    sources: list[RetrievedSource] = []
    for chunk in chunks:
        text = chunk.get("text", "")
        sources.append(
            RetrievedSource(
                chunk_id      = chunk.get("chunk_id"),
                section_title = chunk.get("section_title"),
                source_file   = chunk.get("source_file"),
                score         = chunk.get("score"),
                text_excerpt  = text[:300].strip(),
            )
        )
    return sources


def _chunk_ids_json(chunks: list[dict]) -> str:
    """Serialise a list of chunk_id strings as a compact JSON array."""
    ids = [c.get("chunk_id", "") for c in chunks if c.get("chunk_id")]
    return json.dumps(ids)


# ---------------------------------------------------------------------------
# POST /api/review
# ---------------------------------------------------------------------------

@router.post(
    "/review",
    response_model=ReviewResponse,
    summary="Review a pharmaceutical deviation",
    description=(
        "Accepts a free-text deviation description, retrieves the most relevant "
        "SOP sections, and returns a structured GMP assessment with a severity "
        "classification, recommended immediate action, and QA escalation flag. "
        "Every call is persisted to the traces table."
    ),
    responses={
        200: {"description": "Structured deviation assessment"},
        422: {"description": "Validation error — user_input too short or malformed"},
        500: {"description": "Internal server error"},
    },
)
def review_deviation(body: ReviewRequest) -> ReviewResponse:
    """
    End-to-end deviation review pipeline:
      1. Generate a trace_id for this request.
      2. Retrieve top-3 SOP chunks most relevant to the deviation.
      3. Call assess_deviation_traced() — Haiku call + validation + retry.
      4. Write a trace record to SQLite (best-effort; never fails the request).
      5. Return ReviewResponse.
    """
    t0        = time.monotonic()
    trace_id  = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Retrieve relevant SOP chunks -----------------------------------------
    retrieval_error: str | None = None
    try:
        sop_chunks: list[dict] = search_sop(body.user_input, top_k=3)
    except Exception as exc:  # noqa: BLE001
        retrieval_error = f"Retrieval failed: {type(exc).__name__}: {exc}"
        sop_chunks = []

    # 2. Run the LLM assessment pipeline --------------------------------------
    assessment, trace_meta = assess_deviation_traced(
        user_text  = body.user_input,
        sop_chunks = sop_chunks,
    )

    latency_ms = int((time.monotonic() - t0) * 1000)

    # 3. Persist trace record (best-effort) -----------------------------------
    log_trace({
        "trace_id":         trace_id,
        "timestamp":        timestamp,
        "user_input":       body.user_input,
        "retrieved_chunks": _chunk_ids_json(sop_chunks),
        "prompt_version":   _PROMPT_VERSION,
        "model_output":     trace_meta.model_output_raw or None,
        "latency_ms":       latency_ms,
        "input_tokens":     trace_meta.input_tokens,
        "output_tokens":    trace_meta.output_tokens,
        # Surface the first error encountered: LLM error takes priority over retrieval
        "error":            trace_meta.error or retrieval_error,
    })

    # 4. Build and return response --------------------------------------------
    return ReviewResponse(
        classification    = assessment.get("classification",   SAFE_FALLBACK["classification"]),
        severity          = assessment.get("severity",         SAFE_FALLBACK["severity"]),
        impact            = assessment.get("impact",           SAFE_FALLBACK["impact"]),
        immediate_action  = assessment.get("immediate_action", SAFE_FALLBACK["immediate_action"]),
        qa_escalation     = assessment.get("qa_escalation",    SAFE_FALLBACK["qa_escalation"]),
        missing_info      = assessment.get("missing_info",     SAFE_FALLBACK["missing_info"]),
        draft_summary     = assessment.get("draft_summary",    SAFE_FALLBACK["draft_summary"]),
        retrieved_sources = _shape_sources(sop_chunks),
        trace_id          = trace_id,
        case_id           = body.case_id,
        latency_ms        = latency_ms,
        is_fallback       = trace_meta.is_fallback,
    )
