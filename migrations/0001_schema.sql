-- SOP Deviation Review Assistant — D1 schema (port of backend/db/schema.py)

-- Synthetic deviation scenarios (kept for parity with the Python schema).
CREATE TABLE IF NOT EXISTS cases (
    id               TEXT    PRIMARY KEY,          -- e.g. "CASE-001"
    scenario         TEXT    NOT NULL,             -- full deviation description
    area             TEXT    NOT NULL,             -- e.g. "Sample Management"
    type             TEXT    NOT NULL,             -- e.g. "Process Deviation"
    severity         TEXT    NOT NULL              -- "Low" | "Medium" | "High"
                     CHECK (severity IN ('Low', 'Medium', 'High')),
    expected_action  TEXT    NOT NULL
);

-- One row per /api/review call — full audit trail of every LLM interaction.
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

-- Thumbs-up / thumbs-down ratings tied to a specific trace.
CREATE TABLE IF NOT EXISTS feedback (
    id                  TEXT    PRIMARY KEY,       -- UUID v4
    trace_id            TEXT    NOT NULL           -- FK → traces.id
                        REFERENCES traces(id) ON DELETE CASCADE,
    rating              INTEGER NOT NULL           -- 1 = thumbs_up, -1 = thumbs_down
                        CHECK (rating IN (1, -1)),
    comment             TEXT,
    reviewer_correction TEXT,
    created_at          TEXT    NOT NULL           -- ISO-8601 UTC
);

-- One row per case per eval run, for every model_tag in that run.
CREATE TABLE IF NOT EXISTS eval_results (
    id              TEXT    PRIMARY KEY,           -- UUID v4
    case_id         TEXT    NOT NULL,              -- e.g. "CASE-002"
    run_id          TEXT    NOT NULL,              -- UUID grouping one complete eval run
    model_tag       TEXT    NOT NULL DEFAULT 'actual',  -- "actual" | "baseline_always_escalate"
    groundedness    INTEGER NOT NULL DEFAULT 0 CHECK (groundedness  BETWEEN 0 AND 2),
    classification  INTEGER NOT NULL DEFAULT 0 CHECK (classification BETWEEN 0 AND 2),
    escalation      INTEGER NOT NULL DEFAULT 0 CHECK (escalation    BETWEEN 0 AND 2),
    clarity         INTEGER NOT NULL DEFAULT 0 CHECK (clarity       BETWEEN 0 AND 2),
    overall_pass    INTEGER NOT NULL DEFAULT 0 CHECK (overall_pass IN (0, 1)),
    notes           TEXT,                          -- judge's 1-2 sentence explanation
    created_at      TEXT    NOT NULL               -- ISO-8601 UTC timestamp
);

-- Daily aggregate roll-ups (kept for parity with the Python schema).
CREATE TABLE IF NOT EXISTS metrics (
    id               TEXT    PRIMARY KEY,
    date             TEXT    NOT NULL UNIQUE,      -- "YYYY-MM-DD"
    total_chats      INTEGER NOT NULL DEFAULT 0,
    escalation_count INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms   REAL    NOT NULL DEFAULT 0.0,
    total_tokens     INTEGER NOT NULL DEFAULT 0,
    total_cost_usd   REAL    NOT NULL DEFAULT 0.0
);

-- Eval runs in progress. The Python backend ran all 15 cases in one 3–6 minute
-- request; the Worker runs one case per request, so the run's start is kept here.
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id      TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,                     -- shared created_at for all rows in the run
    started_ms  INTEGER NOT NULL                   -- epoch ms, for duration_s
);

-- Per-IP request log for the /api/review rate limit (replaces the in-memory
-- sliding window, which can't be shared across Worker isolates).
CREATE TABLE IF NOT EXISTS rate_limit_hits (
    ip  TEXT NOT NULL,
    ts  REAL NOT NULL                              -- epoch seconds
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_ip_ts ON rate_limit_hits(ip, ts);
