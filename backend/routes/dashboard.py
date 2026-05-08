"""
routes/dashboard.py — GET /api/dashboard/metrics endpoint.

Computes all eight dashboard metrics from the traces and feedback SQLite tables
on every call.  No caching in V1 — the query is fast on the expected row counts.

Metrics returned:
    total_chats            — total deviation reviews submitted
    escalation_rate        — % of reviews that triggered QA escalation
    avg_latency_ms         — mean response latency in milliseconds
    total_tokens_used      — sum of all input + output tokens across reviews
    estimated_cost_usd     — Anthropic API cost estimate (Haiku pricing)
    downvote_rate          — % of rated reviews marked as unhelpful (rating = -1)
    top_severity_breakdown — review count bucketed by severity level
    chats_last_7_days      — daily review count for the last 7 calendar days
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "sop_assistant.db"

# ---------------------------------------------------------------------------
# Haiku token pricing  (USD per token, input / output separately priced)
# https://www.anthropic.com/pricing  — Claude Haiku
# ---------------------------------------------------------------------------
_INPUT_PRICE_PER_TOKEN  = 0.80 / 1_000_000   # $0.80 per million input tokens
_OUTPUT_PRICE_PER_TOKEN = 4.00 / 1_000_000   # $4.00 per million output tokens


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class SeverityCount(BaseModel):
    """Row in the severity breakdown list."""
    severity: str = Field(description="'High' | 'Medium' | 'Low'")
    count:    int = Field(description="Number of reviews at this severity level")


class DailyCount(BaseModel):
    """One calendar day in the 7-day activity chart."""
    date:  str = Field(description="ISO-8601 date: 'YYYY-MM-DD'")
    count: int = Field(description="Number of reviews on this date (0 if none)")


class DashboardMetrics(BaseModel):
    """All dashboard metrics returned by GET /api/dashboard/metrics."""

    total_chats:            int               = Field(description="Total deviation reviews submitted")
    escalation_rate:        float             = Field(description="% of reviews that required QA escalation (0–100)")
    avg_latency_ms:         float             = Field(description="Mean response latency in milliseconds")
    total_tokens_used:      int               = Field(description="Sum of all input + output tokens")
    estimated_cost_usd:     float             = Field(description="Estimated Anthropic API cost in USD")
    downvote_rate:          float             = Field(description="% of rated reviews marked as unhelpful (0–100)")
    top_severity_breakdown: list[SeverityCount] = Field(description="Review count per severity level, descending")
    chats_last_7_days:      list[DailyCount]    = Field(description="Daily review count for the trailing 7 days")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_assessment(model_output_raw: str | None) -> dict[str, Any]:
    """
    Deserialise a stored model_output JSON string into the assessment dict.

    The traces table stores the validated LLM response as a JSON object with keys:
    classification, severity, impact, immediate_action, qa_escalation,
    missing_info, draft_summary.

    Returns an empty dict on any parse failure — never raises.
    """
    if not model_output_raw:
        return {}
    try:
        data = json.loads(model_output_raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


# ---------------------------------------------------------------------------
# GET /api/dashboard/metrics
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/metrics",
    response_model=DashboardMetrics,
    summary="Retrieve all dashboard metrics",
    description=(
        "Computes eight metrics from the traces and feedback tables.  "
        "Severity breakdown and escalation rate are derived by parsing the "
        "stored model_output JSON.  Cost estimate uses published Haiku pricing."
    ),
    responses={
        200: {"description": "All metrics computed successfully"},
        500: {"description": "Database error"},
    },
)
def get_dashboard_metrics() -> DashboardMetrics:
    """
    Open one SQLite connection, compute all metrics, close, return.
    """
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            return _compute_metrics(conn)
        finally:
            conn.close()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database error while computing metrics: {exc}",
        ) from exc


def _compute_metrics(conn: sqlite3.Connection) -> DashboardMetrics:
    """
    All metric computation in one place, accepting an open connection.
    Separated from the route handler to make unit testing straightforward.
    """

    # ── 1. Total chats ───────────────────────────────────────────────────────
    total_chats: int = conn.execute(
        "SELECT COUNT(*) FROM traces"
    ).fetchone()[0] or 0

    # ── 2. Latency + token aggregates (single scan) ──────────────────────────
    agg = conn.execute("""
        SELECT
            AVG(CASE WHEN latency_ms IS NOT NULL THEN latency_ms END) AS avg_lat,
            SUM(COALESCE(input_tokens,  0))                           AS in_tok,
            SUM(COALESCE(output_tokens, 0))                           AS out_tok
        FROM traces
    """).fetchone()

    avg_latency_ms:   float = round(float(agg["avg_lat"] or 0.0), 1)
    total_input_tok:  int   = int(agg["in_tok"]  or 0)
    total_output_tok: int   = int(agg["out_tok"] or 0)
    total_tokens_used: int  = total_input_tok + total_output_tok

    # ── 3. Estimated cost ────────────────────────────────────────────────────
    estimated_cost_usd = round(
        total_input_tok  * _INPUT_PRICE_PER_TOKEN +
        total_output_tok * _OUTPUT_PRICE_PER_TOKEN,
        6,
    )

    # ── 4 + 5. Escalation rate & severity breakdown (parse model_output) ─────
    #
    # model_output stores the validated assessment dict as a JSON string, e.g.:
    # {"classification":"Environmental","severity":"High","qa_escalation":true,...}
    #
    # We fetch all non-null rows and parse in Python so the logic is transparent
    # and works regardless of future SQLite JSON function availability.
    outputs = conn.execute(
        "SELECT model_output FROM traces WHERE model_output IS NOT NULL"
    ).fetchall()

    escalation_count  = 0
    severity_counter: Counter[str] = Counter()

    for (raw,) in outputs:
        assessment = _parse_assessment(raw)
        if assessment.get("qa_escalation") is True:
            escalation_count += 1
        sev = assessment.get("severity")
        if sev:
            severity_counter[sev] += 1

    escalation_rate = round(
        (escalation_count / total_chats * 100) if total_chats > 0 else 0.0,
        1,
    )

    # Sorted descending by count; canonical order for display: High, Medium, Low
    _SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
    top_severity_breakdown = [
        SeverityCount(severity=s, count=c)
        for s, c in sorted(
            severity_counter.items(),
            key=lambda x: (_SEVERITY_ORDER.get(x[0], 99), -x[1]),
        )
    ]

    # ── 6. Downvote rate ─────────────────────────────────────────────────────
    fb = conn.execute("""
        SELECT
            COUNT(*)                                      AS total,
            SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS downvotes
        FROM feedback
    """).fetchone()

    total_fb  = int(fb["total"]     or 0)
    downvotes = int(fb["downvotes"] or 0)
    downvote_rate = round(
        (downvotes / total_fb * 100) if total_fb > 0 else 0.0,
        1,
    )

    # ── 7. Chats last 7 days ─────────────────────────────────────────────────
    #
    # Build the full 7-day window (today − 6 days … today) so that days with
    # zero reviews still appear in the array.  Timestamps are stored as
    # ISO-8601 strings; SUBSTR(timestamp, 1, 10) extracts "YYYY-MM-DD".
    today  = date.today()
    window: dict[str, int] = {
        (today - timedelta(days=i)).isoformat(): 0
        for i in range(6, -1, -1)
    }
    cutoff = min(window.keys())

    daily_rows = conn.execute("""
        SELECT SUBSTR(timestamp, 1, 10) AS day,
               COUNT(*)                 AS cnt
        FROM   traces
        WHERE  timestamp >= ?
        GROUP  BY day
        ORDER  BY day
    """, (cutoff,)).fetchall()

    for row in daily_rows:
        if row["day"] in window:
            window[row["day"]] = row["cnt"]

    chats_last_7_days = [
        DailyCount(date=d, count=c) for d, c in window.items()
    ]

    return DashboardMetrics(
        total_chats            = total_chats,
        escalation_rate        = escalation_rate,
        avg_latency_ms         = avg_latency_ms,
        total_tokens_used      = total_tokens_used,
        estimated_cost_usd     = estimated_cost_usd,
        downvote_rate          = downvote_rate,
        top_severity_breakdown = top_severity_breakdown,
        chats_last_7_days      = chats_last_7_days,
    )
