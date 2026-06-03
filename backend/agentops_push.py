"""
agentops_push.py — Bridge between SOP Deviation Review and AgentOps dashboard.

Called automatically after:
  - Every eval run  (POST /api/evals/run)  → pushes eval results + dimensions
  - Every /api/review call                 → queues daily cost/token rollup
  - On-demand sync  (POST /api/agentops/sync)

Environment variables:
  AGENTOPS_API_URL   — AgentOps backend base URL (Railway deployment)
  AGENTOPS_AGENT_ID  — Agent ID registered in AgentOps (default: gmp-deviation-review)

If AGENTOPS_API_URL is not set, all push calls are silently skipped (safe for
local dev without an AgentOps instance running).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
AGENTOPS_URL   = os.environ.get("AGENTOPS_API_URL", "").rstrip("/")
AGENT_ID       = os.environ.get("AGENTOPS_AGENT_ID", "gmp-deviation-review")
_DB_PATH       = Path(__file__).resolve().parent / "db" / "sop_assistant.db"

# Haiku pricing — must match routes/dashboard.py
_INPUT_PRICE   = 0.80 / 1_000_000
_OUTPUT_PRICE  = 4.00 / 1_000_000


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _api(method: str, path: str, body: dict | None = None) -> dict | None:
    """
    Call the AgentOps REST API. Returns parsed JSON on success, None on any error.
    Never raises — failures are logged and silently swallowed so the GMP agent
    continues operating even if AgentOps is unreachable.
    """
    if not AGENTOPS_URL:
        logger.debug("AGENTOPS_API_URL not set — skipping push (%s %s)", method, path)
        return None
    url  = f"{AGENTOPS_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urlrequest.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        err = exc.read().decode(errors="replace")
        logger.warning("AgentOps %s %s → HTTP %s: %s", method, path, exc.code, err[:200])
    except URLError as exc:
        logger.warning("AgentOps %s %s → connection error: %s", method, path, exc.reason)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AgentOps %s %s → unexpected error: %s", method, path, exc)
    return None


# ── Ensure agent is registered ─────────────────────────────────────────────────

_AGENT_REGISTERED = False   # module-level flag — avoid repeat calls per process

def ensure_agent_registered() -> None:
    """
    Register the GMP Deviation Review agent in AgentOps if it doesn't exist yet.
    Called lazily before the first push. Idempotent — AgentOps returns 409 if
    already registered, which is silently ignored.
    """
    global _AGENT_REGISTERED
    if _AGENT_REGISTERED or not AGENTOPS_URL:
        return

    payload = {
        "id":          AGENT_ID,
        "name":        "GMP Deviation Review - AI Assistant",
        "description": (
            "Pharmaceutical GMP deviation-review assistant. Accepts a structured deviation "
            "report, retrieves applicable SOPs via TF-IDF retrieval over 5 validated documents, "
            "classifies deviation severity (Critical / Major / Minor), identifies the primary "
            "applicable SOP and clause, proposes root cause hypothesis, recommends CAPA actions, "
            "and escalates by default when evidence is ambiguous or a patient-impacting process "
            "is involved. Built with Claude Haiku. Eval-gated before production."
        ),
        "owner": "Quality Assurance / Krishna Paruchuri",
        "classification": {
            "pii_access":           False,
            "production_critical":  True,
            "regulated_domain":     True,
            "data_classification":  "confidential",
            "escalates_to_human":   True,
            "product":              "GMP Deviation Review",
            "workflow":             "Pharmaceutical QA Team Review",
            "domain":               "Pharmaceutical",
            "environment":          "production",
            "model":                "claude-haiku-4-5",
            "eval_threshold":       0.75,   # pass if total >= 6/8
            "guardrails": [
                "No patient data or PII in output — mask or reject if present in input",
                "Always escalate when evidence is ambiguous, conflicting, or missing",
                "Do not make regulatory submission decisions — flag for Regulatory Affairs",
                "Output must be structured JSON with all 7 required fields",
                "If SOP documents are not retrievable, return escalate_flag=true",
                "For Critical deviations: identify containment actions before CAPA",
                "Refuse Minor classification if a released batch or patient-impacting step is involved",
            ],
            "golden_rules": [
                "Cite the applicable SOP by full document ID and clause (e.g. SOP-QA-042, Clause 5.3.1)",
                "State severity (Critical/Major/Minor) with explicit justification from the deviation report",
                "For Critical deviations, list containment actions as the first CAPA item",
                "Every CAPA must include: owner role, target date, effectiveness check criteria",
                "If root cause is unknown, state 'Root cause undetermined — investigation required'",
                "Flag Regulatory Affairs if deviation involves a released batch or validated process step",
                "Never recommend closing a deviation without a stated root cause or investigation plan",
            ],
        },
    }

    result = _api("POST", "/agents", payload)
    if result or True:   # 409 also means agent exists — either way we're done
        _AGENT_REGISTERED = True
        logger.info("AgentOps agent registration confirmed: %s", AGENT_ID)


# ── Push eval results ──────────────────────────────────────────────────────────

def push_eval_results(run_summary: dict[str, Any]) -> None:
    """
    Push an eval run summary to AgentOps after eval_runner.run_full_eval() completes.

    Args:
        run_summary: dict returned by run_full_eval(), with keys:
            run_id, actual (dict with pass_rate_pct, avg_total_score, avg_*), duration_s
    """
    ensure_agent_registered()
    if not AGENTOPS_URL:
        return

    actual = run_summary.get("actual", {})
    if not actual:
        logger.warning("AgentOps push_eval_results: no 'actual' summary in run_summary")
        return

    # Map the GMP eval 0–8 total score to AgentOps 0–10 avg_score convention
    # GMP rubric: 4 dimensions × 0–2 = 0–8 max.  Normalise to 0–10 for AgentOps.
    avg_total = actual.get("avg_total_score", 0.0)
    avg_score_10 = round(avg_total * 10 / 8, 2)

    total_cases  = actual.get("cases", 15)
    passed_cases = actual.get("pass_count", 0)
    pass_rate    = round(passed_cases / total_cases, 4) if total_cases else 0.0

    # Map 0–2 per-dimension scores to 0–10 for display in AgentOps
    def to10(val: float) -> float:
        return round(val * 10 / 2, 2)

    payload = {
        "version":      "1.0.0",
        "run_by":       "eval_runner (automated)",
        "pass_rate":    pass_rate,
        "avg_score":    avg_score_10,
        "total_cases":  total_cases,
        "passed_cases": passed_cases,
        "threshold_met": pass_rate >= 0.75,
        "dimensions": {
            "groundedness":   to10(actual.get("avg_groundedness",   0)),
            "classification": to10(actual.get("avg_classification", 0)),
            "escalation":     to10(actual.get("avg_escalation",     0)),
            "clarity":        to10(actual.get("avg_clarity",        0)),
            "baseline_pass_rate": run_summary.get("baseline", {}).get("pass_rate_pct", 0) / 100,
        },
    }

    result = _api("POST", f"/agents/{AGENT_ID}/evals", payload)
    if result:
        logger.info(
            "AgentOps eval pushed: run=%s pass_rate=%.0f%% avg=%.2f/10",
            run_summary.get("run_id", "?")[:8],
            pass_rate * 100,
            avg_score_10,
        )


# ── Push daily cost record ─────────────────────────────────────────────────────

def push_daily_cost(target_date: date | None = None) -> None:
    """
    Compute today's (or target_date's) token usage and cost from the traces table
    and push a cost record to AgentOps.

    Call this:
    - After every /api/review  (lightweight — one SQL query)
    - From POST /api/agentops/sync  (manual trigger)
    """
    ensure_agent_registered()
    if not AGENTOPS_URL:
        return

    d = (target_date or date.today()).isoformat()

    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                COUNT(*)                          AS review_count,
                SUM(COALESCE(input_tokens,  0))   AS input_tokens,
                SUM(COALESCE(output_tokens, 0))   AS output_tokens
            FROM   traces
            WHERE  SUBSTR(timestamp, 1, 10) = ?
            """,
            (d,),
        ).fetchone()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("AgentOps push_daily_cost: DB error: %s", exc)
        return

    review_count  = int(row["review_count"]  or 0)
    input_tokens  = int(row["input_tokens"]  or 0)
    output_tokens = int(row["output_tokens"] or 0)
    total_tokens  = input_tokens + output_tokens
    cost_usd      = round(input_tokens * _INPUT_PRICE + output_tokens * _OUTPUT_PRICE, 6)

    if review_count == 0:
        logger.debug("AgentOps push_daily_cost: no reviews for %s — skipping", d)
        return

    payload = {
        "recorded_date": d,
        "total_tokens":  total_tokens,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost_usd,
        "review_count":  review_count,
    }

    result = _api("POST", f"/agents/{AGENT_ID}/costs", payload)
    if result:
        logger.info(
            "AgentOps cost pushed: date=%s reviews=%d tokens=%d cost=$%.4f",
            d, review_count, total_tokens, cost_usd,
        )


# ── Push individual execution trace ───────────────────────────────────────────

def push_trace(
    trace_id:    str,
    timestamp:   str,
    user_input:  str,
    assessment:  dict,
    input_tokens:  int,
    output_tokens: int,
    latency_ms:    int,
    is_fallback:   bool,
) -> None:
    """
    Push a single /api/review execution trace to AgentOps after it completes.
    This populates the Execution Traces tab in the AgentOps dashboard.

    Args:
        trace_id:      UUID generated in routes/review.py
        timestamp:     ISO-8601 UTC string
        user_input:    raw deviation text (trimmed server-side to 500 chars by AgentOps)
        assessment:    the parsed LLM assessment dict (classification, severity, etc.)
        input_tokens:  tokens consumed by the LLM call
        output_tokens: tokens returned by the LLM call
        latency_ms:    end-to-end latency of the review pipeline
        is_fallback:   True if the LLM call used the safe fallback response
    """
    ensure_agent_registered()
    if not AGENTOPS_URL:
        return

    cost_usd = round(
        input_tokens * _INPUT_PRICE + output_tokens * _OUTPUT_PRICE, 6
    )

    payload = {
        "trace_id":       trace_id,
        "timestamp":      timestamp,
        "user_input":     user_input,
        "severity":       assessment.get("severity"),
        "qa_escalation":  bool(assessment.get("qa_escalation", False)),
        "classification": assessment.get("classification"),
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "cost_usd":       cost_usd,
        "latency_ms":     latency_ms,
        "is_fallback":    is_fallback,
        "model_output":   None,  # omit full output to keep payload lean
        "source_app":     "sop-deviation-review",
    }

    result = _api("POST", f"/agents/{AGENT_ID}/traces", payload)
    if result:
        logger.debug(
            "AgentOps trace pushed: id=%s severity=%s escalate=%s latency=%dms cost=$%.5f",
            trace_id[:8],
            assessment.get("severity", "?"),
            assessment.get("qa_escalation"),
            latency_ms,
            cost_usd,
        )


# ── Full sync (manual trigger) ─────────────────────────────────────────────────

def full_sync() -> dict[str, Any]:
    """
    Sync all recent data to AgentOps:
    - Daily cost records for the last 7 days (upsert-safe — AgentOps ignores duplicates)
    - Returns a summary of what was pushed.

    Called by POST /api/agentops/sync.
    """
    ensure_agent_registered()
    today = date.today()
    pushed = []

    for days_ago in range(7):
        d = date.fromordinal(today.toordinal() - days_ago)
        push_daily_cost(d)
        pushed.append(d.isoformat())

    return {
        "agent_id":    AGENT_ID,
        "synced_dates": pushed,
        "agentops_url": AGENTOPS_URL or "(not configured)",
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
