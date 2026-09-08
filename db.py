"""SQLite persistence with payment lifecycle.

KEY INVARIANT
-------------
Only tickets with status='active' count toward the pool and the odds.
Pending (unpaid) tickets are reserved but excluded, so an unpaid order can
never dilute a paying buyer's odds.
"""

import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("RAFFLE_DB_PATH", Path(__file__).parent / "raffle.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS raffles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    ticket_price  REAL NOT NULL DEFAULT 10.0,
    num_prizes    INTEGER NOT NULL DEFAULT 4,
    prize_1 TEXT DEFAULT 'Prize 1', prize_2 TEXT DEFAULT 'Prize 2',
    prize_3 TEXT DEFAULT 'Prize 3', prize_4 TEXT DEFAULT 'Prize 4',
    status        TEXT NOT NULL DEFAULT 'open',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS buyers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, email TEXT, phone TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    raffle_id      INTEGER NOT NULL REFERENCES raffles(id),
    buyer_id       INTEGER NOT NULL REFERENCES buyers(id),
    receipt_id     TEXT NOT NULL UNIQUE,
    lookup_code    TEXT NOT NULL UNIQUE,
    quantity       INTEGER NOT NULL,
    amount_paid    REAL NOT NULL,
    payment_status TEXT NOT NULL DEFAULT 'pending',
    payment_method TEXT NOT NULL DEFAULT 'card',
    provider_ref   TEXT,
    memo_code      TEXT,
    paid_at        TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raffle_id     INTEGER NOT NULL REFERENCES raffles(id),
    order_id      INTEGER NOT NULL REFERENCES orders(id),
    buyer_id      INTEGER NOT NULL REFERENCES buyers(id),
    ticket_number TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    voided        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    UNIQUE (raffle_id, ticket_number)
);
CREATE TABLE IF NOT EXISTS draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raffle_id INTEGER NOT NULL REFERENCES raffles(id),
    prize_slot INTEGER NOT NULL, prize_name TEXT NOT NULL,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id), drawn_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    event TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(raffle_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_buyer  ON tickets(raffle_id, buyer_id);
CREATE INDEX IF NOT EXISTS idx_orders_lookup  ON orders(lookup_code);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(raffle_id, payment_status);
"""

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_col(conn, table, name, decl):
    if name not in _cols(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _ensure_current_schema(conn):
    """Bring a fresh or old DB up to the current app schema.

    Render creates an empty persistent DB on first boot. SCHEMA handles the
    original tables; this function applies every later additive migration before
    optional seed data runs.
    """
    for name, decl in [
        ("sponsor_name", "TEXT DEFAULT ''"),
        ("sponsor_address", "TEXT DEFAULT ''"),
        ("sponsor_email", "TEXT DEFAULT ''"),
        ("start_at", "TEXT"),
        ("end_at", "TEXT"),
        ("prize_arv_total", "REAL DEFAULT 0"),
        ("eligibility_text", "TEXT DEFAULT ''"),
        ("void_where", "TEXT DEFAULT ''"),
        ("entry_limit_per_person", "INTEGER DEFAULT 0"),
        ("amoe_enabled", "INTEGER DEFAULT 1"),
        ("winner_selection_text", "TEXT DEFAULT ''"),
        ("rules_published", "INTEGER DEFAULT 0"),
        ("prize_1_url", "TEXT DEFAULT ''"),
        ("prize_2_url", "TEXT DEFAULT ''"),
        ("prize_3_url", "TEXT DEFAULT ''"),
        ("prize_4_url", "TEXT DEFAULT ''"),
        ("prize_1_img", "TEXT DEFAULT ''"),
        ("prize_2_img", "TEXT DEFAULT ''"),
        ("prize_3_img", "TEXT DEFAULT ''"),
        ("prize_4_img", "TEXT DEFAULT ''"),
        ("mail_name", "TEXT DEFAULT ''"),
        ("mail_attn", "TEXT DEFAULT ''"),
        ("mail_street", "TEXT DEFAULT ''"),
        ("mail_city", "TEXT DEFAULT ''"),
        ("mail_state", "TEXT DEFAULT ''"),
        ("mail_zip", "TEXT DEFAULT ''"),
        ("entry_limit_per_household", "INTEGER DEFAULT 0"),
    ]:
        _add_col(conn, "raffles", name, decl)

    _add_col(conn, "buyers", "address", "TEXT DEFAULT ''")

    for name, decl in [
        ("payment_status", "TEXT NOT NULL DEFAULT 'paid'"),
        ("payment_method", "TEXT NOT NULL DEFAULT 'cash'"),
        ("provider_ref", "TEXT"),
        ("memo_code", "TEXT"),
        ("paid_at", "TEXT"),
        ("entry_source", "TEXT DEFAULT 'purchase'"),
    ]:
        _add_col(conn, "orders", name, decl)

    _add_col(conn, "tickets", "status", "TEXT NOT NULL DEFAULT 'active'")
    conn.execute("UPDATE tickets SET status='void' WHERE voided=1")
    conn.execute("""CREATE TABLE IF NOT EXISTS amoe_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raffle_id INTEGER NOT NULL REFERENCES raffles(id),
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT DEFAULT '',
        address TEXT DEFAULT '',
        ip_hash TEXT DEFAULT '',
        granted INTEGER NOT NULL DEFAULT 0,
        reason TEXT DEFAULT '',
        order_id INTEGER REFERENCES orders(id),
        created_at TEXT NOT NULL,
        postmark_date TEXT DEFAULT '',
        received_date TEXT DEFAULT '',
        recorded_by TEXT DEFAULT ''
    )""")
    for name, decl in [
        ("postmark_date", "TEXT DEFAULT ''"),
        ("received_date", "TEXT DEFAULT ''"),
        ("recorded_by", "TEXT DEFAULT ''"),
    ]:
        _add_col(conn, "amoe_requests", name, decl)

    conn.execute("""UPDATE orders SET entry_source='comp'
                    WHERE payment_method='comp'
                      AND COALESCE(entry_source, 'purchase')='purchase'""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_amoe_email ON amoe_requests(raffle_id, email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_amoe_ip ON amoe_requests(raffle_id, ip_hash, created_at)")
    conn.commit()


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    _ensure_current_schema(conn)
    if os.environ.get("RAFFLE_SEED_ON_INIT") == "1":
        from seed_data import seed_if_empty
        seed_if_empty(conn)
    conn.close()


def gen_code(n=8):
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def log_event(conn, order_id, event, detail=None):
    conn.execute(
        "INSERT INTO payment_events (order_id,event,detail,created_at) "
        "VALUES (?,?,?,?)", (order_id, event, detail, now()))


# ------------------------------------------------------------------ raffles

def create_raffle(name, ticket_price=10.0, num_prizes=4, prizes=None):
    prizes = (list(prizes or ["Prize 1", "Prize 2", "Prize 3", "Prize 4"])
              + ["", "", "", ""])[:4]
    conn = connect()
    cur = conn.execute(
        """INSERT INTO raffles (name,ticket_price,num_prizes,
           prize_1,prize_2,prize_3,prize_4,status,created_at)
           VALUES (?,?,?,?,?,?,?,'open',?)""",
        (name, ticket_price, num_prizes, *prizes, now()))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_raffle(rid):
    conn = connect()
    r = conn.execute("SELECT * FROM raffles WHERE id=?", (rid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def list_raffles():
    conn = connect()
    rows = conn.execute("SELECT * FROM raffles ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ counts
# ALL of these count ONLY status='active'.

def total_tickets(rid):
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM tickets "
                     "WHERE raffle_id=? AND status='active'", (rid,)).fetchone()["c"]
    conn.close()
    return n


def pending_tickets(rid):
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM tickets "
                     "WHERE raffle_id=? AND status='pending'", (rid,)).fetchone()["c"]
    conn.close()
    return n


def buyer_ticket_count(rid, bid):
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM tickets WHERE raffle_id=? "
                     "AND buyer_id=? AND status='active'", (rid, bid)).fetchone()["c"]
    conn.close()
    return n


def revenue(rid):
    """Confirmed revenue only -- pending orders excluded."""
    conn = connect()
    r = conn.execute("SELECT COALESCE(SUM(amount_paid),0) t FROM orders "
                     "WHERE raffle_id=? AND payment_status='paid'", (rid,)).fetchone()["t"]
    conn.close()
    return r


def pending_revenue(rid):
    conn = connect()
    r = conn.execute("SELECT COALESCE(SUM(amount_paid),0) t FROM orders "
                     "WHERE raffle_id=? AND payment_status='pending'", (rid,)).fetchone()["t"]
    conn.close()
    return r


# ------------------------------------------------------------------ purchase

def create_order(rid, name, email, phone, quantity, payment_method,
                 memo_code=None):
    """Create buyer + order + tickets.

    Tickets start 'pending' for offline methods and for gateway methods that
    have not yet been confirmed. They only become 'active' on confirm_payment.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    conn = connect()
    try:
        raffle = conn.execute("SELECT * FROM raffles WHERE id=?", (rid,)).fetchone()
        if not raffle:
            raise ValueError("raffle not found")
        if raffle["status"] != "open":
            raise ValueError("raffle is closed")

        buyer = None
        if email:
            buyer = conn.execute("SELECT * FROM buyers WHERE email=?",
                                 (email,)).fetchone()
        if buyer:
            bid = buyer["id"]
        else:
            bid = conn.execute(
                "INSERT INTO buyers (name,email,phone,created_at) VALUES (?,?,?,?)",
                (name, email, phone, now())).lastrowid

        receipt_id = "R-" + gen_code(10)
        lookup = gen_code(8)
        amount = quantity * raffle["ticket_price"]

        oid = conn.execute(
            """INSERT INTO orders (raffle_id,buyer_id,receipt_id,lookup_code,
               quantity,amount_paid,payment_status,payment_method,memo_code,created_at)
               VALUES (?,?,?,?,?,?,'pending',?,?,?)""",
            (rid, bid, receipt_id, lookup, quantity, amount,
             payment_method, memo_code, now())).lastrowid

        # Reserve sequential numbers across ALL tickets so numbers never collide
        start = conn.execute("SELECT COUNT(*) c FROM tickets WHERE raffle_id=?",
                             (rid,)).fetchone()["c"]
        nums = []
        for i in range(quantity):
            tn = f"{start + i + 1:06d}"
            conn.execute(
                """INSERT INTO tickets (raffle_id,order_id,buyer_id,
                   ticket_number,status,created_at) VALUES (?,?,?,?,'pending',?)""",
                (rid, oid, bid, tn, now()))
            nums.append(tn)

        log_event(conn, oid, "order_created",
                  f"method={payment_method} qty={quantity} amount={amount}")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return {"order_id": oid, "buyer_id": bid, "raffle_id": rid,
            "receipt_id": receipt_id, "lookup_code": lookup,
            "quantity": quantity, "amount_paid": amount,
            "memo_code": memo_code, "payment_method": payment_method,
            "ticket_numbers": nums}


def confirm_payment(lookup_code, provider_ref=None, source="manual"):
    """Flip an order to paid and activate its tickets.

    IDEMPOTENT -- a duplicate webhook cannot double-activate. Returns True if
    this call performed the transition, False if it was already paid.
    """
    conn = connect()
    try:
        o = conn.execute("SELECT * FROM orders WHERE lookup_code=?",
                         (lookup_code,)).fetchone()
        if not o:
            raise ValueError("order not found")
        if o["payment_status"] == "paid":
            log_event(conn, o["id"], "confirm_duplicate", f"source={source}")
            conn.commit()
            conn.close()
            return False

        conn.execute("""UPDATE orders SET payment_status='paid',
                        provider_ref=COALESCE(?,provider_ref), paid_at=?
                        WHERE id=?""", (provider_ref, now(), o["id"]))
        conn.execute("UPDATE tickets SET status='active' "
                     "WHERE order_id=? AND status='pending'", (o["id"],))
        log_event(conn, o["id"], "payment_confirmed",
                  f"source={source} ref={provider_ref}")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return True


def cancel_order(lookup_code, reason="cancelled"):
    """Void an unpaid order. Refuses to touch a paid one."""
    conn = connect()
    try:
        o = conn.execute("SELECT * FROM orders WHERE lookup_code=?",
                         (lookup_code,)).fetchone()
        if not o:
            raise ValueError("order not found")
        if o["payment_status"] == "paid":
            raise ValueError("cannot cancel a paid order")
        conn.execute("UPDATE orders SET payment_status='cancelled' WHERE id=?",
                     (o["id"],))
        conn.execute("UPDATE tickets SET status='void', voided=1 WHERE order_id=?",
                     (o["id"],))
        log_event(conn, o["id"], "order_cancelled", reason)
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return True


def set_provider_ref(lookup_code, ref):
    conn = connect()
    o = conn.execute("SELECT id FROM orders WHERE lookup_code=?",
                     (lookup_code,)).fetchone()
    if o:
        conn.execute("UPDATE orders SET provider_ref=? WHERE id=?", (ref, o["id"]))
        log_event(conn, o["id"], "provider_session", ref)
        conn.commit()
    conn.close()


# ------------------------------------------------------------------ reads

def issue_comp_tickets(rid, name, email, phone, quantity, note=None):
    """Issue FREE giveaway tickets at an event.

    Differs from create_order in three ways:
      * amount_paid is forced to 0.00 regardless of ticket price
      * payment_status is 'paid' immediately (no approval step)
      * tickets are 'active' immediately -- they are real entries

    They count in the pool and the odds exactly like a purchased ticket,
    but contribute nothing to revenue.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    conn = connect()
    try:
        raffle = conn.execute("SELECT * FROM raffles WHERE id=?", (rid,)).fetchone()
        if not raffle:
            raise ValueError("raffle not found")
        if raffle["status"] != "open":
            raise ValueError("raffle is closed")

        buyer = None
        if email:
            buyer = conn.execute("SELECT * FROM buyers WHERE email=?",
                                 (email,)).fetchone()
        if buyer:
            bid = buyer["id"]
        else:
            bid = conn.execute(
                "INSERT INTO buyers (name,email,phone,created_at) VALUES (?,?,?,?)",
                (name, email, phone, now())).lastrowid

        receipt_id = "G-" + gen_code(10)   # G prefix = giveaway
        lookup = gen_code(8)
        memo = "COMP-" + gen_code(6)

        oid = conn.execute(
            """INSERT INTO orders (raffle_id,buyer_id,receipt_id,lookup_code,
               quantity,amount_paid,payment_status,payment_method,memo_code,
               paid_at,created_at,entry_source)
               VALUES (?,?,?,?,?,0.0,'paid','comp',?,?,?,'comp')""",
            (rid, bid, receipt_id, lookup, quantity, memo, now(),
             now())).lastrowid

        start = conn.execute("SELECT COUNT(*) c FROM tickets WHERE raffle_id=?",
                             (rid,)).fetchone()["c"]
        nums = []
        for i in range(quantity):
            tn = f"{start + i + 1:06d}"
            conn.execute(
                """INSERT INTO tickets (raffle_id,order_id,buyer_id,
                   ticket_number,status,created_at) VALUES (?,?,?,?,'active',?)""",
                (rid, oid, bid, tn, now()))
            nums.append(tn)

        log_event(conn, oid, "comp_issued",
                  f"qty={quantity} note={note or 'event giveaway'}")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return {"order_id": oid, "buyer_id": bid, "raffle_id": rid,
            "receipt_id": receipt_id, "lookup_code": lookup,
            "quantity": quantity, "amount_paid": 0.0, "memo_code": memo,
            "payment_method": "comp", "ticket_numbers": nums}


def comp_stats(rid):
    """Counts for giveaway tickets vs paid tickets."""
    conn = connect()
    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN o.payment_method='comp' THEN 1 ELSE 0 END),0) comp,
             COALESCE(SUM(CASE WHEN o.payment_method!='comp' THEN 1 ELSE 0 END),0) paid
           FROM tickets t JOIN orders o ON o.id=t.order_id
           WHERE t.raffle_id=? AND t.status='active'""", (rid,)).fetchone()
    conn.close()
    return {"comp": row["comp"], "paid": row["paid"]}


def amoe_entry(rid, name, email, phone="", address="", ip_hash="",
               quantity=1, postmark_date="", received_date="",
               recorded_by=""):
    """Create a FREE entry via the Alternative Method of Entry.

    ============================================================
    THIS IS THE LEGAL FREE PATH. Do not weaken it.
    ============================================================
    The resulting tickets are IDENTICAL to purchased tickets:
      * same tickets table       * same status='active'
      * same pool                * same odds
      * same drawing

    The ONLY differences are amount_paid=0.0 and entry_source='amoe',
    which exist for accounting and audit -- never for odds.

    If you ever find yourself adding a condition that gives an AMOE
    entrant worse treatment than a purchaser, STOP: that reintroduces
    consideration and turns the promotion back into a lottery.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    conn = connect()
    try:
        raffle = conn.execute("SELECT * FROM raffles WHERE id=?", (rid,)).fetchone()
        if not raffle:
            raise ValueError("sweepstakes not found")
        if raffle["status"] != "open":
            raise ValueError("sweepstakes is closed")

        buyer = None
        if email:
            buyer = conn.execute("SELECT * FROM buyers WHERE email=?",
                                 (email,)).fetchone()
        if buyer:
            bid = buyer["id"]
        else:
            bid = conn.execute(
                "INSERT INTO buyers (name,email,phone,created_at) VALUES (?,?,?,?)",
                (name, email, phone, now())).lastrowid

        receipt_id = "E-" + gen_code(10)
        lookup = gen_code(8)
        memo = "AMOE-" + gen_code(6)

        oid = conn.execute(
            """INSERT INTO orders (raffle_id,buyer_id,receipt_id,lookup_code,
               quantity,amount_paid,payment_status,payment_method,memo_code,
               paid_at,created_at,entry_source)
               VALUES (?,?,?,?,?,0.0,'paid','amoe',?,?,?,'amoe')""",
            (rid, bid, receipt_id, lookup, quantity, memo, now(),
             now())).lastrowid

        # Identical allocation to a purchase -- same sequence, same table,
        # same 'active' status. This is what makes the odds equal.
        start = conn.execute("SELECT COUNT(*) c FROM tickets WHERE raffle_id=?",
                             (rid,)).fetchone()["c"]
        nums = []
        for i in range(quantity):
            tn = f"{start + i + 1:06d}"
            conn.execute(
                """INSERT INTO tickets (raffle_id,order_id,buyer_id,
                   ticket_number,status,created_at) VALUES (?,?,?,?,'active',?)""",
                (rid, oid, bid, tn, now()))
            nums.append(tn)

        conn.execute(
            """INSERT INTO amoe_requests
               (raffle_id,name,email,phone,address,ip_hash,granted,
                reason,order_id,created_at,postmark_date,received_date,
                recorded_by)
               VALUES (?,?,?,?,?,?,1,'granted',?,?,?,?,?)""",
            (rid, name, email, phone, address, ip_hash, oid, now(),
             postmark_date, received_date or now()[:10], recorded_by))

        log_event(conn, oid, "amoe_entry", f"qty={quantity} free entry (AMOE)")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return {"order_id": oid, "buyer_id": bid, "raffle_id": rid,
            "receipt_id": receipt_id, "lookup_code": lookup,
            "quantity": quantity, "amount_paid": 0.0, "memo_code": memo,
            "payment_method": "amoe", "entry_source": "amoe",
            "ticket_numbers": nums}


def log_amoe_rejection(rid, name, email, ip_hash, reason):
    """Record a refused free-entry attempt.

    Kept for the audit trail: if the promotion is challenged, this shows
    exactly who was turned away and why. A pattern of rejections for
    anything other than documented abuse would be a red flag.
    """
    conn = connect()
    conn.execute(
        """INSERT INTO amoe_requests
           (raffle_id,name,email,phone,address,ip_hash,granted,reason,created_at)
           VALUES (?,?,?,'','',?,0,?,?)""",
        (rid, name, email, ip_hash, reason,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def amoe_count_for_ip(rid, ip_hash, hours=24):
    """How many free entries has this IP been granted recently?

    Abuse control only. Does not apply to purchases because a purchase
    already carries its own friction (payment).
    """
    if not ip_hash:
        return 0
    conn = connect()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    n = conn.execute(
        """SELECT COUNT(*) c FROM amoe_requests
           WHERE raffle_id=? AND ip_hash=? AND granted=1 AND created_at>?""",
        (rid, ip_hash, cutoff)).fetchone()["c"]
    conn.close()
    return n


def entries_for_email(rid, email):
    """Total ACTIVE entries this person holds, by any method.

    Used for the per-person entry cap. Counts paid, AMOE, and comp
    together -- the cap must apply equally regardless of how the entry
    was obtained, or free entrants would face a restriction buyers don't.
    """
    conn = connect()
    n = conn.execute(
        """SELECT COUNT(t.id) c
           FROM tickets t
           JOIN buyers b ON b.id = t.buyer_id
           WHERE t.raffle_id=? AND LOWER(b.email)=LOWER(?) AND t.status='active'""",
        (rid, email)).fetchone()["c"]
    conn.close()
    return n


def entries_for_household(rid, address="", email=""):
    """Count ACTIVE entries already held by this household.

    Counts EVERY entry source -- donated, mail-in AMOE, and admin comp.
    The household cap must bind identically regardless of how the entry
    was obtained; a cap that only restricted free entrants would make the
    free path inferior and break the sweepstakes structure.
    """
    import sweepstakes as _sw
    key = _sw.household_key(address, email)
    if not key:
        return 0

    # Counts ACTIVE **and** PENDING tickets.
    #
    # Pending must be counted or the cap is trivially bypassed: start an
    # offline (cash/Zelle) order, never pay, and the household slot stays
    # free while more orders are stacked up. Pending entries do NOT affect
    # the odds -- but they DO consume the household's slot until the order
    # is confirmed or cancelled.
    conn = connect()
    rows = conn.execute(
        """SELECT b.address, b.email, COUNT(t.id) n
           FROM tickets t
           JOIN buyers b ON b.id = t.buyer_id
           WHERE t.raffle_id=? AND t.status IN ('active','pending')
           GROUP BY b.id""", (rid,)).fetchall()
    conn.close()

    total = 0
    for r in rows:
        if _sw.household_key(r["address"] or "", r["email"] or "") == key:
            total += r["n"]
    return total


def set_buyer_address(buyer_id, address):
    """Record a buyer's address so household matching can work."""
    if not address:
        return
    conn = connect()
    conn.execute("UPDATE buyers SET address=? WHERE id=?",
                 (address.strip(), buyer_id))
    conn.commit()
    conn.close()


def update_sweepstakes(rid, **fields):
    """Update sweepstakes disclosure fields."""
    allowed = {"sponsor_name", "sponsor_address", "sponsor_email",
               "start_at", "end_at", "prize_arv_total", "eligibility_text",
               "void_where", "entry_limit_per_person",
               "entry_limit_per_household", "amoe_enabled",
               "winner_selection_text", "rules_published", "name"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return False
    vals.append(rid)
    conn = connect()
    conn.execute(f"UPDATE raffles SET {','.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return True


def mailin_log(rid, limit=100):
    """Recent mail-in free entries, newest first.

    This is the compliance record: who mailed in, when it was postmarked,
    when it was received, and what ticket code was generated.
    """
    conn = connect()
    rows = conn.execute(
        """SELECT a.*, o.lookup_code, o.receipt_id, o.quantity
           FROM amoe_requests a
           LEFT JOIN orders o ON o.id = a.order_id
           WHERE a.raffle_id=? AND a.granted=1
           ORDER BY a.id DESC LIMIT ?""", (rid, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def amoe_stats(rid):
    """AMOE activity summary for the admin dashboard."""
    conn = connect()
    row = conn.execute(
        """SELECT
             SUM(CASE WHEN granted=1 THEN 1 ELSE 0 END) granted,
             SUM(CASE WHEN granted=0 THEN 1 ELSE 0 END) rejected,
             COUNT(*) total
           FROM amoe_requests WHERE raffle_id=?""", (rid,)).fetchone()
    conn.close()
    return {"granted": row["granted"] or 0,
            "rejected": row["rejected"] or 0,
            "total": row["total"] or 0}


def get_order_by_lookup(code):
    conn = connect()
    row = conn.execute(
        """SELECT o.*, b.name buyer_name, b.email buyer_email, b.phone buyer_phone,
                  r.name raffle_name, r.num_prizes, r.ticket_price,
                  r.status raffle_status, r.prize_1,r.prize_2,r.prize_3,r.prize_4
           FROM orders o JOIN buyers b ON b.id=o.buyer_id
           JOIN raffles r ON r.id=o.raffle_id WHERE o.lookup_code=?""",
        (code.strip().upper(),)).fetchone()
    if not row:
        conn.close()
        return None
    tix = conn.execute("SELECT ticket_number,status FROM tickets "
                       "WHERE order_id=? ORDER BY id", (row["id"],)).fetchall()
    conn.close()
    d = dict(row)
    d["tickets"] = [t["ticket_number"] for t in tix]
    d["ticket_rows"] = [dict(t) for t in tix]
    return d


def get_order_by_lookup_for_receipt(receipt_id):
    """Look an order up by its receipt_id (used by winner notifications,
    which start from a drum-list row rather than a lookup code)."""
    conn = connect()
    row = conn.execute("SELECT lookup_code FROM orders WHERE receipt_id=?",
                       (receipt_id,)).fetchone()
    conn.close()
    return get_order_by_lookup(row["lookup_code"]) if row else None


def drum_list(rid):
    """Active tickets only -- unpaid tickets never enter the drum.

    Comp (giveaway) tickets ARE included: they are real entries. The
    is_comp flag lets the printed list mark them.
    """
    conn = connect()
    rows = conn.execute(
        """SELECT t.ticket_number,b.name buyer_name,b.phone buyer_phone,
                  b.email buyer_email,o.receipt_id,o.payment_method,
                  CASE WHEN o.payment_method='comp' THEN 1 ELSE 0 END is_comp
           FROM tickets t JOIN buyers b ON b.id=t.buyer_id
           JOIN orders o ON o.id=t.order_id
           WHERE t.raffle_id=? AND t.status='active'
           ORDER BY t.ticket_number""", (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def leaderboard(rid):
    """Active entrants with their entry count and how they entered.

    `methods` is a comma-joined list of the distinct payment methods behind
    a buyer's active tickets -- a person can hold both purchased and
    mail-in (amoe) entries, and the admin needs to see that.

    NOTE: method affects NOTHING about the odds. It is displayed for
    accounting and compliance only. AMOE entries carry identical odds
    to purchased ones by design.
    """
    conn = connect()
    rows = conn.execute(
        """SELECT b.id buyer_id, b.name buyer_name, COUNT(*) tickets,
                  GROUP_CONCAT(DISTINCT o.payment_method) methods,
                  GROUP_CONCAT(DISTINCT o.entry_source) sources
           FROM tickets t
           JOIN buyers b ON b.id = t.buyer_id
           JOIN orders o ON o.id = t.order_id
           WHERE t.raffle_id=? AND t.status='active'
           GROUP BY b.id ORDER BY tickets DESC, b.name""", (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pending_orders(rid):
    """Awaiting manual confirmation -- the admin approval queue."""
    conn = connect()
    rows = conn.execute(
        """SELECT o.*,b.name buyer_name,b.email buyer_email,b.phone buyer_phone
           FROM orders o JOIN buyers b ON b.id=o.buyer_id
           WHERE o.raffle_id=? AND o.payment_status='pending'
           ORDER BY o.created_at""", (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def payment_breakdown(rid):
    conn = connect()
    rows = conn.execute(
        """SELECT payment_method, payment_status, COUNT(*) orders,
                  SUM(quantity) tickets, SUM(amount_paid) amount
           FROM orders WHERE raffle_id=?
           GROUP BY payment_method,payment_status
           ORDER BY payment_method""", (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def order_events(lookup_code):
    conn = connect()
    rows = conn.execute(
        """SELECT e.* FROM payment_events e JOIN orders o ON o.id=e.order_id
           WHERE o.lookup_code=? ORDER BY e.id""",
        (lookup_code.strip().upper(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ draw

def draw_winners(rid):
    conn = connect()
    if conn.execute("SELECT COUNT(*) c FROM draws WHERE raffle_id=?",
                    (rid,)).fetchone()["c"]:
        conn.close()
        raise ValueError("winners already drawn for this raffle")

    raffle = conn.execute("SELECT * FROM raffles WHERE id=?", (rid,)).fetchone()
    pool = [dict(p) for p in conn.execute(
        """SELECT t.id,t.ticket_number,b.name buyer_name
           FROM tickets t JOIN buyers b ON b.id=t.buyer_id
           WHERE t.raffle_id=? AND t.status='active'""", (rid,)).fetchall()]
    if not pool:
        conn.close()
        raise ValueError("no paid tickets in pool")

    p = min(raffle["num_prizes"], len(pool))
    names = [raffle["prize_1"], raffle["prize_2"], raffle["prize_3"], raffle["prize_4"]]
    winners, remaining = [], pool[:]
    for slot in range(p):
        w = remaining.pop(secrets.randbelow(len(remaining)))
        conn.execute("""INSERT INTO draws (raffle_id,prize_slot,prize_name,
                        ticket_id,drawn_at) VALUES (?,?,?,?,?)""",
                     (rid, slot + 1, names[slot], w["id"], now()))
        winners.append({"prize_slot": slot + 1, "prize_name": names[slot],
                        "ticket_number": w["ticket_number"],
                        "buyer_name": w["buyer_name"]})
    conn.execute("UPDATE raffles SET status='drawn' WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return winners


def get_winners(rid):
    conn = connect()
    rows = conn.execute(
        """SELECT d.prize_slot,d.prize_name,t.ticket_number,b.name buyer_name,d.drawn_at
           FROM draws d JOIN tickets t ON t.id=d.ticket_id
           JOIN buyers b ON b.id=t.buyer_id
           WHERE d.raffle_id=? ORDER BY d.prize_slot""", (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
