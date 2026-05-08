"""
schema.py — SQL CREATE TABLE statements for the SOP Deviation Review Assistant.

All tables use explicit column types and constraints.
Parameterized queries must be used everywhere these tables are accessed.
"""

# ---------------------------------------------------------------------------
# cases
# Synthetic deviation scenarios used for demos and the eval golden set.
# Populated from data/cases/synthetic_deviations.json at startup.
# ---------------------------------------------------------------------------
CREATE_CASES_TABLE = """
CREATE TABLE IF NOT EXISTS cases (
    id               TEXT    PRIMARY KEY,          -- e.g. "CASE-001"
    scenario         TEXT    NOT NULL,             -- full deviation description
    area             TEXT    NOT NULL,             -- e.g. "Sample Management"
    type             TEXT    NOT NULL,             -- e.g. "Process Deviation"
    severity         TEXT    NOT NULL              -- "Low" | "Medium" | "High"
                     CHECK (severity IN ('Low', 'Medium', 'High')),
    expected_action  TEXT    NOT NULL              -- "Escalate to QA" | "Log and Monitor" | "Immediate Corrective Action"
);
"""

# ---------------------------------------------------------------------------
# traces
# One row per /api/review call — full audit trail of every LLM interaction.
# Written by observability/tracer.py before the response is returned.
# ---------------------------------------------------------------------------
CREATE_TRACES_TABLE = """
CREATE TABLE IF NOT EXISTS traces (
    id               TEXT    PRIMARY KEY,          -- UUID v4
    timestamp        TEXT    NOT NULL,             -- ISO-8601 UTC e.g. "2026-05-07T14:32:00Z"
    user_input       TEXT    NOT NULL,             -- raw deviation description from user
    retrieved_chunks TEXT,                         -- JSON array of SOP chunk IDs used
    prompt_version   TEXT    NOT NULL DEFAULT 'v1',-- tracks prompt iteration
    model_output     TEXT,                         -- full raw JSON string returned by Haiku
    latency_ms       INTEGER,                      -- wall-clock time from request to response
    input_tokens     INTEGER,                      -- tokens in (prompt)
    output_tokens    INTEGER,                      -- tokens out (completion)
    error            TEXT                          -- NULL on success; error message on failure
);
"""

# ---------------------------------------------------------------------------
# feedback
# User thumbs-up / thumbs-down ratings tied to a specific trace.
#   rating = 1  → thumbs up   (reviewer agrees with the assessment)
#   rating = -1 → thumbs down (reviewer disagrees)
# reviewer_correction stores the corrected free-text when rating = -1.
# ---------------------------------------------------------------------------
CREATE_FEEDBACK_TABLE = """
CREATE TABLE IF NOT EXISTS feedback (
    id                  TEXT    PRIMARY KEY,       -- UUID v4
    trace_id            TEXT    NOT NULL           -- FK → traces.id
                        REFERENCES traces(id) ON DELETE CASCADE,
    rating              INTEGER NOT NULL           -- 1 = thumbs_up, -1 = thumbs_down
                        CHECK (rating IN (1, -1)),
    comment             TEXT,                      -- optional free-text note
    reviewer_correction TEXT,                      -- corrected output when rating = -1
    created_at          TEXT    NOT NULL           -- ISO-8601 UTC
);
"""

# ---------------------------------------------------------------------------
# eval_results
# One row per case per eval run, for every model_tag in that run.
#   model_tag = "actual"                   → the real agent pipeline
#   model_tag = "baseline_always_escalate" → always returns qa_escalation=True
#
# Rubric dimensions are scored 0–2 by an LLM-as-judge call to Haiku.
# A case "passes" when the total of all four dimensions reaches ≥ 6 / 8.
# ---------------------------------------------------------------------------
CREATE_EVAL_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS eval_results (
    id              TEXT    PRIMARY KEY,           -- UUID v4
    case_id         TEXT    NOT NULL,              -- e.g. "CASE-002"
    run_id          TEXT    NOT NULL,              -- UUID grouping one complete eval run
    model_tag       TEXT    NOT NULL DEFAULT 'actual',  -- "actual" | "baseline_always_escalate"
    groundedness    INTEGER NOT NULL DEFAULT 0     -- 0=hallucinated refs, 1=partial, 2=fully grounded
                    CHECK (groundedness  BETWEEN 0 AND 2),
    classification  INTEGER NOT NULL DEFAULT 0     -- 0=wrong severity, 1=adjacent, 2=exact match
                    CHECK (classification BETWEEN 0 AND 2),
    escalation      INTEGER NOT NULL DEFAULT 0     -- 0=wrong flag, 1=correct+weak rationale, 2=correct+sound
                    CHECK (escalation    BETWEEN 0 AND 2),
    clarity         INTEGER NOT NULL DEFAULT 0     -- 0=vague, 1=adequate, 2=clear+complete
                    CHECK (clarity       BETWEEN 0 AND 2),
    overall_pass    INTEGER NOT NULL DEFAULT 0     -- 1 if total score >= 6/8
                    CHECK (overall_pass IN (0, 1)),
    notes           TEXT,                          -- judge's 1-2 sentence explanation
    created_at      TEXT    NOT NULL               -- ISO-8601 UTC timestamp
);
"""

# ---------------------------------------------------------------------------
# metrics
# Daily aggregate roll-ups written by a background job or on-demand.
# One row per calendar date; upserted each time metrics are refreshed.
# ---------------------------------------------------------------------------
CREATE_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS metrics (
    id               TEXT    PRIMARY KEY,          -- UUID v4
    date             TEXT    NOT NULL UNIQUE,      -- "YYYY-MM-DD"
    total_chats      INTEGER NOT NULL DEFAULT 0,
    escalation_count INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms   REAL    NOT NULL DEFAULT 0.0,
    total_tokens     INTEGER NOT NULL DEFAULT 0,
    total_cost_usd   REAL    NOT NULL DEFAULT 0.0
);
"""

# ---------------------------------------------------------------------------
# Ordered list used by init_db.py — tables are created in dependency order
# so foreign-key targets always exist before referencing tables.
# ---------------------------------------------------------------------------
ALL_TABLES = [
    ("cases",        CREATE_CASES_TABLE),
    ("traces",       CREATE_TRACES_TABLE),
    ("feedback",     CREATE_FEEDBACK_TABLE),
    ("eval_results", CREATE_EVAL_RESULTS_TABLE),
    ("metrics",      CREATE_METRICS_TABLE),
]
