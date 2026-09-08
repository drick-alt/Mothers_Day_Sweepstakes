#!/usr/bin/env python3
"""Create a clean production DB without destroying the demo DB.

This copies the current database schema and sweepstakes configuration, then
removes demo entrants/orders/tickets/draws/logs. Use this when deploying to a
real host:

    python3 prepare_production_db.py
    cp raffle_prod_clean.db /data/raffle.db

The source raffle.db is never modified.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

SRC = Path(__file__).parent / "raffle.db"
OUT = Path(__file__).parent / "raffle_prod_clean.db"
KEEP_RAFFLE_ID = 6


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing source DB: {SRC}")
    if OUT.exists():
        OUT.unlink()
    shutil.copy2(SRC, OUT)

    conn = sqlite3.connect(OUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")

    # Keep the production sweepstakes config only. Everything else is demo data.
    keep = conn.execute("SELECT * FROM raffles WHERE id=?", (KEEP_RAFFLE_ID,)).fetchone()
    if not keep:
        raise SystemExit(f"Raffle/sweepstakes id {KEEP_RAFFLE_ID} not found")

    for table in ("payment_events", "amoe_requests", "draws", "tickets",
                  "orders", "buyers"):
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if exists:
            conn.execute(f"DELETE FROM {table}")

    conn.execute("DELETE FROM raffles WHERE id<>?", (KEEP_RAFFLE_ID,))
    conn.execute("UPDATE raffles SET status='open' WHERE id=?", (KEEP_RAFFLE_ID,))

    # Reset sequences for dynamic tables. Leave raffles alone so public links
    # remain /raffle/6, /admin/6, etc.
    for table in ("payment_events", "amoe_requests", "draws", "tickets",
                  "orders", "buyers"):
        conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))

    conn.commit()

    counts = {}
    for table in ("raffles", "buyers", "orders", "tickets", "draws",
                  "payment_events", "amoe_requests"):
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if exists:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    name = conn.execute("SELECT name FROM raffles WHERE id=?", (KEEP_RAFFLE_ID,)).fetchone()[0]
    conn.close()

    print(f"created: {OUT}")
    print(f"kept sweepstakes id {KEEP_RAFFLE_ID}: {name}")
    for k, v in counts.items():
        print(f"  {k:<15} {v}")


if __name__ == "__main__":
    main()
