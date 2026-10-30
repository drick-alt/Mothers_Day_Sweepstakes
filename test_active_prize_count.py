"""Prize-count regression tests.

The active prize list is the source of truth for odds, analytics and drawings.
A stale num_prizes column must not make the app compute odds for too few or too
many prizes after a prize is added/removed through admin data changes.
"""
import os

SCRATCH = "/tmp/active_prize_count_test.db"
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["RAFFLE_DB_PATH"] = SCRATCH

import db
from odds import compute_odds

P = F = 0

def chk(label, got, want):
    global P, F
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + f"{label}: got={got!r} want={want!r}")
    if ok:
        P += 1
    else:
        F += 1


def close(label, got, want, places=12):
    chk(label, round(got, places), round(want, places))


db.init_db()
conn = db.connect()
# Deliberately stale: num_prizes says 2, but three prize names are populated.
conn.execute("""INSERT INTO raffles (id,name,ticket_price,num_prizes,
    prize_1,prize_2,prize_3,prize_4,status,created_at)
    VALUES (1,'Prize Count Test',10.0,2,'Bag','TV','Visa Gift Card','','open',?)""",
             (db.now(),))
conn.commit(); conn.close()
RID = 1

print("=" * 70)
print("1. get_raffle normalises stale num_prizes from active prize names")
print("=" * 70)
r = db.get_raffle(RID)
assert r is not None
chk("active prize names", db.prize_names(r), ["Bag", "TV", "Visa Gift Card"])
chk("normalised num_prizes", r["num_prizes"], 3)

print("\n" + "=" * 70)
print("2. Receipt/order rows also normalise num_prizes")
print("=" * 70)
o = db.create_order(RID, "Buyer", "buyer@example.com", "7705550101", 5, "zelle")
db.confirm_payment(o["lookup_code"])
order = db.get_order_by_lookup(o["lookup_code"])
assert order is not None
chk("order num_prizes", order["num_prizes"], 3)

print("\n" + "=" * 70)
print("3. Odds analytics use three prizes, not stale two-prize value")
print("=" * 70)
total = db.total_tickets(RID)
mine = db.buyer_ticket_count(RID, order["buyer_id"])
actual = compute_odds(total, mine, order["num_prizes"])
want = compute_odds(total, mine, 3)
wrong = compute_odds(total, mine, 2)
close("expected prizes uses p=3", actual["expected_prizes"], want["expected_prizes"])
close("at least one uses p=3", actual["at_least_one"], want["at_least_one"])
chk("not using stale p=2", actual["expected_prizes"] == wrong["expected_prizes"], False)

print("\n" + "=" * 70)
print("4. Drawing selects three named prizes")
print("=" * 70)
winners = db.draw_winners(RID)
chk("winner count", len(winners), 3)
chk("winner prize names", [w["prize_name"] for w in winners], ["Bag", "TV", "Visa Gift Card"])

print("\nRESULTS:", P, "passed,", F, "failed")
raise SystemExit(1 if F else 0)
