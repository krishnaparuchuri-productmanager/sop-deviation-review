"""
seed/demo_seed.py — Insert realistic demo traces and feedback so the dashboard
shows meaningful data immediately after a fresh deployment.

Called once from main.py lifespan if the traces table is empty.
All data is synthetic — no real patient or batch information.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "sop_assistant.db"

# ---------------------------------------------------------------------------
# Static demo traces — realistic GMP deviation scenarios
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)

def _ts(days_ago: int, hour: int = 10) -> str:
    dt = _NOW - timedelta(days=days_ago, hours=(_NOW.hour - hour))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_DEMO_TRACES = [
    {
        "user_input": (
            "The temperature monitoring log for Cold Room CR-03 is missing entries "
            "for the period 06:00–14:00 yesterday. The room holds finished product "
            "stability samples and three retained injectable batches."
        ),
        "model_output": json.dumps({
            "classification": "Environmental",
            "severity": "High",
            "impact": "Potential loss of cold-chain integrity for retained injectable batches and stability samples.",
            "immediate_action": "Quarantine affected batches. Retrieve continuous logger data to confirm actual temperature. Notify QA immediately.",
            "qa_escalation": True,
            "missing_info": "Continuous data logger readings for the gap period.",
            "draft_summary": "A gap in the paper temperature log for CR-03 (06:00–14:00) was identified. Continuous logger data must be reviewed to confirm excursion status before any disposition decision."
        }),
        "severity": "High",
        "qa_escalation": 1,
        "latency_ms": 4230,
        "input_tokens": 812,
        "output_tokens": 198,
        "timestamp": _ts(0, 9),
    },
    {
        "user_input": (
            "An analyst completed the in-process dissolution test for Batch TAB-1177 "
            "without performing the required media deaeration step as specified in "
            "STP-022. Results have been entered into the LIMS and are pending QA approval."
        ),
        "model_output": json.dumps({
            "classification": "Laboratory",
            "severity": "Medium",
            "impact": "Dissolution results may be artificially elevated or depressed. Data integrity concern as results are already in LIMS.",
            "immediate_action": "Place LIMS results on hold. Repeat dissolution test with deaeration. Raise CAPA for analyst retraining on STP-022.",
            "qa_escalation": True,
            "missing_info": "None",
            "draft_summary": "The deaeration step in STP-022 was omitted during dissolution testing for TAB-1177. All results are on hold pending retest with the correct method."
        }),
        "severity": "Medium",
        "qa_escalation": 1,
        "latency_ms": 3870,
        "input_tokens": 796,
        "output_tokens": 187,
        "timestamp": _ts(1, 11),
    },
    {
        "user_input": (
            "During final packaging inspection for Batch PKG-0892, the QA line inspector "
            "found that the secondary carton label shows Lot No. PKG-0829 instead of the "
            "correct PKG-0892. Approximately 3,200 units have already been labelled."
        ),
        "model_output": json.dumps({
            "classification": "Labelling",
            "severity": "High",
            "impact": "Mislabelled product cannot be distributed. Risk of mix-up if units leave the site.",
            "immediate_action": "Stop packaging line. Quarantine all 3,200 labelled units. Confirm no units have left the warehouse. Initiate relabelling under QA supervision.",
            "qa_escalation": True,
            "missing_info": "Confirmation of whether any units reached the warehouse dispatch area.",
            "draft_summary": "Incorrect lot number (PKG-0829) was printed on secondary cartons for Batch PKG-0892. 3,200 units quarantined; relabelling authorised by QA pending root cause investigation."
        }),
        "severity": "High",
        "qa_escalation": 1,
        "latency_ms": 4110,
        "input_tokens": 824,
        "output_tokens": 201,
        "timestamp": _ts(1, 14),
    },
    {
        "user_input": (
            "The autoclave used for sterilising equipment in the aseptic fill suite "
            "triggered a high-pressure abort alarm mid-cycle during a sterilisation "
            "run for Batch INJ-0044. The cycle aborted at 78% completion."
        ),
        "model_output": json.dumps({
            "classification": "Equipment",
            "severity": "High",
            "impact": "Equipment components may not be sterile. Batch INJ-0044 cannot proceed until sterilisation is confirmed.",
            "immediate_action": "Quarantine all components from the aborted run. Do not use until re-sterilised. Remove autoclave from service and initiate equipment investigation.",
            "qa_escalation": True,
            "missing_info": "Engineering fault code from the autoclave PLC log.",
            "draft_summary": "Autoclave AB-07 aborted a sterilisation cycle at 78% due to a high-pressure alarm. All affected components quarantined; equipment under investigation."
        }),
        "severity": "High",
        "qa_escalation": 1,
        "latency_ms": 3950,
        "input_tokens": 803,
        "output_tokens": 195,
        "timestamp": _ts(2, 9),
    },
    {
        "user_input": (
            "Operator on Filling Line 2 recorded a fill volume of 5.12 mL for Batch "
            "LIQ-0307 against a specification of 5.00 ± 0.10 mL. Two consecutive IPC "
            "checks both showed the same over-fill. The line has been stopped."
        ),
        "model_output": json.dumps({
            "classification": "Process",
            "severity": "Medium",
            "impact": "Batch may be out-of-specification on fill volume. Regulatory label claim is 5 mL; over-fill may create compliance risk.",
            "immediate_action": "Retain all filled vials since last in-spec IPC. Recalibrate filling heads and recheck against specification before restarting.",
            "qa_escalation": True,
            "missing_info": "Volume of product filled since the last in-spec IPC check.",
            "draft_summary": "Fill volume for LIQ-0307 recorded at 5.12 mL (spec 5.00 ± 0.10 mL) on two consecutive checks. Line stopped; vials quarantined pending filling head recalibration."
        }),
        "severity": "Medium",
        "qa_escalation": 1,
        "latency_ms": 4080,
        "input_tokens": 811,
        "output_tokens": 193,
        "timestamp": _ts(3, 13),
    },
    {
        "user_input": (
            "A gowning audit of the Grade B anteroom found that one operator entered "
            "the cleanroom without completing the required glove sanitisation step. "
            "The operator had already been in the Grade B area for approximately 15 minutes."
        ),
        "model_output": json.dumps({
            "classification": "Environmental",
            "severity": "Medium",
            "impact": "Potential contamination risk in Grade B area. Batches being processed during the exposure window may be affected.",
            "immediate_action": "Identify all batches processed during the exposure window. Perform environmental monitoring of the affected area. Operator retraining required.",
            "qa_escalation": True,
            "missing_info": "Which batches were being processed in the Grade B area during the 15-minute window.",
            "draft_summary": "An operator entered Grade B without completing glove sanitisation and remained for 15 minutes. Environmental monitoring initiated; affected batches under review."
        }),
        "severity": "Medium",
        "qa_escalation": 1,
        "latency_ms": 3760,
        "input_tokens": 788,
        "output_tokens": 184,
        "timestamp": _ts(3, 16),
    },
    {
        "user_input": (
            "The calibration certificate for balance BA-12 expired three days ago. "
            "The balance was used for three routine IPC weighing checks on Batch "
            "GRN-0218 before the expiry was noticed."
        ),
        "model_output": json.dumps({
            "classification": "Equipment",
            "severity": "Low",
            "impact": "Weighing data from IPC checks may be unreliable. Risk is low as balance calibration rarely drifts significantly over 3 days.",
            "immediate_action": "Withdraw BA-12 from service and send for immediate recalibration. Review IPC weighing data against historical calibration drift data for this balance.",
            "qa_escalation": False,
            "missing_info": "Historical calibration drift records for BA-12.",
            "draft_summary": "Balance BA-12 was used with an expired calibration certificate (3 days). Balance withdrawn; recalibration in progress. IPC data for GRN-0218 under review."
        }),
        "severity": "Low",
        "qa_escalation": 0,
        "latency_ms": 3410,
        "input_tokens": 772,
        "output_tokens": 178,
        "timestamp": _ts(4, 10),
    },
    {
        "user_input": (
            "During cleaning verification of Reactor R-06, swab samples from two "
            "internal locations exceeded the cleaning acceptance limit for active "
            "residue by 12% and 18% respectively. A third location passed."
        ),
        "model_output": json.dumps({
            "classification": "Cleaning",
            "severity": "High",
            "impact": "Reactor R-06 cannot be used for the next product campaign. Cross-contamination risk if the reactor is used before re-cleaning and re-verification.",
            "immediate_action": "Quarantine reactor R-06. Initiate re-cleaning per the validated cleaning procedure. Escalate to QA and Manufacturing management.",
            "qa_escalation": True,
            "missing_info": "Identity of the next scheduled product in R-06 and its therapeutic window.",
            "draft_summary": "Cleaning verification swabs at two of three locations in R-06 exceeded the active residue limit by up to 18%. Reactor quarantined; re-cleaning authorised by QA."
        }),
        "severity": "High",
        "qa_escalation": 1,
        "latency_ms": 4340,
        "input_tokens": 817,
        "output_tokens": 199,
        "timestamp": _ts(5, 11),
    },
    {
        "user_input": (
            "A routine environmental monitoring air sample from Grade C corridor CC-07 "
            "returned a total viable count of 45 CFU/m³ against an action limit of "
            "50 CFU/m³. The alert limit is 25 CFU/m³."
        ),
        "model_output": json.dumps({
            "classification": "Environmental",
            "severity": "Low",
            "impact": "Count is above alert limit but below action limit. Trend monitoring should be reviewed. No immediate product impact identified.",
            "immediate_action": "Investigate potential root causes (gowning, cleaning frequency, HVAC). Increase monitoring frequency for CC-07 until three consecutive passing results are obtained.",
            "qa_escalation": False,
            "missing_info": "Recent trend data for CC-07 over the past 4 weeks.",
            "draft_summary": "EM air sample for CC-07 recorded 45 CFU/m³ — above alert limit (25) but below action limit (50). Enhanced monitoring and root cause investigation initiated."
        }),
        "severity": "Low",
        "qa_escalation": 0,
        "latency_ms": 3520,
        "input_tokens": 779,
        "output_tokens": 182,
        "timestamp": _ts(6, 14),
    },
    {
        "user_input": (
            "Batch release documentation for ORL-0521 was signed by a QA officer whose "
            "training record for the relevant SOP (SOP-QA-031) lapsed two weeks ago. "
            "The batch has not yet been shipped."
        ),
        "model_output": json.dumps({
            "classification": "Documentation",
            "severity": "Medium",
            "impact": "Batch release may not be valid if signed by an officer whose training was lapsed. Potential GMP data integrity issue.",
            "immediate_action": "Do not ship the batch. Assess whether a qualified, currently trained QA officer must countersign or re-issue the release. Complete retraining for the original signatory.",
            "qa_escalation": True,
            "missing_info": "Whether the specific SOP content changed since the officer's last training.",
            "draft_summary": "A batch release document for ORL-0521 was signed by a QA officer with a lapsed training record for SOP-QA-031. Batch held; QA management review in progress."
        }),
        "severity": "Medium",
        "qa_escalation": 1,
        "latency_ms": 3890,
        "input_tokens": 798,
        "output_tokens": 191,
        "timestamp": _ts(6, 16),
    },
]

# ---------------------------------------------------------------------------
# Demo eval results — 15 actual + 15 baseline rows (one fixed run)
# Reflects ~87% pass rate for actual, ~53% for baseline
# ---------------------------------------------------------------------------
_EVAL_RUN_ID = "demo-eval-run-00000000-0000-0000-0000-000000000001"
_EVAL_RUN_TS = _ts(2, 8)

_EVAL_CASES = [
    # case_id, groundedness, classification, escalation, clarity, pass
    ("EVAL-001", 2, 2, 2, 2, 1),
    ("EVAL-002", 2, 2, 2, 1, 1),
    ("EVAL-003", 2, 2, 2, 2, 1),
    ("EVAL-004", 1, 2, 2, 2, 1),
    ("EVAL-005", 2, 1, 2, 2, 1),
    ("EVAL-006", 2, 2, 2, 2, 1),
    ("EVAL-007", 2, 2, 1, 2, 1),
    ("EVAL-008", 2, 2, 2, 2, 1),
    ("EVAL-009", 1, 1, 2, 2, 1),
    ("EVAL-010", 2, 2, 2, 2, 1),
    ("EVAL-011", 2, 2, 2, 1, 1),
    ("EVAL-012", 2, 2, 2, 2, 1),
    ("EVAL-013", 1, 2, 1, 1, 0),  # fail
    ("EVAL-014", 2, 2, 2, 2, 1),
    ("EVAL-015", 1, 1, 2, 1, 0),  # fail
]

_EVAL_BASELINE_CASES = [
    # baseline always escalates — scores lower on groundedness + classification
    ("EVAL-001", 1, 1, 2, 1, 0),
    ("EVAL-002", 1, 1, 2, 1, 0),
    ("EVAL-003", 2, 1, 2, 1, 1),
    ("EVAL-004", 1, 1, 2, 1, 0),
    ("EVAL-005", 1, 1, 2, 1, 0),
    ("EVAL-006", 2, 1, 2, 2, 1),
    ("EVAL-007", 1, 1, 2, 1, 0),
    ("EVAL-008", 1, 1, 2, 1, 0),
    ("EVAL-009", 2, 1, 2, 1, 1),
    ("EVAL-010", 1, 1, 2, 1, 0),
    ("EVAL-011", 1, 1, 2, 1, 0),
    ("EVAL-012", 2, 1, 2, 2, 1),
    ("EVAL-013", 1, 1, 2, 1, 0),
    ("EVAL-014", 1, 1, 2, 1, 0),
    ("EVAL-015", 1, 1, 2, 1, 0),
]

_DEMO_FEEDBACK = [
    # trace index 0 → thumbs up
    {"rating": 1,  "comment": "Accurate assessment, action was correct."},
    # trace index 1 → thumbs down with correction
    {"rating": -1, "comment": "Severity should be High, not Medium — LIMS integrity issue is critical.",
     "reviewer_correction": "Severity: High. QA hold on LIMS entry required before any further testing proceeds."},
    # trace index 2 → thumbs up
    {"rating": 1,  "comment": None},
    # trace index 5 → thumbs up
    {"rating": 1,  "comment": "Good catch on environmental monitoring."},
]
_FEEDBACK_TRACE_INDICES = [0, 1, 2, 5]


def seed_demo_data() -> None:
    """
    Insert demo traces and feedback if the traces table is empty.
    Safe to call on every startup — does nothing if data already exists.
    """
    conn = sqlite3.connect(_DB_PATH)
    try:
        trace_count = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        eval_count  = conn.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0]

        # Seed traces + feedback only if traces table is empty
        if trace_count > 0 and eval_count > 0:
            return  # Everything already seeded — do nothing

        trace_ids: list[str] = []

        if trace_count == 0:
            for t in _DEMO_TRACES:
                tid = str(uuid.uuid4())
                trace_ids.append(tid)
                conn.execute(
                    """
                    INSERT INTO traces
                        (id, timestamp, user_input, retrieved_chunks,
                         prompt_version, model_output, latency_ms,
                         input_tokens, output_tokens, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tid,
                        t["timestamp"],
                        t["user_input"],
                        json.dumps([]),
                        "v1",
                        t["model_output"],
                        t["latency_ms"],
                        t["input_tokens"],
                        t["output_tokens"],
                        None,
                    ),
                )

            for fb, idx in zip(_DEMO_FEEDBACK, _FEEDBACK_TRACE_INDICES):
                conn.execute(
                    """
                    INSERT INTO feedback
                        (id, trace_id, rating, comment,
                         reviewer_correction, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        trace_ids[idx],
                        fb["rating"],
                        fb.get("comment"),
                        fb.get("reviewer_correction"),
                        _ts(0),
                    ),
                )

        # Seed eval results only if missing
        if eval_count > 0:
            conn.commit()
            return

        for case_id, g, c, e, cl, p in _EVAL_CASES:
            conn.execute(
                """
                INSERT INTO eval_results
                    (id, case_id, run_id, model_tag,
                     groundedness, classification, escalation, clarity,
                     overall_pass, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), case_id, _EVAL_RUN_ID, "actual",
                 g, c, e, cl, p, "", _EVAL_RUN_TS),
            )
        for case_id, g, c, e, cl, p in _EVAL_BASELINE_CASES:
            conn.execute(
                """
                INSERT INTO eval_results
                    (id, case_id, run_id, model_tag,
                     groundedness, classification, escalation, clarity,
                     overall_pass, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), case_id, _EVAL_RUN_ID,
                 "baseline_always_escalate",
                 g, c, e, cl, p, "", _EVAL_RUN_TS),
            )

        conn.commit()
        print(f"[seed] Inserted {len(_DEMO_TRACES)} demo traces, {len(_DEMO_FEEDBACK)} feedback records, and {len(_EVAL_CASES) * 2} eval results.")

    except Exception as exc:  # noqa: BLE001
        print(f"[seed] Skipped — {exc}")
    finally:
        conn.close()
