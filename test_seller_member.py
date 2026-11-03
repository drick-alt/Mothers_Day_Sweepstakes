"""Seller/member tracking for public ticket purchases.

The public purchase form collects the organization member who sold the ticket.
Admin needs a leaderboard showing confirmed and pending ticket sales by member.
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


def find(board, member):
    for row in board:
        if row["seller_member"] == member:
            return row
    raise AssertionError(f"missing seller row {member!r}: {board!r}")


db.init_db()
RID = db.create_raffle("SellerTest", 10.0, 3, ["Bag", "TV", "Visa"])

print("=" * 70)
print("1. Public form exposes seller/member field")
print("=" * 70)
raffle = db.get_raffle(RID)
html = views.page_buy(
    raffle,
    1,
    {"at_least_one": 0.0, "expected_prizes": 0.0, "per_prize": 0.0},
    [{"key": "cash", "label": "Cash", "note": "Manual", "ready": True}],
)
chk("form has seller_member input", 'name="seller_member"' in html, True)
chk("form label mentions member", "Organization member who sold this ticket" in html, True)

print()
print("=" * 70)
print("2. Orders persist seller/member names")
print("=" * 70)
o1 = db.create_order(RID, "Buyer One", "one@example.com", "7705550001", 3,
                     "zelle", "RAF-ONE", seller_member="Alice Member")
o2 = db.create_order(RID, "Buyer Two", "two@example.com", "7705550002", 2,
                     "cash", "RAF-TWO", seller_member="Bob Member")
o3 = db.create_order(RID, "Buyer Three", "three@example.com", "7705550003", 1,
                     "cash", "RAF-THREE", seller_member="Alice Member")
o4 = db.create_order(RID, "Buyer Four", "four@example.com", "7705550004", 4,
                     "cash", "RAF-FOUR", seller_member="")
chk("returned seller member", o1["seller_member"], "Alice Member")
order2 = db.get_order_by_lookup(o2["lookup_code"])
assert order2 is not None
chk("lookup returned order", True, True)
chk("lookup seller member", order2["seller_member"], "Bob Member")

print()
print("=" * 70)
print("3. Leaderboard separates paid from pending and groups blanks")
print("=" * 70)
db.confirm_payment(o1["lookup_code"], "manual", source="test")
db.confirm_payment(o3["lookup_code"], "manual", source="test")
board = db.seller_member_leaderboard(RID)
alice = find(board, "Alice Member")
bob = find(board, "Bob Member")
blank = find(board, "Online / not specified")
chk("Alice paid tickets", alice["paid_tickets"], 4)
chk("Alice pending tickets", alice["pending_tickets"], 0)
chk("Alice paid amount", alice["paid_amount"], 40.0)
chk("Bob paid tickets", bob["paid_tickets"], 0)
chk("Bob pending tickets", bob["pending_tickets"], 2)
chk("Bob pending amount", bob["pending_amount"], 20.0)
chk("blank seller grouped", blank["pending_tickets"], 4)

print()
print("=" * 70)
print("4. Admin dashboard renders seller leaderboard")
print("=" * 70)
admin_html = views.page_admin(
    db.get_raffle(RID),
    db.total_tickets(RID),
    db.pending_tickets(RID),
    db.revenue(RID),
    db.pending_revenue(RID),
    [],
    db.pending_orders(RID),
    db.payment_breakdown(RID),
    [],
    db.comp_stats(RID),
    db.printed_counts(RID),
    db.raffle_page_hit_stats(RID),
    board,
)
for needle in ["Member sales leaderboard", "Alice Member", "Bob Member", "Paid tickets", "Pending $"]:
    chk(f"admin contains {needle}", needle in admin_html, True)

print()
print("=" * 70)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 70)
raise SystemExit(1 if F else 0)
