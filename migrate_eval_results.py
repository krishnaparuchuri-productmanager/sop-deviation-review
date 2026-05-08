"""One-time migration: rebuild eval_results with 0-2 rubric scores + model_tag + created_at."""
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path(__file__).parent / "backend" / "db" / "sop_assistant.db"
conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys=OFF;")

exists = conn.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='eval_results'"
).fetchone()[0]
n = conn.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0] if exists else 0
print(f"eval_results rows before migration: {n}")

conn.execute("DROP TABLE IF EXISTS eval_results")
conn.execute("""
CREATE TABLE eval_results (
    id              TEXT    PRIMARY KEY,
    case_id         TEXT    NOT NULL,
    run_id          TEXT    NOT NULL,
    model_tag       TEXT    NOT NULL DEFAULT 'actual',
    groundedness    INTEGER NOT NULL DEFAULT 0 CHECK (groundedness  BETWEEN 0 AND 2),
    classification  INTEGER NOT NULL DEFAULT 0 CHECK (classification BETWEEN 0 AND 2),
    escalation      INTEGER NOT NULL DEFAULT 0 CHECK (escalation    BETWEEN 0 AND 2),
    clarity         INTEGER NOT NULL DEFAULT 0 CHECK (clarity       BETWEEN 0 AND 2),
    overall_pass    INTEGER NOT NULL DEFAULT 0 CHECK (overall_pass  IN (0, 1)),
    notes           TEXT,
    created_at      TEXT    NOT NULL
)
""")
conn.execute("PRAGMA foreign_keys=ON;")
conn.commit()
conn.close()
print("Migration complete — eval_results rebuilt with 0-2 rubric + model_tag + created_at.")
