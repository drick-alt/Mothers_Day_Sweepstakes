"""Migrate raffle.db to add payment lifecycle. Safe to re-run (idempotent)."""

import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "raffle.db"


def cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def main():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = OFF")
    changed = []

    ocols = cols(conn, "orders")
    if "payment_status" not in ocols:
        # Existing rows predate payments -- they were honor-system sales, so
        # mark them paid to preserve the current pool and odds.
        conn.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT "
                     "NOT NULL DEFAULT 'paid'")
        changed.append("orders.payment_status")
    if "payment_method" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT "
                     "NOT NULL DEFAULT 'cash'")
        changed.append("orders.payment_method")
    if "provider_ref" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN provider_ref TEXT")
        changed.append("orders.provider_ref")
    if "memo_code" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN memo_code TEXT")
        changed.append("orders.memo_code")
    if "paid_at" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN paid_at TEXT")
        changed.append("orders.paid_at")

    tcols = cols(conn, "tickets")
    if "status" not in tcols:
        # 'active'   -> paid, counts in pool, eligible to win
        # 'pending'  -> reserved awaiting payment, does NOT count
        # 'void'     -> cancelled/expired, does NOT count
        conn.execute("ALTER TABLE tickets ADD COLUMN status TEXT "
                     "NOT NULL DEFAULT 'active'")
        changed.append("tickets.status")

    # Backfill: any legacy voided=1 rows become status='void'
    conn.execute("UPDATE tickets SET status='void' WHERE voided=1")

    # Backfill memo codes for legacy orders that lack one
    import secrets
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for (oid,) in conn.execute(
            "SELECT id FROM orders WHERE memo_code IS NULL").fetchall():
        code = "RAF-" + "".join(secrets.choice(alpha) for _ in range(6))
        conn.execute("UPDATE orders SET memo_code=? WHERE id=?", (code, oid))

    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status "
                 "ON tickets(raffle_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status "
                 "ON orders(raffle_id, payment_status)")

    # Audit trail for every payment state transition
    conn.execute("""CREATE TABLE IF NOT EXISTS payment_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id   INTEGER NOT NULL REFERENCES orders(id),
        event      TEXT NOT NULL,
        detail     TEXT,
        created_at TEXT NOT NULL
    )""")

    conn.commit()

    n_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    n_active = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE status='active'").fetchone()[0]
    conn.close()

    print("Migration complete.")
    print(f"  columns added: {', '.join(changed) if changed else 'none (already current)'}")
    print(f"  orders: {n_orders}")
    print(f"  active tickets preserved: {n_active}")


if __name__ == "__main__":
    main()
