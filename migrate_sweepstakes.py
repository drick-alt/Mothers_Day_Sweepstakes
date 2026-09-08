"""Migrate the DB from raffle model to sweepstakes model.

Adds the fields sweepstakes law requires you to disclose, plus AMOE
(Alternative Method of Entry) tracking so free entries are auditable.

Safe to re-run (idempotent).

WHY EACH FIELD EXISTS
---------------------
  sponsor_name / sponsor_address
      Official Rules must identify who is running the promotion. An
      anonymous sponsor is a red flag and in many states a defect.

  start_at / end_at
      A sweepstakes must have a defined entry period. Open-ended
      promotions are a compliance problem, and the end date is what
      the winner-selection date is measured against.

  prize_arv_total
      "Approximate Retail Value" must be disclosed. Several states key
      registration/bonding requirements off the total ARV (NY and FL
      are the usual $5,000 thresholds).

  eligibility_text / void_where
      Who may enter (age, residency) and where the promotion is void.

  entry_limit_per_person
      Caps AMOE abuse without making the free path unequal -- the cap
      applies to free and paid entries alike.
"""

import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "raffle.db"


def cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def add(conn, table, name, decl):
    if name not in cols(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        return True
    return False


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    added = []

    # ---- sweepstakes disclosure fields on the raffles table ----
    for name, decl in [
        ("sponsor_name",           "TEXT DEFAULT ''"),
        ("sponsor_address",        "TEXT DEFAULT ''"),
        ("sponsor_email",          "TEXT DEFAULT ''"),
        ("start_at",               "TEXT"),
        ("end_at",                 "TEXT"),
        ("prize_arv_total",        "REAL DEFAULT 0"),
        ("eligibility_text",       "TEXT DEFAULT ''"),
        ("void_where",             "TEXT DEFAULT ''"),
        ("entry_limit_per_person", "INTEGER DEFAULT 0"),   # 0 = no limit
        ("amoe_enabled",           "INTEGER DEFAULT 1"),
        ("winner_selection_text",  "TEXT DEFAULT ''"),
        ("rules_published",        "INTEGER DEFAULT 0"),
    ]:
        if add(conn, "raffles", name, decl):
            added.append(f"raffles.{name}")

    # ---- AMOE audit trail ----
    # Every free entry request is logged whether granted or rejected.
    # If the promotion is ever challenged, this table is the evidence
    # that the free path was real, open, and equal.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS amoe_requests (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            raffle_id    INTEGER NOT NULL,
            name         TEXT NOT NULL,
            email        TEXT NOT NULL,
            phone        TEXT DEFAULT '',
            address      TEXT DEFAULT '',
            ip_hash      TEXT DEFAULT '',
            granted      INTEGER NOT NULL DEFAULT 0,
            reason       TEXT DEFAULT '',
            order_id     INTEGER,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (raffle_id) REFERENCES raffles(id)
        )
    """)
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_amoe_email
                    ON amoe_requests(raffle_id, email)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_amoe_ip
                    ON amoe_requests(raffle_id, ip_hash, created_at)""")

    # ---- entry_source on orders: how did this entry arrive? ----
    # 'purchase' | 'amoe' | 'comp'
    #   purchase = paid
    #   amoe     = self-service free entry (the legal free path)
    #   comp     = admin-issued free ticket (event giveaway)
    # amoe and comp are both free, but they are NOT the same thing
    # legally -- amoe is the published alternative method, comp is a
    # discretionary gift. Keep them distinguishable.
    if add(conn, "orders", "entry_source", "TEXT DEFAULT 'purchase'"):
        added.append("orders.entry_source")

    # Backfill: existing comp orders are 'comp', everything else 'purchase'
    conn.execute("""
        UPDATE orders SET entry_source = 'comp'
        WHERE payment_method = 'comp' AND entry_source = 'purchase'
    """)

    conn.commit()

    print("SWEEPSTAKES MIGRATION")
    print("=" * 60)
    if added:
        for a in added:
            print(f"  added   {a}")
    else:
        print("  (all columns already present)")

    n = conn.execute("SELECT COUNT(*) c FROM amoe_requests").fetchone()["c"]
    print(f"  amoe_requests table ready ({n} rows)")

    src = conn.execute("""SELECT entry_source, COUNT(*) c
                          FROM orders GROUP BY entry_source""").fetchall()
    print("\n  entry_source breakdown:")
    for r in src:
        print(f"    {r['entry_source']:10} {r['c']}")

    tot = conn.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
    print(f"\n  tickets preserved: {tot}")
    conn.close()


if __name__ == "__main__":
    main()
