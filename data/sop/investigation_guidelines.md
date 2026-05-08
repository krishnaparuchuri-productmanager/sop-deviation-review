# SOP-IG-003: Investigation Guidelines — Root Cause Analysis

**Document ID:** SOP-IG-003
**Version:** 3.0
**Effective Date:** 2025-03-01
**Department:** Quality Assurance
**Review Cycle:** Biennial

---

## 1. Purpose

This procedure provides a structured framework for investigating deviations to identify the true root cause, assess product impact, and generate findings that support effective corrective and preventive action. Investigations must be thorough, objective, evidence-based, and completed within defined timelines.

---

## 2. Scope

Applies to all Critical and Major deviations as classified under SOP-DC-001. Minor deviations may follow an abbreviated investigation at QA discretion. Also applies to Out-of-Specification (OOS) results, Out-of-Trend (OOT) observations, and customer complaints that require root cause determination.

---

## 3. Investigation Timelines

| Deviation Class | Preliminary Findings | Full Investigation Report |
|---|---|---|
| Critical | Within 3 business days | Within 20 business days |
| Major | Within 5 business days | Within 30 business days |
| Minor | Not required | Within 45 business days |

Timeline extensions require written QA Manager approval and must be documented in the eQMS.

---

## 4. Investigation Steps

### 4.1 Define the Problem Statement
Write a clear, factual problem statement that answers: What happened? When did it happen? Where did it happen? Who was involved? What was the intended procedure? Do not include suspected causes in the problem statement.

### 4.2 Gather Evidence
Collect all relevant evidence before it is altered or degraded: batch records, system logs, calibration records, environmental monitoring data, training records, and witness statements. Document chain of custody for all physical evidence.

### 4.3 Timeline Reconstruction
Build a chronological timeline from the last known good state to the point of discovery. Prefer objective records (timestamps, electronic signatures) over recalled verbal accounts.

### 4.4 Root Cause Analysis Tools
Apply at least one structured tool:

- **Fishbone Diagram (Ishikawa):** Categorize causes under Man, Machine, Method, Material, Measurement, and Environment. Rule each branch in or out with evidence.
- **5 Whys Analysis:** Ask "Why did this occur?" repeatedly until reaching a systemic cause. Each answer must be evidence-based, not assumed.
- **Fault Tree Analysis:** For complex events with multiple contributing factors, map the logical relationship between causes.

### 4.5 Root Cause vs. Contributing Factors
The root cause is the fundamental condition that, if eliminated, prevents recurrence. Contributing factors allowed the deviation to occur or worsen. Both must be documented separately.

### 4.6 Product and Patient Impact Assessment
Explicitly assess: Was product quality affected? Were distributed batches involved? Is there a patient safety risk? QA must review and sign this assessment before the investigation is closed.

---

## 5. Unacceptable Root Cause Conclusions

The following conclusions are not acceptable as root causes and will be returned for further investigation by QA:

- "Human error" without further explanation of why the error occurred or was not caught.
- "Analyst did not follow the SOP" without identifying why the SOP was not followed.
- "Unknown cause" without documented evidence that all reasonable avenues were explored.

---

## 6. Investigation Report Content

The completed investigation report must contain: problem statement, evidence log, timeline, root cause analysis tool output, identified root cause(s) and contributing factors, product impact assessment, extent of condition review, proposed CAPA actions, and QA sign-off.
