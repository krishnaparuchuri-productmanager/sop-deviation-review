"""
routes/evals.py — POST /api/evals/run and GET /api/evals/results endpoints.

POST /api/evals/run
    Triggers a full evaluation run synchronously: loads eval_set.csv, runs
    every case through the agent pipeline, scores with an LLM-as-judge, also
    scores an always-escalate baseline for comparison, and saves all results
    to the eval_results table.

    Note: the run takes 3–6 minutes (≈30 LLM pipeline calls + ≈30 judge calls).
    The endpoint is a dev/admin tool, not user-facing.

GET /api/evals/results
    Returns eval results for the most recent run (or a specific run_id).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from eval_runner import run_full_eval, compute_summary   # uvicorn from backend/
    from agentops_push import push_eval_results
except ImportError:
    from backend.eval_runner import run_full_eval, compute_summary
    from backend.agentops_push import push_eval_results

router = APIRouter()

_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "sop_assistant.db"


# ---------------------------------------------------------------------------
# Shared response schemas
# ---------------------------------------------------------------------------

class DimensionSummary(BaseModel):
    pass_rate_pct:      float
    avg_total_score:    float
    avg_groundedness:   float
    avg_classification: float
    avg_escalation:     float
    avg_clarity:        float
    cases:              int
    pass_count:         int


class EvalResultRow(BaseModel):
    """One scored row from the eval_results table."""
    id:             str
    case_id:        str
    run_id:         str
    model_tag:      str
    groundedness:   int
    classification: int
    escalation:     int
    clarity:        int
    total_score:    int
    overall_pass:   int
    notes:          str | None
    created_at:     str


# ---------------------------------------------------------------------------
# POST /api/evals/run
# ---------------------------------------------------------------------------

class EvalRunResponse(BaseModel):
    """Returned after a complete eval run."""
    run_id:     str
    duration_s: float
    total_rows: int
    actual:     DimensionSummary = Field(description="Metrics for the real agent pipeline")
    baseline:   DimensionSummary = Field(description="Metrics for the always-escalate baseline")


@router.post(
    "/evals/run",
    response_model=EvalRunResponse,
    summary="Run the full evaluation suite",
    description=(
        "Loads all 15 golden eval cases, runs each through the agent pipeline, "
        "scores with an LLM-as-judge on four rubric dimensions (0–2 each), "
        "compares against an always-escalate baseline, and saves every result "
        "to the eval_results table.  Takes 3–6 minutes to complete."
    ),
    responses={
        200: {"description": "Eval run completed successfully"},
        403: {"description": "Forbidden — invalid or missing X-Eval-Token header"},
        500: {"description": "Pipeline or database error during the run"},
    },
)
def trigger_eval_run(
    x_eval_token: str | None = Header(default=None, description="Secret token required to trigger eval runs"),
) -> EvalRunResponse:
    """Run evals synchronously and return aggregate metrics."""
    # Guard: require the EVAL_SECRET_TOKEN env var to match the request header.
    # Without this, any internet user could trigger 30+ LLM calls and drain credits.
    expected_token = os.environ.get("EVAL_SECRET_TOKEN", "").strip()
    if not expected_token or x_eval_token != expected_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        summary = run_full_eval(verbose=True)
    except Exception as exc:                        # noqa: BLE001
        logger.error("Eval run failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=500,
            detail="Eval run failed due to an internal error. Check server logs.",
        ) from exc

    # Push results to AgentOps governance dashboard (non-blocking — errors are logged, not raised)
    try:
        push_eval_results(summary)
    except Exception as exc:                        # noqa: BLE001
        logger.warning("AgentOps push_eval_results failed (non-fatal): %s", exc)

    return EvalRunResponse(
        run_id     = summary["run_id"],
        duration_s = summary["duration_s"],
        total_rows = summary["total_rows"],
        actual     = DimensionSummary(**summary["actual"]),
        baseline   = DimensionSummary(**summary["baseline"]),
    )


# ---------------------------------------------------------------------------
# GET /api/evals/results
# ---------------------------------------------------------------------------

class EvalResultsResponse(BaseModel):
    """All eval results for one run (latest by default)."""
    run_id:          str | None
    available_runs:  list[str]
    actual_summary:   DimensionSummary | None
    baseline_summary: DimensionSummary | None
    results:         list[EvalResultRow]


@router.get(
    "/evals/results",
    response_model=EvalResultsResponse,
    summary="Retrieve eval results",
    description=(
        "Returns scored results for the most recent eval run, or for a specific "
        "run_id supplied as a query parameter.  Both the actual-model results and "
        "the always-escalate baseline results are included."
    ),
    responses={
        200: {"description": "Results returned (empty list if no runs yet)"},
        500: {"description": "Database error"},
    },
)
def get_eval_results(
    run_id: str | None = Query(default=None, description="Specific run UUID; omit for latest run"),
) -> EvalResultsResponse:
    """Fetch eval results from SQLite and compute per-tag summaries."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            return _fetch_results(conn, run_id)
        finally:
            conn.close()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        logger.error("Database error in get_eval_results: %s", exc)
        raise HTTPException(status_code=500, detail="Database error while fetching eval results.") from exc


def _fetch_results(
    conn:           sqlite3.Connection,
    requested_run:  str | None,
) -> EvalResultsResponse:
    # All available run IDs (newest first)
    run_rows = conn.execute(
        "SELECT DISTINCT run_id FROM eval_results ORDER BY created_at DESC"
    ).fetchall()
    available_runs = [r["run_id"] for r in run_rows]

    if not available_runs:
        return EvalResultsResponse(
            run_id=None,
            available_runs=[],
            actual_summary=None,
            baseline_summary=None,
            results=[],
        )

    target_run = requested_run if requested_run in available_runs else available_runs[0]

    rows = conn.execute(
        """
        SELECT id, case_id, run_id, model_tag,
               groundedness, classification, escalation, clarity,
               groundedness + classification + escalation + clarity AS total_score,
               overall_pass, notes, created_at
        FROM   eval_results
        WHERE  run_id = ?
        ORDER  BY model_tag, case_id
        """,
        (target_run,),
    ).fetchall()

    results = [
        EvalResultRow(
            id             = r["id"],
            case_id        = r["case_id"],
            run_id         = r["run_id"],
            model_tag      = r["model_tag"],
            groundedness   = r["groundedness"],
            classification = r["classification"],
            escalation     = r["escalation"],
            clarity        = r["clarity"],
            total_score    = r["total_score"],
            overall_pass   = r["overall_pass"],
            notes          = r["notes"],
            created_at     = r["created_at"],
        )
        for r in rows
    ]

    # Build per-tag summaries using the dataclass-based compute_summary
    def _to_eval_result_dc(r: EvalResultRow):
        """Convert EvalResultRow Pydantic → EvalResult dataclass for compute_summary."""
        from eval_runner import EvalResult as DC  # noqa: PLC0415 — lazy import avoids circular
        return DC(
            case_id        = r.case_id,
            run_id         = r.run_id,
            model_tag      = r.model_tag,
            groundedness   = r.groundedness,
            classification = r.classification,
            escalation     = r.escalation,
            clarity        = r.clarity,
            overall_pass   = r.overall_pass,
            notes          = r.notes or "",
            created_at     = r.created_at,
        )

    actual_rows   = [r for r in results if r.model_tag == "actual"]
    baseline_rows = [r for r in results if r.model_tag == "baseline_always_escalate"]

    actual_summary   = DimensionSummary(**compute_summary([_to_eval_result_dc(r) for r in actual_rows]))   if actual_rows   else None
    baseline_summary = DimensionSummary(**compute_summary([_to_eval_result_dc(r) for r in baseline_rows])) if baseline_rows else None

    return EvalResultsResponse(
        run_id           = target_run,
        available_runs   = available_runs,
        actual_summary   = actual_summary,
        baseline_summary = baseline_summary,
        results          = results,
    )
