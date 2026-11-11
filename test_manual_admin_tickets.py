"""Admin manual live-ticket entry.

Admin-created tickets should enter the live pool immediately, count as paid
revenue, support seller/member leaderboard attribution, and expose an admin form
without creating live rows during verification.
"""

import db
import views

P = F = 0


def ok(m):
    global P
    P += 1
    print(f"  PASS  {m}")


def no(m):
    global F
    F += 1
    print(f"  FAIL  {m}")


def chk(label, got, want):
    if got == want:
        ok(f"{label}: got={got!r}")
    else:
        no(f"{label}: got={got!r} want={want!r}")


def find(rows, key, value):
    for r in rows:
        if r.get(key) == value:
            return r
    return None


db.init_db()
RID = db.create_raffle("ManualAdminTicketTest", 10.0, 3, ["Bag", "TV", "Visa"])

print("=" * 72)
print("1. Admin-created tickets enter the live pool immediately")
print("=" * 72)
order = db.create_admin_live_tickets(
    RID,
    "Manual Maria",
    "maria@example.com",
    "7705550101",
    3,
    payment_method="cashapp",
    seller_member="On Point",
    note="admin desk sale",
)
assert order is not None
chk("manual order is paid", order["payment_status"], "paid")
chk("manual order method", order["payment_method"], "cashapp")
chk("manual seller member", order["seller_member"], "On Point")
chk("manual active ticket count", len([t for t in order["ticket_rows"] if t["status"] == "active"]), 3)
chk("live pool count", db.total_tickets(RID), 3)
chk("revenue", db.revenue(RID), 30.0)

print()
print("=" * 72)
print("2. Manual tickets appear in payment and seller reports")
print("=" * 72)
pay = find(db.payment_breakdown(RID), "payment_method", "cashapp")
assert pay is not None
chk("cashapp paid tickets", pay["paid_tickets"], 3)
chk("cashapp paid amount", pay["paid_amount"], 30.0)
seller = find(db.seller_member_leaderboard(RID), "seller_member", "On Point")
assert seller is not None
chk("seller paid tickets", seller["paid_tickets"], 3)
chk("seller paid amount", seller["paid_amount"], 30.0)

drum = db.drum_list(RID)
chk("drum has manual tickets", len(drum), 3)
chk("drum method cashapp", {r["payment_method"] for r in drum}, {"cashapp"})

print()
print("=" * 72)
print("3. Admin dashboard renders manual live-ticket form")
print("=" * 72)
raffle = db.get_raffle(RID)
board = db.leaderboard(RID)
for b in board:
    b["odds"] = 1.0
    b["expected"] = 1.0
html = views.page_admin(
    raffle,
    db.total_tickets(RID),
    db.pending_tickets(RID),
    db.revenue(RID),
    db.pending_revenue(RID),
    board,
    db.pending_orders(RID),
    db.payment_breakdown(RID),
    [],
    db.comp_stats(RID),
    db.printed_counts(RID),
    db.raffle_page_hit_stats(RID),
    db.seller_member_leaderboard(RID),
)
for needle in [
    "Manual live ticket entry",
    f'action="/admin/{RID}/manual-ticket"',
    'name="seller_member"',
    'name="payment_method"',
    "Create live paid ticket(s)",
    "enter the live drawing pool immediately",
]:
    chk(f"admin form contains {needle}", needle in html, True)

print()
print("=" * 72)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 72)
raise SystemExit(1 if F else 0)
