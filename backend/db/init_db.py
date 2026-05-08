"""
init_db.py — Initialize the SQLite database for the SOP Deviation Review Assistant.

Creates the database file and all tables if they do not already exist.
Safe to run multiple times — uses IF NOT EXISTS on every table.

Usage:
    python backend/db/init_db.py          # from project root
    python init_db.py                     # from backend/db/
"""

import sqlite3
import sys
import os
from pathlib import Path

# Force UTF-8 output on Windows so status symbols print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Resolve paths regardless of where the script is called from
# ---------------------------------------------------------------------------
THIS_DIR = Path(__file__).resolve().parent          # .../backend/db/
BACKEND_DIR = THIS_DIR.parent                       # .../backend/
PROJECT_ROOT = BACKEND_DIR.parent                   # .../sop-deviation-review/

DB_PATH = BACKEND_DIR / "db" / "sop_assistant.db"

# Allow running from project root OR from backend/db/
sys.path.insert(0, str(BACKEND_DIR))

from db.schema import ALL_TABLES


def get_db_path() -> Path:
    """Return the resolved path to the SQLite database file."""
    return DB_PATH


def init_db(db_path: Path | None = None) -> None:
    """
    Create the database file and all tables if they do not exist.

    Args:
        db_path: Override the default database path. Used in tests.
    """
    target = db_path or DB_PATH

    # Ensure the parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    print(f"[init_db] Database path : {target}")

    conn = sqlite3.connect(target)
    conn.execute("PRAGMA journal_mode=WAL;")       # better concurrent read performance
    conn.execute("PRAGMA foreign_keys=ON;")        # enforce FK constraints

    try:
        with conn:
            for table_name, create_sql in ALL_TABLES:
                conn.execute(create_sql)
                print(f"[init_db] ✓  Table ready : {table_name}")
    except sqlite3.Error as exc:
        print(f"[init_db] ✗  Error creating tables: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()

    print(f"[init_db] Database initialized successfully.")


def verify_tables(db_path: Path | None = None) -> list[str]:
    """
    Return the list of table names that exist in the database.
    Used for post-init verification and in tests.
    """
    target = db_path or DB_PATH
    conn = sqlite3.connect(target)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def print_table_info(db_path: Path | None = None) -> None:
    """Print column definitions for every table — useful for debugging."""
    target = db_path or DB_PATH
    conn = sqlite3.connect(target)
    try:
        tables = verify_tables(target)
        for table in tables:
            print(f"\n  [{table}]")
            cursor = conn.execute(f"PRAGMA table_info({table});")
            for col in cursor.fetchall():
                cid, name, col_type, notnull, default, pk = col
                pk_marker  = " PK"       if pk      else ""
                nn_marker  = " NOT NULL" if notnull  else ""
                def_marker = f" DEFAULT {default}" if default is not None else ""
                print(f"    {name:25s} {col_type:10s}{pk_marker}{nn_marker}{def_marker}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()

    expected = {"cases", "traces", "feedback", "eval_results", "metrics"}
    found    = set(verify_tables())

    missing = expected - found
    extra   = found - expected

    print("\n[init_db] Verification:")
    for name in sorted(expected):
        status = "✓" if name in found else "✗  MISSING"
        print(f"  {status}  {name}")

    if missing:
        print(f"\n[init_db] ERROR — missing tables: {missing}", file=sys.stderr)
        sys.exit(1)

    if extra:
        print(f"\n[init_db] Warning — unexpected tables found: {extra}")

    print("\n[init_db] Column layout:")
    print_table_info()

    print("\n[init_db] All checks passed.")
