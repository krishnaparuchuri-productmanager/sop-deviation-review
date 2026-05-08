"""
generate_csvs.py — Generates data/cases.csv and data/eval_set.csv.
Run from the project root:  python data/generate_csvs.py
"""

import csv
import os
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent   # data/

# ===========================================================================
# 25 synthetic deviation cases
# Columns: case_id, scenario, area, type, severity_hint, expected_action
# Areas   : Manufacturing | Packaging | QC | Documentation | Storage
# Types   : planned | unplanned
# Severity: minor | medium | high
# ===========================================================================
CASES = [
    # ── Manufacturing (5) ──────────────────────────────────────────────────
    {
        "case_id": "CASE-001",
        "scenario": (
            "During tablet compression, the operator noticed the compression force "
            "exceeded the validated upper limit of 15 kN by approximately 8% for a "
            "20-minute window. The out-of-range values were captured in the batch record. "
            "No visual defects were observed on the tablets."
        ),
        "area": "Manufacturing",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "Investigate and log deviation; QA review of in-process results before batch release.",
    },
    {
        "case_id": "CASE-002",
        "scenario": (
            "During API weighing for Batch MFG-0812, the balance printout shows "
            "2.53 kg dispensed against a target of 2.50 kg — a 1.2% excess. The error "
            "was discovered after blending had already commenced. The batch was placed "
            "on hold by the operator."
        ),
        "area": "Manufacturing",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Immediate QA escalation; batch on hold pending impact assessment on potency.",
    },
    {
        "case_id": "CASE-003",
        "scenario": (
            "A planned equipment qualification run was scheduled for the new high-shear "
            "granulator on Line 3. During the qualification, the inlet air temperature "
            "dropped to 38 °C instead of the target 55 °C for 10 minutes due to a "
            "building HVAC issue. The run was paused and the HVAC fault was corrected."
        ),
        "area": "Manufacturing",
        "type": "planned",
        "severity_hint": "minor",
        "expected_action": "Document deviation from qualification protocol; assess whether re-run of affected segment is required.",
    },
    {
        "case_id": "CASE-004",
        "scenario": (
            "An operator began manufacturing a new batch without completing the "
            "line clearance checklist for the previous product. A QC walkthrough "
            "identified leftover granules from the prior batch on the blending "
            "bowl rim. Manufacturing was halted immediately."
        ),
        "area": "Manufacturing",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Immediate QA escalation; both batches quarantined pending cross-contamination risk assessment.",
    },
    {
        "case_id": "CASE-005",
        "scenario": (
            "During a planned process improvement trial, the blending time was "
            "intentionally extended from 15 to 20 minutes per the approved trial "
            "protocol to evaluate content uniformity. All trial steps were pre-approved "
            "by QA and documented in the trial protocol."
        ),
        "area": "Manufacturing",
        "type": "planned",
        "severity_hint": "minor",
        "expected_action": "No deviation action required; document trial results against protocol. Routine QA review.",
    },

    # ── Packaging (5) ──────────────────────────────────────────────────────
    {
        "case_id": "CASE-006",
        "scenario": (
            "After completing a packaging run of 50,000 units, the QA line inspector "
            "discovered that the printed expiry date on the secondary carton reads "
            "NOV 2025 instead of NOV 2027. All 50,000 units are in the warehouse "
            "staging area awaiting dispatch."
        ),
        "area": "Packaging",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Immediate QA escalation; quarantine all 50,000 units; initiate recall assessment if any units have left the site.",
    },
    {
        "case_id": "CASE-007",
        "scenario": (
            "The line clearance documentation for Packaging Line 2 was not signed "
            "off before the start of a new batch run. The supervisor confirmed verbally "
            "that the line had been cleared, but the paper checklist signature was "
            "missing. Packaging of Batch PKG-0441 had already commenced."
        ),
        "area": "Packaging",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "Pause packaging run; complete retrospective line clearance verification; document deviation; QA review before resuming.",
    },
    {
        "case_id": "CASE-008",
        "scenario": (
            "A packaging line speed trial was conducted at 10% above the validated "
            "maximum speed as part of a planned capacity assessment study, pre-approved "
            "by the validation team. Seal integrity samples were collected at regular "
            "intervals. No failures were observed."
        ),
        "area": "Packaging",
        "type": "planned",
        "severity_hint": "minor",
        "expected_action": "Document trial outcome per validation protocol. No batch product at risk. Routine review.",
    },
    {
        "case_id": "CASE-009",
        "scenario": (
            "During routine in-process checks on the blister packaging line, "
            "3 out of 200 sampled units showed incomplete foil sealing — a visible "
            "gap of approximately 1 mm was detected on the peel test. The affected "
            "units were from the same reel of foil material."
        ),
        "area": "Packaging",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Halt line; quarantine all units from the affected foil reel; QA escalation; seal integrity investigation.",
    },
    {
        "case_id": "CASE-010",
        "scenario": (
            "The batch number printed on the secondary carton label for Batch PKG-0560 "
            "was found to have a transposed digit: label reads PKG-0506 instead of "
            "PKG-0560. The error was caught by QA during final release review. "
            "No units have left the warehouse."
        ),
        "area": "Packaging",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "Quarantine affected units; relabel under QA supervision; document deviation; release pending re-inspection.",
    },

    # ── QC (5) ─────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-011",
        "scenario": (
            "The HPLC column used for finished product assay testing was found to "
            "have exceeded its validated injection limit of 500 injections by 37 "
            "injections. The column was used for the last 37 injections without a "
            "column performance check. Two batch release results were generated "
            "using the over-limit column."
        ),
        "area": "QC",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "QA review of affected batch release data; system suitability retrospective assessment; column replaced.",
    },
    {
        "case_id": "CASE-012",
        "scenario": (
            "The primary dissolution test for Batch TAB-2240 returned a result of "
            "71% at 45 minutes against a specification of NLT 80%. An OOS "
            "investigation was initiated. Phase 1 laboratory investigation found no "
            "assignable cause. Phase 2 repeat testing on fresh samples is pending."
        ),
        "area": "QC",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Full OOS investigation per SOP; batch on hold; QA oversight of Phase 2 testing; QP notification if result confirmed.",
    },
    {
        "case_id": "CASE-013",
        "scenario": (
            "The primary reference standard used for an API identity test was "
            "found to have a retest date of 2026-03-31. The test was performed on "
            "2026-05-07 — 37 days after the retest date. The test result passed "
            "specification, but the validity of the standard is in question."
        ),
        "area": "QC",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Invalidate affected test result; retest using a current reference standard; QA review; assess other tests using the same standard.",
    },
    {
        "case_id": "CASE-014",
        "scenario": (
            "An analyst omitted the required 0.45 µm filtration step during sample "
            "preparation for a particulate matter test. The step was not flagged "
            "during the test and results were recorded. The omission was identified "
            "during a peer review of the raw data notebook."
        ),
        "area": "QC",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "Invalidate affected result; repeat test with correct preparation; document deviation; analyst retraining.",
    },
    {
        "case_id": "CASE-015",
        "scenario": (
            "A QC analyst completed a sterility test without a second analyst "
            "witnessing the critical aseptic steps, as required by the test method. "
            "The test returned a negative (pass) result. The witnessing gap was "
            "identified during a QA walkthrough the same day."
        ),
        "area": "QC",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "QA escalation; sterility result placed on hold; assess whether test can be accepted or must be invalidated and repeated.",
    },

    # ── Documentation (5) ──────────────────────────────────────────────────
    {
        "case_id": "CASE-016",
        "scenario": (
            "During a QA review of batch records for Batch GRN-0117, it was noted "
            "that two entries in the in-process weighing section were made in pencil "
            "rather than permanent ink. The entries appear to match expected values. "
            "No other anomalies were found in the record."
        ),
        "area": "Documentation",
        "type": "unplanned",
        "severity_hint": "minor",
        "expected_action": "Document deviation; re-enter values in permanent ink with explanation; analyst notified; no QA escalation required.",
    },
    {
        "case_id": "CASE-017",
        "scenario": (
            "The electronic batch record system logged the completion time for the "
            "granulation endpoint step as 14:52, but the paper witness log shows "
            "14:37 — a discrepancy of 15 minutes. Both records were signed by "
            "different operators. The cause of the discrepancy is unknown."
        ),
        "area": "Documentation",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "Investigate source of discrepancy; reconcile records; if unexplained, QA review for data integrity assessment.",
    },
    {
        "case_id": "CASE-018",
        "scenario": (
            "Correction fluid was used to mask an entry error on page 8 of the "
            "batch manufacturing record for Batch LYO-0033. The original entry "
            "is no longer legible. The identity of the person who applied the "
            "correction fluid is unknown."
        ),
        "area": "Documentation",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "QA escalation; data integrity investigation; batch on hold pending determination of what original entry contained.",
    },
    {
        "case_id": "CASE-019",
        "scenario": (
            "The second-person verification signature is missing for the sterilisation "
            "cycle parameter confirmation step in the batch record for Batch INJ-0099. "
            "This is a critical GMP step. The batch has been released and is currently "
            "in the distribution network."
        ),
        "area": "Documentation",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Immediate QA and QP escalation; assess whether distribution recall is required; regulatory notification may be needed.",
    },
    {
        "case_id": "CASE-020",
        "scenario": (
            "Batch record for Batch ORL-0204 was submitted for QA review with the "
            "yield reconciliation section left entirely blank. The production supervisor "
            "confirmed the yield was within range but did not complete the documentation "
            "before submission."
        ),
        "area": "Documentation",
        "type": "unplanned",
        "severity_hint": "minor",
        "expected_action": "Return batch record for completion; document deviation; no QA escalation required unless yield data cannot be reconstructed.",
    },

    # ── Storage (5) ────────────────────────────────────────────────────────
    {
        "case_id": "CASE-021",
        "scenario": (
            "The continuous temperature logger for Refrigerator RF-04 recorded a "
            "temperature of 10.2 °C between 02:10 and 04:40 (2.5-hour excursion). "
            "The normal storage range is 2–8 °C. The refrigerator holds finished "
            "product stability samples and three retained injectable batches."
        ),
        "area": "Storage",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "QA escalation; quarantine all affected samples; stability impact assessment; notify QP; consider regulatory reporting.",
    },
    {
        "case_id": "CASE-022",
        "scenario": (
            "The controlled substance storage vault was accessed by a single operator "
            "without the required dual-key sign-in. The operator retrieved a reference "
            "standard sample and signed out alone. The access log shows only one "
            "signature where two are required."
        ),
        "area": "Storage",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "QA escalation; verify inventory integrity; regulatory reporting assessment; retraining and access control review.",
    },
    {
        "case_id": "CASE-023",
        "scenario": (
            "Stability samples for Product XR-200 (12-month timepoint) were found "
            "stored upright in the stability chamber instead of inverted as specified "
            "in the stability protocol. The orientation error has been present for "
            "approximately 3 weeks based on storage logs."
        ),
        "area": "Storage",
        "type": "unplanned",
        "severity_hint": "medium",
        "expected_action": "Correct orientation immediately; document deviation; QA assessment of whether the 12-month data is still acceptable.",
    },
    {
        "case_id": "CASE-024",
        "scenario": (
            "During a routine warehouse audit, two pallets of a rejected raw material "
            "batch (rejected for microbial limits failure 6 weeks ago) were found "
            "stored in the approved materials zone rather than the segregated reject "
            "area. The pallets are intact and labeled REJECTED."
        ),
        "area": "Storage",
        "type": "unplanned",
        "severity_hint": "high",
        "expected_action": "Immediate relocation to reject zone; QA escalation; inventory check to confirm no rejected material was dispensed.",
    },
    {
        "case_id": "CASE-025",
        "scenario": (
            "As part of a planned preventive maintenance schedule, samples stored in "
            "Freezer FZ-02 were temporarily relocated to Freezer FZ-03 for 4 hours. "
            "The move was pre-approved by QA, temperature was continuously monitored "
            "during transfer, and all samples were returned to FZ-02 after maintenance."
        ),
        "area": "Storage",
        "type": "planned",
        "severity_hint": "minor",
        "expected_action": "No deviation action required. Document completed transfer per approved protocol. Routine QA sign-off.",
    },
]

# ===========================================================================
# 15-case eval set — subset of CASES with expected_output added
# eval case IDs chosen to cover all areas, all severity levels, planned+unplanned
# ===========================================================================
EVAL_CASE_IDS = {
    "CASE-002", "CASE-004", "CASE-005",   # Manufacturing: high, high, minor/planned
    "CASE-006", "CASE-007", "CASE-010",   # Packaging: high, medium, medium
    "CASE-012", "CASE-013", "CASE-015",   # QC: high x3
    "CASE-016", "CASE-018", "CASE-019",   # Documentation: minor, high, high
    "CASE-021", "CASE-023", "CASE-025",   # Storage: high, medium, minor/planned
}

EXPECTED_OUTPUTS = {
    "CASE-002": (
        "Deviation summary: During API weighing for Batch MFG-0812, 2.53 kg of active ingredient was dispensed "
        "against a target of 2.50 kg — a 1.2% excess — and blending commenced before the error was discovered. "
        "This constitutes an unplanned manufacturing deviation affecting product potency. "
        "SOP reference: SOP-DC-001 Section 3 (Critical Deviation — direct impact on potency) and "
        "SOP-IC-002 Section 4.1 (immediate quarantine of affected batch). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: A 1.2% API excess in a blend that has already been mixed may result in an out-of-specification "
        "potency result. The batch cannot be released without a full impact assessment and re-assay. "
        "The QP must be notified. Confidence: High."
    ),
    "CASE-004": (
        "Deviation summary: Manufacturing commenced on a new batch without completion of the line clearance "
        "checklist, and residual granules from the previous product were found on the blending bowl rim. "
        "This is an unplanned critical deviation with cross-contamination risk to both batches. "
        "SOP reference: SOP-IC-002 Section 4.1 (quarantine of affected material and downstream batches) and "
        "SOP-DC-001 Section 3 (Critical Deviation — potential product identity and purity impact). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: Physical evidence of cross-contamination between two batches is a critical GMP failure. "
        "Both batches must be quarantined and a full contamination risk assessment performed before any "
        "disposition decision is made. Confidence: High."
    ),
    "CASE-005": (
        "Deviation summary: Blending time was extended from 15 to 20 minutes as part of a pre-approved "
        "planned process improvement trial. All activities were conducted under an approved trial protocol "
        "with QA sign-off obtained in advance. "
        "SOP reference: SOP-DC-001 Section 2 (Scope — planned deviations from approved procedures). "
        "Risk level: Low. QA review required: No. "
        "Rationale: This is a planned deviation executed within an approved protocol. No uncontrolled "
        "departure from procedure occurred. Results should be documented against the trial protocol "
        "for review during routine QA oversight. Confidence: High."
    ),
    "CASE-006": (
        "Deviation summary: The expiry date printed on the secondary carton for 50,000 packaged units "
        "reads NOV 2025 instead of the correct NOV 2027 — a two-year labelling error. All units are "
        "currently in the warehouse staging area. This is a critical unplanned packaging deviation. "
        "SOP reference: SOP-DC-001 Section 3 (Critical Deviation — labelling error affecting product "
        "identity information) and SOP-IC-002 Section 4.1 (immediate quarantine). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: An incorrect expiry date constitutes a labelling error that could cause premature "
        "withdrawal of product or, if not caught, distribution of mislabelled product. Quarantine and "
        "recall assessment are mandatory. Confidence: High."
    ),
    "CASE-007": (
        "Deviation summary: Line clearance for Packaging Line 2 was not formally documented before "
        "commencement of Batch PKG-0441, creating a risk that product or labels from a previous batch "
        "could be present on the line. The supervisor confirmed verbal clearance but no written record exists. "
        "SOP reference: SOP-DC-001 Section 3 (Major Deviation) and SOP-IC-002 Section 4.4 (documentation "
        "integrity — written record required). "
        "Risk level: Medium. QA review required: Yes. "
        "Rationale: Missing line clearance documentation is a significant GMP gap. A retrospective physical "
        "inspection and reconciliation should be completed before the batch proceeds. QA must verify "
        "the line status before the run resumes. Confidence: High."
    ),
    "CASE-010": (
        "Deviation summary: The batch number on secondary carton labels for Batch PKG-0560 contains a "
        "transposed digit (PKG-0506 instead of PKG-0560). The error was identified during final QA review "
        "and no units have left the warehouse. "
        "SOP reference: SOP-DC-001 Section 3 (Major Deviation — labelling error affecting batch traceability). "
        "Risk level: Medium. QA review required: Yes. "
        "Rationale: A transposed batch number compromises batch traceability and could prevent effective "
        "recall if needed. All affected units must be quarantined and relabelled under QA supervision "
        "before release. Confidence: High."
    ),
    "CASE-012": (
        "Deviation summary: The dissolution test for Batch TAB-2240 returned a primary result of 71% at "
        "45 minutes against a specification of NLT 80% — a 9-percentage-point failure. An OOS investigation "
        "was initiated but Phase 1 found no assignable laboratory cause, necessitating Phase 2 retesting. "
        "SOP reference: SOP-IG-003 Section 4 (full investigation steps including Phase 2) and "
        "SOP-DC-001 Section 3 (Critical Deviation — direct impact on product efficacy). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: A confirmed dissolution failure on a finished batch has direct patient efficacy implications. "
        "The batch must remain on hold through the full OOS investigation. If Phase 2 confirms the failure, "
        "batch rejection and QP notification are required. Confidence: High."
    ),
    "CASE-013": (
        "Deviation summary: An API identity test was performed using a reference standard that had passed "
        "its retest date by 37 days. The test returned a passing result, but the validity of the reference "
        "standard — and therefore the test result — cannot be confirmed. "
        "SOP reference: SOP-DC-001 Section 3 (Major Deviation — use of expired reference standard compromises "
        "test result integrity) and SOP-IG-003 Section 4.2 (evidence gathering for extent-of-condition review). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: Identity testing performed with an expired reference standard is scientifically invalid. "
        "The result must be invalidated, the test repeated with a current standard, and all other tests "
        "using the same expired standard must be identified and assessed. Confidence: High."
    ),
    "CASE-015": (
        "Deviation summary: A sterility test was completed without a second analyst witnessing the critical "
        "aseptic steps, as required by the test method SOP. The test returned a negative (pass) result, "
        "but the absence of a witness means the integrity of the aseptic technique cannot be independently "
        "confirmed. "
        "SOP reference: SOP-DC-001 Section 3 (Critical Deviation — sterility test integrity) and "
        "SOP-IG-003 Section 4.6 (patient impact assessment required). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: Sterility testing without witnessing is a critical GMP failure. An unwitnessed sterility "
        "test result cannot be used for batch release. QA must determine whether the test must be invalidated "
        "and repeated. The QP must be notified before any disposition decision. Confidence: High."
    ),
    "CASE-016": (
        "Deviation summary: Two entries in the in-process weighing section of the batch record for "
        "Batch GRN-0117 were made in pencil rather than permanent ink, violating GMP documentation "
        "standards. The entries appear consistent with expected values and no other anomalies were found. "
        "SOP reference: SOP-DS-005 Section 4 (Making Entries — permanent ink required) and "
        "SOP-DC-001 Section 3 (Minor Deviation — no direct product quality impact). "
        "Risk level: Low. QA review required: No. "
        "Rationale: Pencil entries are a documentation procedural violation but do not affect product "
        "quality where values are consistent and corroborated. The entries should be re-documented in "
        "permanent ink with a note of explanation. Analyst should receive a reminder of documentation "
        "standards. Confidence: High."
    ),
    "CASE-018": (
        "Deviation summary: Correction fluid was applied to page 8 of the batch manufacturing record for "
        "Batch LYO-0033, rendering the original entry permanently illegible. The identity of the person "
        "responsible is unknown. This represents a serious data integrity violation. "
        "SOP reference: SOP-DS-005 Section 5 (Correcting Errors — correction fluid strictly prohibited) and "
        "SOP-DC-001 Section 3 (Critical Deviation — data integrity breach). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: Use of correction fluid to obscure an original entry is a critical data integrity "
        "violation under ALCOA+ principles. The original content is now unrecoverable from this record. "
        "The batch must be placed on hold and a full data integrity investigation initiated. "
        "Regulatory notification may be required. Confidence: High."
    ),
    "CASE-019": (
        "Deviation summary: The second-person verification signature for the sterilisation cycle "
        "parameter confirmation step is absent from the batch record for Batch INJ-0099. This is a "
        "critical mandatory step. The batch has been released and is currently in the distribution network. "
        "SOP reference: SOP-DC-001 Section 3 (Critical Deviation — missing critical process step "
        "verification in a released sterile product) and SOP-IC-002 Section 4.4 (evidence preservation). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: A missing verification signature on a critical sterilisation step in a released "
        "injectable product is a regulatory and patient safety issue. Immediate QA and QP escalation "
        "is mandatory. A distribution hold and potential recall assessment must be initiated without delay. "
        "Confidence: High."
    ),
    "CASE-021": (
        "Deviation summary: Refrigerator RF-04 recorded a temperature of 10.2 °C for a 2.5-hour "
        "window, exceeding the 2–8 °C storage specification. The unit contains finished product "
        "stability samples and three retained injectable batches, all of which were exposed to the "
        "temperature excursion. "
        "SOP reference: SOP-DC-001 Section 3 (Critical Deviation — storage condition excursion on "
        "injectable products) and SOP-IC-002 Section 4.1 (quarantine of all affected materials). "
        "Risk level: High. QA review required: Yes. "
        "Rationale: A 2.5-hour excursion to 10.2 °C on injectable retained batches and stability "
        "samples requires a full stability impact assessment. The QP must be notified and regulatory "
        "reporting should be assessed. No affected samples may be used for release or stability "
        "reporting until QA approves. Confidence: High."
    ),
    "CASE-023": (
        "Deviation summary: Stability samples for Product XR-200 at the 12-month timepoint were "
        "stored upright for approximately 3 weeks instead of inverted as specified in the stability "
        "protocol. The orientation error affects the validity of the 12-month stability data. "
        "SOP reference: SOP-DC-001 Section 3 (Major Deviation — departure from approved stability "
        "protocol storage conditions) and SOP-IG-003 Section 4.6 (product impact assessment). "
        "Risk level: Medium. QA review required: Yes. "
        "Rationale: Storage orientation is a controlled variable in stability studies. A 3-week "
        "deviation from the specified orientation may affect the scientific validity of the 12-month "
        "data. QA must assess whether the data is still acceptable or whether the timepoint must be "
        "repeated. Confidence: High."
    ),
    "CASE-025": (
        "Deviation summary: Samples stored in Freezer FZ-02 were temporarily relocated to Freezer FZ-03 "
        "for 4 hours during planned preventive maintenance. The transfer was pre-approved by QA, "
        "temperature was continuously monitored, and all samples were returned to FZ-02 after maintenance. "
        "SOP reference: SOP-DC-001 Section 2 (Scope — planned deviations with prior QA approval). "
        "Risk level: Low. QA review required: No. "
        "Rationale: This is a planned, pre-approved activity conducted within defined controls. "
        "Continuous temperature monitoring during transfer provides evidence that storage conditions "
        "were maintained. No GMP deviation occurred. Document the activity as a completed planned "
        "event and file the temperature records. Confidence: High."
    ),
}


# ===========================================================================
# Write cases.csv
# ===========================================================================
def write_cases_csv() -> Path:
    out_path = OUT_DIR / "cases.csv"
    fieldnames = ["case_id", "scenario", "area", "type", "severity_hint", "expected_action"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(CASES)
    print(f"[generate_csvs] Wrote {len(CASES)} rows -> {out_path}")
    return out_path


# ===========================================================================
# Write eval_set.csv
# ===========================================================================
def write_eval_set_csv() -> Path:
    out_path = OUT_DIR / "eval_set.csv"
    fieldnames = ["case_id", "scenario", "area", "type", "severity_hint",
                  "expected_action", "expected_output"]
    eval_rows = []
    for case in CASES:
        if case["case_id"] in EVAL_CASE_IDS:
            row = dict(case)
            row["expected_output"] = EXPECTED_OUTPUTS[case["case_id"]]
            eval_rows.append(row)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(eval_rows)
    print(f"[generate_csvs] Wrote {len(eval_rows)} rows -> {out_path}")
    return out_path


# ===========================================================================
# Verification
# ===========================================================================
def verify(cases_path: Path, eval_path: Path) -> None:
    import collections

    # --- cases.csv ---
    with open(cases_path, encoding="utf-8") as f:
        cases_rows = list(csv.DictReader(f))

    area_counts = collections.Counter(r["area"] for r in cases_rows)
    sev_counts  = collections.Counter(r["severity_hint"] for r in cases_rows)
    type_counts = collections.Counter(r["type"] for r in cases_rows)

    print(f"\n[verify] cases.csv — {len(cases_rows)} rows")
    print(f"  Areas    : {dict(area_counts)}")
    print(f"  Severity : {dict(sev_counts)}")
    print(f"  Types    : {dict(type_counts)}")

    assert len(cases_rows) == 25, f"Expected 25 rows, got {len(cases_rows)}"
    assert set(area_counts.keys()) == {"Manufacturing", "Packaging", "QC", "Documentation", "Storage"}
    assert set(sev_counts.keys()) == {"minor", "medium", "high"}

    # --- eval_set.csv ---
    with open(eval_path, encoding="utf-8") as f:
        eval_rows = list(csv.DictReader(f))

    print(f"\n[verify] eval_set.csv — {len(eval_rows)} rows")
    for row in eval_rows:
        assert row["expected_output"], f"Empty expected_output for {row['case_id']}"
        assert len(row["expected_output"]) > 50, f"expected_output too short for {row['case_id']}"

    assert len(eval_rows) == 15, f"Expected 15 rows, got {len(eval_rows)}"
    print(f"  expected_output present : all {len(eval_rows)} rows OK")

    print("\n[verify] All checks passed.")


if __name__ == "__main__":
    cases_path = write_cases_csv()
    eval_path  = write_eval_set_csv()
    verify(cases_path, eval_path)
