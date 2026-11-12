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
print("4. Blank seller/member rows can be reassigned to a member")
print("=" * 70)
onpoint = db.create_order(RID, "Buyer Five", "five@example.com", "7705550005", 1,
                          "cash", "RAF-FIVE", seller_member="On Point")
db.confirm_payment(onpoint["lookup_code"], "manual", source="test")
res = db.assign_blank_seller_member(RID, "On Point")
chk("blank reassignment order count", res["orders"], 1)
chk("blank reassignment pending tickets", res["pending_tickets"], 4)
board = db.seller_member_leaderboard(RID)
onpoint_row = find(board, "On Point")
chk("On Point paid tickets after reassignment", onpoint_row["paid_tickets"], 1)
chk("On Point pending tickets after reassignment", onpoint_row["pending_tickets"], 4)
printed = db.seed_printed_tickets(RID, 4)
printed_nums = [r["ticket_number"] for r in printed]
db.activate_printed_tickets(RID, printed_nums, holder_name="Printed Buyer",
                            holder_email="printed@example.com",
                            holder_phone="7705550006",
                            seller_member="On Point")
db.return_printed_to_available(RID, printed_nums[:2])
board = db.seller_member_leaderboard(RID)
onpoint_row = find(board, "On Point")
chk("On Point paid tickets exclude returned printed", onpoint_row["paid_tickets"], 3)
chk("On Point online paid tickets", onpoint_row["paid_online_tickets"], 1)
chk("On Point printed paid tickets", onpoint_row["paid_printed_tickets"], 2)
chk("On Point paid amount excludes returned printed", onpoint_row["paid_amount"], 30.0)
chk("On Point pending unchanged after printed return", onpoint_row["pending_tickets"], 4)
if any(r["seller_member"] == "Online / not specified" for r in board):
    no("blank seller row remained after reassignment")
else:
    ok("blank seller row removed after reassignment")

print()
print("=" * 70)
print("5. Misspelled/alternate member names can be merged into the correct member")
print("=" * 70)
wade = db.create_order(RID, "Buyer Wade", "wade@example.com", "7705550100", 3,
                       "cash", "RAF-WADE", seller_member="Wade")
db.confirm_payment(wade["lookup_code"], "manual", source="test")
wade_larry = db.create_order(RID, "Buyer Wade Larry", "wadel@example.com", "7705550101", 2,
                             "cash", "RAF-WL", seller_member="Wade Larry")
db.confirm_payment(wade_larry["lookup_code"], "manual", source="test")
hubert = db.create_order(RID, "Hubert Buyer", "hubert@example.com", "7705550102", 4,
                         "cash", "RAF-HUB", seller_member="Hubert Steam Cleaning, Inc.")
db.confirm_payment(hubert["lookup_code"], "manual", source="test")
res_wade = db.reassign_seller_member(RID, "Wade", "Kosher")
res_wade_larry = db.reassign_seller_member(RID, "Wade Larry", "Kosher")
res_hubert = db.reassign_seller_member(RID, "Hubert Steam Cleaning, Inc.", "On Point")
chk("Wade reassignment moved tickets", res_wade["paid_tickets"], 3)
chk("Wade Larry reassignment moved tickets", res_wade_larry["paid_tickets"], 2)
chk("Hubert reassignment moved tickets", res_hubert["paid_tickets"], 4)
board = db.seller_member_leaderboard(RID)
kosher_row = find(board, "Kosher")
onpoint_row = find(board, "On Point")
chk("Kosher merged paid tickets", kosher_row["paid_tickets"], 5)
chk("Kosher online paid tickets", kosher_row["paid_online_tickets"], 5)
chk("Kosher printed paid tickets", kosher_row["paid_printed_tickets"], 0)
chk("On Point includes Hubert tickets", onpoint_row["paid_tickets"], 7)
chk("On Point merged online paid tickets", onpoint_row["paid_online_tickets"], 5)
chk("On Point merged printed paid tickets", onpoint_row["paid_printed_tickets"], 2)
if any(r["seller_member"] in ["Wade", "Wade Larry", "Hubert Steam Cleaning, Inc."] for r in board):
    no("old member alias rows remained after reassignment")
else:
    ok("old member alias rows removed after reassignment")

print()
print("=" * 70)
print("6. Admin dashboard renders seller leaderboard")
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
for needle in ["Member sales leaderboard", "Alice Member", "Bob Member", "Paid tickets", "Pending $",
               "Online paid", "Printed paid", "non-printed website/manual purchase tickets",
               "Sales Leader", "Second Place", "color:#22c55e", "color:#facc15",
               "Credit / Edit", "Credit to member", "seller-member/reassign",
               "rankings recalculate after submit"]:
    chk(f"admin contains {needle}", needle in admin_html, True)
chk("leader has trophy", "🏆" in admin_html, True)
chk("second place has medal", "🥈" in admin_html, True)
chk("member leaderboard moved above details", admin_html.find("Member sales leaderboard") < admin_html.find("Printed Tickets"), True)
chk("create raffle moved near bottom after draw", admin_html.find("Draw</h2>") < admin_html.find("Create another raffle"), True)

print()
print("=" * 70)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 70)
raise SystemExit(1 if F else 0)
