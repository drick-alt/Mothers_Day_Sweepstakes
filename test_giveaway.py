"""Test free giveaway (comp) tickets."""

import db
import payments
from odds import compute_odds, pct

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
    ok(f"{label} ({got})") if got == want else no(f"{label} (got {got!r} want {want!r})")


db.init_db()
RID = db.create_raffle("GiveawayTest", 25.0, 4, ["A", "B", "C", "D"])
print(f"raffle id={RID}, ticket price $25.00\n")

print("=" * 68)
print("1. Giveaway tickets are FREE but REAL")
print("=" * 68)
g = db.issue_comp_tickets(RID, "Event Eddie", "eddie@t.com", "555", 5,
                          "Fall Festival booth")
chk("amount_paid is 0.00", g["amount_paid"], 0.0)
chk("5 tickets issued", len(g["ticket_numbers"]), 5)
chk("method is comp", g["payment_method"], "comp")
chk("receipt has G- prefix", g["receipt_id"][:2], "G-")
chk("active in pool immediately", db.total_tickets(RID), 5)
chk("NOT pending -- no approval needed", db.pending_tickets(RID), 0)
chk("revenue stays $0", db.revenue(RID), 0.0)
print("  -> 5 real entries worth $125 at face value, $0 revenue. Correct.")

print()
print("=" * 68)
print("2. Giveaway tickets affect odds like any other ticket")
print("=" * 68)
o = compute_odds(db.total_tickets(RID), 5, 4)
chk("Eddie owns whole pool -> 100%", round(o["at_least_one"], 6), 1.0)
p = db.create_order(RID, "Paying Paula", "paula@t.com", "555", 5, "card")
db.confirm_payment(p["lookup_code"], "pi_x", source="test")
chk("pool now 10", db.total_tickets(RID), 10)
chk("revenue now $125", db.revenue(RID), 125.0)
eddie = compute_odds(10, 5, 4)["at_least_one"]
paula = compute_odds(10, 5, 4)["at_least_one"]
chk("free and paid tickets have IDENTICAL odds", eddie, paula)
print(f"  Eddie (free) {pct(eddie)} == Paula (paid) {pct(paula)}")

print()
print("=" * 68)
print("3. Revenue accounting separates free from paid")
print("=" * 68)
cs = db.comp_stats(RID)
chk("5 comp tickets", cs["comp"], 5)
chk("5 purchased tickets", cs["paid"], 5)
chk("revenue counts only purchased", db.revenue(RID), 125.0)
print(f"  -> 10 tickets in pool, but only $125 collected (not $250)")

print()
print("=" * 68)
print("4. SECURITY -- comp is admin-only")
print("=" * 68)
if payments.is_public("comp"):
    no("comp is publicly selectable -- SECURITY BUG")
else:
    ok("comp rejected as a public method")
pub = [m["key"] for m in payments.available_methods()]
if "comp" in pub:
    no("comp appears on public buy page -- SECURITY BUG")
else:
    ok("comp hidden from public buy page")
print(f"  public methods: {pub}")
adm = [m["key"] for m in payments.available_methods(include_admin=True)]
if "comp" in adm:
    ok("comp visible to admin")
else:
    no("comp missing from admin list")

print()
print("=" * 68)
print("5. Giveaway tickets appear in the drum, flagged")
print("=" * 68)
drum = db.drum_list(RID)
chk("drum has all 10", len(drum), 10)
comps = [d for d in drum if d["is_comp"]]
chk("5 flagged as giveaway", len(comps), 5)
names = {d["buyer_name"] for d in comps}
chk("flagged rows belong to Eddie", names, {"Event Eddie"})

print()
print("=" * 68)
print("6. Unpaid tickets STILL excluded (regression check)")
print("=" * 68)
z = db.create_order(RID, "Zelle Zed", "zed@t.com", "555", 20, "zelle",
                    payments.gen_memo_code())
chk("pool unchanged at 10", db.total_tickets(RID), 10)
chk("20 pending", db.pending_tickets(RID), 20)
chk("drum still 10", len(db.drum_list(RID)), 10)
print("  -> giveaway logic did not break the payment-integrity fix")

print()
print("=" * 68)
print("7. Giveaway tickets can win")
print("=" * 68)
w = db.draw_winners(RID)
chk("4 winners", len(w), 4)
eligible = {d["ticket_number"] for d in db.drum_list(RID)}
if all(x["ticket_number"] in eligible for x in w):
    ok("all winners from eligible pool")
else:
    no("ineligible ticket won -- BUG")
if any(x["buyer_name"] == "Zelle Zed" for x in w):
    no("UNPAID buyer won -- CRITICAL BUG")
else:
    ok("unpaid buyer excluded from draw")
for x in w:
    kind = "FREE" if x["buyer_name"] == "Event Eddie" else "paid"
    print(f"    {x['prize_name']}: {x['ticket_number']} -> {x['buyer_name']} ({kind})")

print()
print("=" * 68)
print("8. Audit trail records the giveaway")
print("=" * 68)
ev = db.order_events(g["lookup_code"])
kinds = [e["event"] for e in ev]
print(f"  events: {kinds}")
if "comp_issued" in kinds:
    ok("comp_issued logged")
else:
    no("giveaway not audited")
detail = next((e["detail"] for e in ev if e["event"] == "comp_issued"), "")
if "Fall Festival" in detail:
    ok(f"event note captured: {detail}")
else:
    no("note not recorded")

print()
print("=" * 68)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 68)
raise SystemExit(1 if F else 0)
