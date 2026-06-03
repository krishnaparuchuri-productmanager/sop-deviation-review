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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import threading

try:
    from langsmith import Client as LangSmithClient
    _ls_client: LangSmithClient | None = None

    def _get_ls_client() -> LangSmithClient | None:
        """Return a cached LangSmith client, or None if unavailable."""
        global _ls_client
        if _ls_client is None:
            try:
                _ls_client = LangSmithClient()
            except Exception:
                pass
        return _ls_client

except ImportError:
    LangSmithClient = None  # type: ignore
    def _get_ls_client():
        return None

def traceable(**_kw):           # no-op decorator — tracing done manually below
    def _wrap(fn): return fn
    return _wrap

try:
    # Running via uvicorn from inside backend/
    from retrieval import search_sop
    from prompts import assess_deviation_traced, SAFE_FALLBACK
    from tracer import log_trace
    from rate_limit import is_rate_limited
    from agentops_push import push_daily_cost, push_trace
except ImportError:
    # Running tests / import from project root
    from backend.retrieval import search_sop
    from backend.prompts import assess_deviation_traced, SAFE_FALLBACK
    from backend.tracer import log_trace
    from backend.rate_limit import is_rate_limited
    from backend.agentops_push import push_daily_cost, push_trace

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
        max_length=4000,
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

def _run_review_pipeline(user_input: str, case_id: str | None) -> dict:
    """
    Inner traceable pipeline — separated from the FastAPI handler so LangSmith
    receives clean inputs/outputs without FastAPI Request objects.
    Returns the raw assessment dict + metadata for the response builder.
    """
    trace_id  = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t0        = time.monotonic()

    retrieval_error: str | None = None
    try:
        sop_chunks: list[dict] = search_sop(user_input, top_k=3)
    except Exception as exc:
        retrieval_error = f"Retrieval failed: {type(exc).__name__}: {exc}"
        sop_chunks = []

    assessment, trace_meta = assess_deviation_traced(
        user_text  = user_input,
        sop_chunks = sop_chunks,
    )

    latency_ms = int((time.monotonic() - t0) * 1000)

    log_trace({
        "trace_id":         trace_id,
        "timestamp":        timestamp,
        "user_input":       user_input,
        "retrieved_chunks": _chunk_ids_json(sop_chunks),
        "prompt_version":   _PROMPT_VERSION,
        "model_output":     trace_meta.model_output_raw or None,
        "latency_ms":       latency_ms,
        "input_tokens":     trace_meta.input_tokens,
        "output_tokens":    trace_meta.output_tokens,
        "error":            trace_meta.error or retrieval_error,
    })

    try:
        push_trace(
            trace_id      = trace_id,
            timestamp     = timestamp,
            user_input    = user_input,
            assessment    = assessment,
            input_tokens  = trace_meta.input_tokens or 0,
            output_tokens = trace_meta.output_tokens or 0,
            latency_ms    = latency_ms,
            is_fallback   = trace_meta.is_fallback,
        )
        push_daily_cost()
    except Exception:
        pass

    result = {
        "assessment":   assessment,
        "trace_meta":   trace_meta,
        "sop_chunks":   sop_chunks,
        "trace_id":     trace_id,
        "case_id":      case_id,
        "latency_ms":   latency_ms,
    }

    # Push trace to LangSmith in a background thread so it never blocks the response.
    def _push_langsmith():
        try:
            client = _get_ls_client()
            if client is None:
                return
            import os
            project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT") or "default"
            run_id = str(uuid.uuid4())
            client.create_run(
                id          = run_id,
                name        = "gmp-deviation-review",
                run_type    = "chain",
                project_name = project,
                inputs      = {"user_input": user_input, "case_id": case_id},
                outputs     = {"assessment": assessment},
                tags        = ["pharma", "gmp", "deviation"],
                extra       = {
                    "metadata": {
                        "trace_id":      trace_id,
                        "prompt_version": _PROMPT_VERSION,
                        "latency_ms":    latency_ms,
                        "input_tokens":  trace_meta.input_tokens,
                        "output_tokens": trace_meta.output_tokens,
                        "is_fallback":   trace_meta.is_fallback,
                    }
                },
            )
        except Exception:
            pass  # Never let LangSmith errors surface to the caller

    threading.Thread(target=_push_langsmith, daemon=True).start()

    return result


@router.post(
    "/review",
    response_model=ReviewResponse,
    summary="Review a pharmaceutical deviation",
    description=(
        "Accepts a free-text deviation description, retrieves the top-3 relevant SOP chunks, "
        "calls Claude Haiku for structured assessment, and returns a fixed-schema JSON response."
    ),
    responses={
        200: {"description": "Structured deviation assessment"},
        422: {"description": "Validation error — user_input too short/long or malformed"},
        429: {"description": "Rate limit exceeded — max 10 requests per minute per IP"},
        500: {"description": "Internal server error"},
    },
)
def review_deviation(request: Request, body: ReviewRequest) -> ReviewResponse:
    """
    End-to-end deviation review pipeline:
      1. Rate-limit check — 10 requests/minute per IP.
      2. Generate a trace_id for this request.
      3. Retrieve top-3 SOP chunks most relevant to the deviation.
      4. Call assess_deviation_traced() — Haiku call + validation + retry.
      5. Write a trace record to SQLite (best-effort; never fails the request).
      6. Return ReviewResponse.
    """
    # 0. Rate-limit gate -------------------------------------------------------
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment before trying again.",
        )

    # 1–4. Run traceable pipeline (LangSmith captures full span) --------------
    result     = _run_review_pipeline(body.user_input, body.case_id)
    assessment = result["assessment"]
    trace_meta = result["trace_meta"]
    sop_chunks = result["sop_chunks"]

    # 5. Build and return response --------------------------------------------
    return ReviewResponse(
        classification    = assessment.get("classification",   SAFE_FALLBACK["classification"]),
        severity          = assessment.get("severity",         SAFE_FALLBACK["severity"]),
        impact            = assessment.get("impact",           SAFE_FALLBACK["impact"]),
        immediate_action  = assessment.get("immediate_action", SAFE_FALLBACK["immediate_action"]),
        qa_escalation     = assessment.get("qa_escalation",    SAFE_FALLBACK["qa_escalation"]),
        missing_info      = assessment.get("missing_info",     SAFE_FALLBACK["missing_info"]),
        draft_summary     = assessment.get("draft_summary",    SAFE_FALLBACK["draft_summary"]),
        retrieved_sources = _shape_sources(sop_chunks),
        trace_id          = result["trace_id"],
        case_id           = result["case_id"],
        latency_ms        = result["latency_ms"],
        is_fallback       = trace_meta.is_fallback,
    )
