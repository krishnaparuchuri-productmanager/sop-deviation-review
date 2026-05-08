"""
eval_runner.py — End-to-end evaluation pipeline for the SOP Deviation Review Assistant.

Loads 15 golden eval cases from data/eval_set.csv, runs each case through the full
agent pipeline (retrieval + LLM assessment), and scores every output using an
LLM-as-judge call to Claude Haiku on four rubric dimensions (0–2 each, max 8 points).

A parallel "always-escalate" baseline is evaluated on the same cases to contextualise
the real model's performance: the baseline always returns qa_escalation=True and
severity=High with a generic summary, which reveals how much value the agent adds
beyond the conservative-by-default policy.

Rubric (0–2 per dimension):
    groundedness   — does the response cite only supplied SOP context?
    classification — does severity level match the expected golden output?
    escalation     — does qa_escalation flag and rationale match expected action?
    clarity        — is the draft_summary clear, complete, and accurate?

Pass threshold: total score ≥ 6 / 8.

Usage (standalone):
    cd sop-deviation-review/backend
    python eval_runner.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from retrieval import search_sop                       # uvicorn from backend/
    from prompts   import assess_deviation
    from llm_client import call_haiku
except ImportError:
    from backend.retrieval  import search_sop              # pytest / project root
    from backend.prompts    import assess_deviation
    from backend.llm_client import call_haiku

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent
_DB_PATH     = _BACKEND_DIR / "db" / "sop_assistant.db"
_EVAL_CSV    = _BACKEND_DIR.parent / "data" / "eval_set.csv"

# Pass threshold: total across all four 0–2 dimensions must reach this value.
PASS_THRESHOLD = 6   # out of 8 maximum

# ---------------------------------------------------------------------------
# Always-escalate baseline
# A static model that never looks at the deviation — it always returns High /
# qa_escalation=True with generic text.  Its scores reveal the ceiling a
# "just escalate everything" policy achieves, so the real model's gains are
# visible at a glance.
# ---------------------------------------------------------------------------
_ALWAYS_ESCALATE_OUTPUT: dict[str, Any] = {
    "classification":   "Unknown",
    "severity":         "High",
    "impact":           (
        "All deviations are treated as high-risk by this baseline. "
        "No case-specific impact analysis has been performed."
    ),
    "immediate_action": "Escalate immediately to QA. Do not proceed without QA sign-off.",
    "qa_escalation":    True,
    "missing_info":     "All details require manual verification by a qualified QA person.",
    "draft_summary":    (
        "This deviation has been automatically escalated to QA for manual review. "
        "No risk-based assessment was performed. QA must review before any action is taken."
    ),
}

# ---------------------------------------------------------------------------
# LLM-as-judge: tool schema
# ---------------------------------------------------------------------------
_JUDGE_SYSTEM = (
    "You are an expert evaluator of pharmaceutical GMP deviation review outputs. "
    "Your task: compare an actual model response to a golden-reference expected output "
    "and assign integer scores 0–2 for each of four rubric dimensions. "
    "Be strict and consistent: award 2 only when the criterion is clearly met, "
    "1 when partially met, and 0 when not met. "
    "Call submit_eval_scores with your four scores and a brief explanation."
)

_JUDGE_TOOL: dict[str, Any] = {
    "name": "submit_eval_scores",
    "description": (
        "Submit numeric evaluation scores for a deviation review response "
        "compared to the golden-set expected output."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "groundedness": {
                "type": "integer",
                "description": (
                    "Does the response cite only SOP sections, procedures, and document IDs "
                    "that appear explicitly in the supplied SOP context?\n"
                    "2 = fully grounded — no unsupported SOP citations\n"
                    "1 = mostly grounded — one or two minor unsupported claims\n"
                    "0 = hallucinated — cites SOP IDs, section numbers, or procedures "
                    "not present in the supplied context"
                ),
            },
            "classification": {
                "type": "integer",
                "description": (
                    "Does the severity level match what the expected output indicates?\n"
                    "2 = exact match (e.g., both say High)\n"
                    "1 = one level off (e.g., Medium when High expected — borderline)\n"
                    "0 = clearly wrong (e.g., Low when High expected)"
                ),
            },
            "escalation": {
                "type": "integer",
                "description": (
                    "Does the qa_escalation flag match the expected action, "
                    "and is the rationale sound?\n"
                    "2 = flag matches expected AND rationale clearly supports the recommended action\n"
                    "1 = flag matches expected but rationale is weak or incomplete\n"
                    "0 = flag does not match expected (e.g., true when false expected)"
                ),
            },
            "clarity": {
                "type": "integer",
                "description": (
                    "Is the draft_summary clear, concise, and accurate?\n"
                    "2 = clear, factual, covers what happened + impact + recommended action\n"
                    "1 = adequate but missing some important details\n"
                    "0 = vague, inaccurate, or missing key information"
                ),
            },
            "notes": {
                "type": "string",
                "description": "1–2 sentences explaining the key scoring decisions.",
            },
        },
        "required": ["groundedness", "classification", "escalation", "clarity", "notes"],
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    """One row from eval_set.csv."""
    case_id:         str
    scenario:        str
    area:            str
    type_:           str    # "planned" | "unplanned"
    severity_hint:   str    # "high" | "medium" | "minor"
    expected_action: str
    expected_output: str    # Full golden-reference assessment text


@dataclass
class EvalResult:
    """Scored output for one (case, model_tag) pair."""
    case_id:        str
    run_id:         str
    model_tag:      str     # "actual" | "baseline_always_escalate"
    groundedness:   int     # 0–2
    classification: int     # 0–2
    escalation:     int     # 0–2
    clarity:        int     # 0–2
    overall_pass:   int     # 1 if total ≥ PASS_THRESHOLD
    notes:          str
    created_at:     str


# ---------------------------------------------------------------------------
# Load eval cases
# ---------------------------------------------------------------------------

def load_eval_cases(csv_path: Path = _EVAL_CSV) -> list[EvalCase]:
    """Read eval_set.csv and return a list of EvalCase objects."""
    cases: list[EvalCase] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cases.append(EvalCase(
                case_id         = row["case_id"].strip(),
                scenario        = row["scenario"].strip(),
                area            = row["area"].strip(),
                type_           = row["type"].strip(),
                severity_hint   = row["severity_hint"].strip(),
                expected_action = row["expected_action"].strip(),
                expected_output = row["expected_output"].strip(),
            ))
    return cases


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

def _score_with_judge(case: EvalCase, actual: dict[str, Any]) -> tuple[dict[str, int], str]:
    """
    Call Claude Haiku as a judge to score `actual` against the golden reference.

    Returns:
        (scores, notes)  where scores = {groundedness, classification, escalation, clarity}
        all integers 0–2.  On judge failure, neutral score 1 is returned for every dimension.
    """
    judge_prompt = (
        f"## Deviation Scenario\n{case.scenario}\n\n"
        f"## Expected Assessment (golden reference)\n{case.expected_output}\n\n"
        "## Actual Model Response\n"
        f"Severity         : {actual.get('severity', 'N/A')}\n"
        f"Classification   : {actual.get('classification', 'N/A')}\n"
        f"QA Escalation    : {actual.get('qa_escalation', 'N/A')}\n"
        f"Impact           : {actual.get('impact', 'N/A')}\n"
        f"Immediate Action : {actual.get('immediate_action', 'N/A')}\n"
        f"Draft Summary    : {actual.get('draft_summary', 'N/A')}\n\n"
        "Score the actual response on the four rubric dimensions by calling submit_eval_scores."
    )

    response = call_haiku(
        system_prompt = _JUDGE_SYSTEM,
        user_message  = judge_prompt,
        max_tokens    = 400,
        tools         = [_JUDGE_TOOL],
        tool_choice   = {"type": "tool", "name": "submit_eval_scores"},
    )

    if not response.success:
        return (
            {"groundedness": 1, "classification": 1, "escalation": 1, "clarity": 1},
            f"Judge call failed: {response.error}",
        )

    try:
        raw = json.loads(response.text)
        scores: dict[str, int] = {}
        for dim in ("groundedness", "classification", "escalation", "clarity"):
            scores[dim] = max(0, min(2, int(raw.get(dim, 1))))
        notes = str(raw.get("notes", ""))
        return scores, notes
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return (
            {"groundedness": 1, "classification": 1, "escalation": 1, "clarity": 1},
            f"Judge parse error: {exc}",
        )


# ---------------------------------------------------------------------------
# Run evaluation for one model
# ---------------------------------------------------------------------------

def run_model_eval(
    cases:     list[EvalCase],
    run_id:    str,
    model_tag: str,
    created_at: str,
    verbose:   bool = True,
) -> list[EvalResult]:
    """
    Run the pipeline (or baseline) + judge for every case.

    Args:
        cases:      EvalCase list from load_eval_cases().
        run_id:     UUID shared across this entire eval run.
        model_tag:  "actual" → full retrieval + LLM pipeline.
                    "baseline_always_escalate" → static always-escalate output.
        created_at: ISO-8601 UTC timestamp shared across all rows in this run.
        verbose:    Print per-case progress if True.
    """
    results: list[EvalResult] = []

    for i, case in enumerate(cases, 1):
        if verbose:
            print(f"  [{model_tag[:6]}] {i:>2}/{len(cases)}  {case.case_id} ...",
                  end="", flush=True)
        t0 = time.monotonic()

        # ── Step 1: obtain model output ─────────────────────────────────────
        if model_tag == "actual":
            try:
                sop_chunks = search_sop(case.scenario, top_k=3)
            except Exception as exc:          # noqa: BLE001
                sop_chunks = []
                if verbose:
                    print(f" [retrieval err: {exc}]", end="")
            actual = assess_deviation(case.scenario, sop_chunks)
        else:
            # Always-escalate baseline: no LLM call for the pipeline step
            actual = dict(_ALWAYS_ESCALATE_OUTPUT)

        # ── Step 2: judge scoring ────────────────────────────────────────────
        scores, notes = _score_with_judge(case, actual)
        total        = sum(scores.values())   # 0–8
        overall_pass = 1 if total >= PASS_THRESHOLD else 0

        elapsed = time.monotonic() - t0
        if verbose:
            flag = "PASS" if overall_pass else "FAIL"
            print(f"  {total}/8 {flag}  ({elapsed:.1f}s)")

        results.append(EvalResult(
            case_id        = case.case_id,
            run_id         = run_id,
            model_tag      = model_tag,
            groundedness   = scores["groundedness"],
            classification = scores["classification"],
            escalation     = scores["escalation"],
            clarity        = scores["clarity"],
            overall_pass   = overall_pass,
            notes          = notes,
            created_at     = created_at,
        ))

    return results


# ---------------------------------------------------------------------------
# Persist to SQLite
# ---------------------------------------------------------------------------

def save_results(results: list[EvalResult], db_path: Path = _DB_PATH) -> None:
    """Insert EvalResult rows into the eval_results table."""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            for r in results:
                conn.execute(
                    """
                    INSERT INTO eval_results
                        (id, case_id, run_id, model_tag,
                         groundedness, classification, escalation, clarity,
                         overall_pass, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        r.case_id, r.run_id, r.model_tag,
                        r.groundedness, r.classification,
                        r.escalation,   r.clarity,
                        r.overall_pass, r.notes, r.created_at,
                    ),
                )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------

def compute_summary(results: list[EvalResult]) -> dict[str, Any]:
    """Return a metric dict for a list of EvalResult objects."""
    def avg(vals: list[float]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    totals     = [r.groundedness + r.classification + r.escalation + r.clarity for r in results]
    pass_count = sum(r.overall_pass for r in results)

    return {
        "cases":              len(results),
        "pass_count":         pass_count,
        "pass_rate_pct":      round(pass_count / len(results) * 100, 1) if results else 0.0,
        "avg_total_score":    avg(totals),
        "avg_groundedness":   avg([r.groundedness   for r in results]),
        "avg_classification": avg([r.classification for r in results]),
        "avg_escalation":     avg([r.escalation     for r in results]),
        "avg_clarity":        avg([r.clarity        for r in results]),
    }


def print_summary(
    actual_results:   list[EvalResult],
    baseline_results: list[EvalResult],
) -> dict[str, Any]:
    """Print a formatted comparison table and return {actual, baseline} summary dicts."""
    a = compute_summary(actual_results)
    b = compute_summary(baseline_results)

    # ── Comparison table ────────────────────────────────────────────────────
    W = 52
    print("\n" + "=" * W)
    print("  EVAL RESULTS SUMMARY")
    print("=" * W)
    print(f"  {'Metric':<32} {'Actual':>7}  {'Baseline':>8}")
    print("-" * W)
    rows = [
        ("Pass rate (%)",         "pass_rate_pct"),
        ("Avg total score (/8)",  "avg_total_score"),
        ("  Groundedness (/2)",   "avg_groundedness"),
        ("  Classification (/2)", "avg_classification"),
        ("  Escalation (/2)",     "avg_escalation"),
        ("  Clarity (/2)",        "avg_clarity"),
    ]
    for label, key in rows:
        print(f"  {label:<32} {str(a[key]):>7}  {str(b[key]):>8}")
    print("=" * W)

    # ── Per-case breakdown (actual model only) ───────────────────────────────
    print("\n  Per-case breakdown (actual model):")
    for r in actual_results:
        total = r.groundedness + r.classification + r.escalation + r.clarity
        flag  = "✓" if r.overall_pass else "✗"
        print(
            f"  {flag} {r.case_id}  {total}/8  "
            f"G={r.groundedness} Cl={r.classification} "
            f"Es={r.escalation} Cy={r.clarity}"
        )
    print()

    return {"actual": a, "baseline": b}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_full_eval(verbose: bool = True) -> dict[str, Any]:
    """
    Load eval cases, run actual model + always-escalate baseline, judge every
    output, save results to SQLite, print summary.

    Returns:
        Summary dict with keys: run_id, actual, baseline, duration_s, total_rows.
    """
    t_start    = time.monotonic()
    run_id     = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if verbose:
        print(f"\n[eval] Starting run {run_id[:8]}…")

    cases = load_eval_cases()
    if verbose:
        print(f"[eval] Loaded {len(cases)} cases from {_EVAL_CSV.name}\n")

    # ── Actual model ─────────────────────────────────────────────────────────
    if verbose:
        print("[eval] ── Actual model (retrieval + LLM) ──")
    actual_results = run_model_eval(
        cases, run_id, model_tag="actual",
        created_at=created_at, verbose=verbose,
    )

    # ── Always-escalate baseline ─────────────────────────────────────────────
    if verbose:
        print("\n[eval] ── Always-escalate baseline ──")
    baseline_results = run_model_eval(
        cases, run_id, model_tag="baseline_always_escalate",
        created_at=created_at, verbose=verbose,
    )

    # ── Persist ──────────────────────────────────────────────────────────────
    all_results = actual_results + baseline_results
    save_results(all_results)
    if verbose:
        print(f"\n[eval] Saved {len(all_results)} rows to eval_results table.")

    # ── Summary ──────────────────────────────────────────────────────────────
    summary = print_summary(actual_results, baseline_results)
    summary["run_id"]     = run_id
    summary["duration_s"] = round(time.monotonic() - t_start, 1)
    summary["total_rows"] = len(all_results)

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Ensure stdout uses UTF-8 on Windows so check marks print correctly.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_full_eval()
