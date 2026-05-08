"""One-time migration: change feedback.rating from TEXT to INTEGER (1/-1)."""
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path(__file__).parent / "backend" / "db" / "sop_assistant.db"
conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys=OFF;")

# Show current schema
row = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='feedback'"
).fetchone()
print("Current schema:", row[0] if row else "NOT FOUND")

# Create new table with INTEGER rating
conn.execute("""
    CREATE TABLE IF NOT EXISTS feedback_new (
        id                  TEXT    PRIMARY KEY,
        trace_id            TEXT    NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
        rating              INTEGER NOT NULL CHECK (rating IN (1, -1)),
        comment             TEXT,
        reviewer_correction TEXT,
        created_at          TEXT    NOT NULL
    )
""")

# Copy existing rows, converting 'thumbs_up' → 1, anything else → -1
n = conn.execute("""
    INSERT INTO feedback_new (id, trace_id, rating, comment, reviewer_correction, created_at)
    SELECT id, trace_id,
           CASE rating WHEN 'thumbs_up' THEN 1 ELSE -1 END,
           comment, reviewer_correction, created_at
    FROM feedback
""").rowcount

conn.execute("DROP TABLE feedback")
conn.execute("ALTER TABLE feedback_new RENAME TO feedback")
conn.execute("PRAGMA foreign_keys=ON;")
conn.commit()
conn.close()
print(f"Migration complete — {n} row(s) converted.")
