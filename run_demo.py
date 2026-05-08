"""
run_demo.py — Full 25-case demo for the SOP Deviation Review Assistant.

Steps for every case:
  1. POST /api/review  — submit the deviation scenario
  2. Validate response — all required fields present, severity in allowed values
  3. POST /api/feedback — rate thumbs-up (1) when QA escalation matches expected,
                          thumbs-down (-1) otherwise (with an explanatory comment)

After all 25 cases:
  4. Print a summary table
  5. Print current dashboard metrics
  6. POST /api/evals/run   — run the full eval suite (≈ 3-6 min)
  7. Print eval summary

Run from the project root:
    python run_demo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

# ── encoding fix for Windows terminal ─────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE      = "http://localhost:8001"
CASES_FILE = Path(__file__).parent / "data" / "cases" / "synthetic_deviations.json"

REQUIRED_FIELDS = {"classification", "severity", "impact", "immediate_action",
                   "qa_escalation", "draft_summary", "trace_id"}
VALID_SEVERITIES = {"Low", "Medium", "High"}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def post_json(path: str, body: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_json(path: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_response(resp: dict) -> list[str]:
    """Return a list of validation error strings (empty = pass)."""
    errors: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in resp:
            errors.append(f"missing field: {f}")
    if resp.get("severity") not in VALID_SEVERITIES:
        errors.append(f"severity '{resp.get('severity')}' not in {VALID_SEVERITIES}")
    for txt_field in ("impact", "immediate_action", "draft_summary"):
        val = resp.get(txt_field, "")
        if not val or not str(val).strip():
            errors.append(f"empty field: {txt_field}")
    return errors


# ── Rating logic ───────────────────────────────────────────────────────────────

def decide_rating(case: dict, resp: dict) -> tuple[int, str | None]:
    """
    Return (rating, comment) based on how well the model matched expectations.

    Rating 1  (thumbs up)   — qa_escalation AND severity both match expected
    Rating -1 (thumbs down) — at least one is wrong
    """
    expected_escalation = case["expected_action"] in ("Escalate to QA", "Immediate Corrective Action")
    got_escalation      = bool(resp.get("qa_escalation"))
    expected_severity   = case["severity"]
    got_severity        = resp.get("severity", "")

    issues: list[str] = []
    if got_escalation != expected_escalation:
        expected_str = "Escalate" if expected_escalation else "Log and Monitor"
        got_str      = "Escalate" if got_escalation      else "Log and Monitor"
        issues.append(f"Escalation: expected {expected_str}, got {got_str}")
    if got_severity != expected_severity:
        issues.append(f"Severity: expected {expected_severity}, got {got_severity}")

    if issues:
        return -1, "Reviewer correction: " + "; ".join(issues)
    return 1, None


# ── Table printing ─────────────────────────────────────────────────────────────

def fmt_row(*cells: str, widths: list[int]) -> str:
    parts = [str(c).ljust(w)[:w] for c, w in zip(cells, widths)]
    return "  ".join(parts)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 72)
    print("  SOP Deviation Review Assistant — Full 25-Case Demo")
    print("=" * 72)
    print()

    # ── Load cases ─────────────────────────────────────────────────────────────
    cases: list[dict] = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} cases from {CASES_FILE.name}")
    print()

    # ── Column widths for results table ────────────────────────────────────────
    COLS = [9, 10, 8, 8, 6, 6, 4, 5]    # id, area(abbr), exp_sev, got_sev, exp_esc, got_esc, valid, rate
    HDR  = ["CaseID", "Area", "E.Sev", "G.Sev", "E.Esc", "G.Esc", "OK?", "Rate"]
    print(fmt_row(*HDR, widths=COLS))
    print("-" * 72)

    results: list[dict] = []
    total_latency = 0
    passed_validation = 0
    thumbs_up = 0

    for i, case in enumerate(cases, start=1):
        case_id  = case["id"]
        scenario = case["scenario"]
        area_abbr = case["area"][:10]

        # 1. Submit review ───────────────────────────────────────────────────
        try:
            resp = post_json("/api/review", {"user_input": scenario, "case_id": case_id}, timeout=90)
        except urllib.error.URLError as exc:
            print(f"  {case_id}: NETWORK ERROR — {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  {case_id}: ERROR — {exc}")
            continue

        latency = resp.get("latency_ms", 0)
        total_latency += latency

        # 2. Validate ────────────────────────────────────────────────────────
        errs = validate_response(resp)
        valid_str = "YES" if not errs else "NO"
        if not errs:
            passed_validation += 1

        # 3. Rate ────────────────────────────────────────────────────────────
        rating, comment = decide_rating(case, resp)
        if rating == 1:
            thumbs_up += 1
        trace_id = resp.get("trace_id", "")

        try:
            fb_body: dict = {"trace_id": trace_id, "rating": rating}
            if comment:
                fb_body["comment"] = comment
            post_json("/api/feedback", fb_body, timeout=30)
        except Exception as exc:  # noqa: BLE001
            comment = f"[feedback error: {exc}]"

        # Store row for summary
        results.append({
            "case_id":    case_id,
            "area":       case["area"],
            "exp_sev":    case["severity"],
            "got_sev":    resp.get("severity", "?"),
            "exp_esc":    "Y" if case["expected_action"] != "Log and Monitor" else "N",
            "got_esc":    "Y" if resp.get("qa_escalation") else "N",
            "valid":      valid_str,
            "rating":     "+1" if rating == 1 else "-1",
            "latency_ms": latency,
            "trace_id":   trace_id,
            "errs":       errs,
        })

        # Print row
        row_str = fmt_row(
            case_id, area_abbr,
            case["severity"], resp.get("severity", "?"),
            "Y" if case["expected_action"] != "Log and Monitor" else "N",
            "Y" if resp.get("qa_escalation") else "N",
            valid_str,
            "+1" if rating == 1 else "-1",
            widths=COLS,
        )
        status = "" if not errs else f"  [WARN: {'; '.join(errs)}]"
        print(f"{row_str}{status}")

        # Small delay to avoid saturating Haiku rate limits
        if i < len(cases):
            time.sleep(0.5)

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(f"  Submitted   : {len(results)} / {len(cases)} cases")
    print(f"  Valid resp  : {passed_validation} / {len(results)}")
    print(f"  Thumbs-up   : {thumbs_up} / {len(results)}  "
          f"({100 * thumbs_up // max(len(results), 1)}%)")
    print(f"  Thumbs-down : {len(results) - thumbs_up} / {len(results)}")
    avg_lat = total_latency // max(len(results), 1)
    print(f"  Avg latency : {avg_lat} ms  ({avg_lat / 1000:.1f}s per review)")

    # Per-severity accuracy
    sev_hits  = sum(1 for r in results if r["got_sev"] == r["exp_sev"].replace("exp_sev",""))
    esc_hits  = sum(1 for r in results if r["exp_esc"] == r["got_esc"])
    print(f"  Sev match   : {sum(1 for r in results if r['got_sev'] == cases[i2]['severity'] for i2, _ in [(results.index(r), None)])}"
          f" / {len(results)} (see row comparison above)")
    print(f"  Esc match   : {esc_hits} / {len(results)}")
    print("=" * 72)

    # ── Dashboard metrics ──────────────────────────────────────────────────────
    print()
    print("Current dashboard metrics (GET /api/dashboard/metrics):")
    try:
        m = get_json("/api/dashboard/metrics")
        print(f"  total_chats      : {m['total_chats']}")
        print(f"  escalation_rate  : {m['escalation_rate']}%")
        print(f"  avg_latency_ms   : {m['avg_latency_ms']:.0f} ms")
        print(f"  total_tokens     : {m['total_tokens_used']:,}")
        print(f"  estimated_cost   : ${m['estimated_cost_usd']:.4f}")
        print(f"  downvote_rate    : {m['downvote_rate']}%")
        sevs = m.get("top_severity_breakdown", [])
        for s in sevs:
            print(f"  severity {s['severity']:6}: {s['count']} reviews")
    except Exception as exc:  # noqa: BLE001
        print(f"  [dashboard error: {exc}]")

    # ── Eval run ───────────────────────────────────────────────────────────────
    print()
    print("Running full eval suite (POST /api/evals/run) — this takes 3-6 minutes…")
    t_eval = time.time()
    try:
        eval_resp = post_json("/api/evals/run", {}, timeout=600)
        dur = time.time() - t_eval
        print(f"  Eval run complete in {dur:.0f}s")
        print(f"  run_id       : {eval_resp['run_id'][:16]}…")
        print(f"  total_rows   : {eval_resp['total_rows']}")
        a = eval_resp["actual"]
        b = eval_resp["baseline"]
        print()
        print("  Dimension scores (0-2 each):")
        print(f"  {'Metric':<22} {'Agent':>7}  {'Baseline':>9}")
        print("  " + "-" * 42)
        dims = [
            ("Groundedness",   "avg_groundedness"),
            ("Classification", "avg_classification"),
            ("Escalation",     "avg_escalation"),
            ("Clarity",        "avg_clarity"),
            ("TOTAL /8",       "avg_total_score"),
            ("Pass rate",      "pass_rate_pct"),
        ]
        for label, key in dims:
            av = a[key]
            bv = b[key]
            suffix = "%" if "rate" in key else ""
            print(f"  {label:<22} {av:>6.2f}{suffix}   {bv:>6.2f}{suffix}")
        print()
        print(f"  Agent pass rate  : {a['pass_rate_pct']:.0f}%  "
              f"({a['pass_count']}/{a['cases']})")
        print(f"  Baseline pass rt : {b['pass_rate_pct']:.0f}%  "
              f"({b['pass_count']}/{b['cases']})")
    except urllib.error.URLError as exc:
        print(f"  [eval error: {exc}]")
    except Exception as exc:  # noqa: BLE001
        print(f"  [eval error: {exc}]")

    print()
    print("Demo complete. Open http://localhost:5173 to view all 5 screens.")
    print()


if __name__ == "__main__":
    main()
