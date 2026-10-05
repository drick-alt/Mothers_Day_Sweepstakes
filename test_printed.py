"""Printed-ticket invariants. Proves the 1,100 stubs cannot touch the live
pool or the odds until an admin moves them."""
import os, shutil, sqlite3, sys

SCRATCH = "/tmp/printed_test.db"
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["RAFFLE_DB_PATH"] = SCRATCH

import db, odds

P, F = 0, 0
def chk(label, got, want):
    global P, F
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + f"{label}: got={got} want={want}")
    if ok: P += 1
    else:  F += 1

db.init_db()
conn = db.connect()
conn.execute("""INSERT INTO raffles (id,name,ticket_price,num_prizes,
    prize_1,prize_2,status,created_at) VALUES
    (1,'Printed Test',10.0,2,'A','B','open',?)""", (db.now(),))
conn.commit(); conn.close()
RID = 1

print("=" * 66)
print("1. Baseline: a few ONLINE tickets sold and paid")
print("=" * 66)
o = db.create_order(RID, "Online Buyer", "on@e.com", "7705550001", 3, "zelle")
db.confirm_payment(o["lookup_code"])
chk("online active tickets", db.total_tickets(RID), 3)
print("     online numbers:", o["ticket_numbers"])

print()
print("=" * 66)
print("2. Seed 1,100 PRINTED tickets -> must change NOTHING live")
print("=" * 66)
before_total = db.total_tickets(RID)
before_odds = odds.compute_odds(before_total, 1, 2)["at_least_one"]
made = db.seed_printed_tickets(RID, 1100)
chk("stock rows created", len(made), 1100)
chk("total_tickets UNCHANGED", db.total_tickets(RID), before_total)
chk("odds UNCHANGED",
    round(odds.compute_odds(db.total_tickets(RID), 1, 2)["at_least_one"], 12),
    round(before_odds, 12))
chk("drum excludes stock", len(db.drum_list(RID)), 3)
c = db.printed_counts(RID)
chk("printed available", c["available"], 1100)
chk("printed active", c["active"], 0)
print(f"     first 3 stubs: {[m['ticket_number'] for m in made[:3]]}")
print(f"     last  3 stubs: {[m['ticket_number'] for m in made[-3:]]}")
print(f"     check codes  : {[m['check_code'] for m in made[:3]]}")

print()
print("=" * 66)
print("3. Numbering shares ONE sequence with online sales")
print("=" * 66)
nums = [m["ticket_number"] for m in made]
chk("stock continues from online", nums[0], "000004")
chk("sequential, no gaps", nums[-1], f"{3 + 1100:06d}")
chk("all unique", len(set(nums)), 1100)
o2 = db.create_order(RID, "Later Buyer", "later@e.com", "7705550002", 2, "zelle")
db.confirm_payment(o2["lookup_code"])
chk("online resumes AFTER stock (no collision)",
    o2["ticket_numbers"], ["001104", "001105"])
conn = db.connect()
dupes = conn.execute(
    "SELECT COUNT(*) c FROM (SELECT ticket_number FROM tickets "
    "WHERE raffle_id=? GROUP BY ticket_number HAVING COUNT(*)>1)",
    (RID,)).fetchone()["c"]
conn.close()
chk("zero duplicate numbers overall", dupes, 0)

print()
print("=" * 66)
print("4. Admin moves 5 sold stubs into the LIVE pool")
print("=" * 66)
sell = nums[:5]
live_before = db.total_tickets(RID)
moved = db.activate_printed_tickets(RID, sell, holder_name="Church Table Sale")
chk("tickets moved", len(moved), 5)
chk("live pool grew by exactly 5", db.total_tickets(RID), live_before + 5)
chk("printed available now", db.printed_counts(RID)["available"], 1095)
chk("printed active now", db.printed_counts(RID)["active"], 5)
drum = {d["ticket_number"] for d in db.drum_list(RID)}
chk("moved stubs ARE in the drum", all(s in drum for s in sell), True)
chk("unsold stubs are NOT in the drum",
    any(n in drum for n in nums[5:]), False)

print()
print("=" * 66)
print("5. Safety rails")
print("=" * 66)
again = None
try:
    db.activate_printed_tickets(RID, sell)
except ValueError as e:
    again = str(e)
chk("re-activating same stubs refused", again is not None, True)
chk("pool did NOT double-count", db.total_tickets(RID), live_before + 5)

mixed = db.activate_printed_tickets(RID, [nums[5], nums[6], "000001", "999999"])
chk("mixed batch moves only eligible stubs", sorted(mixed),
    sorted([nums[5], nums[6]]))
chk("online ticket 000001 not hijacked",
    db.printed_counts(RID)["active"], 7)

n_back = db.return_printed_to_available(RID, [nums[5]])
chk("return-to-available works", n_back, 1)
chk("available restored", db.printed_counts(RID)["available"], 1094)

print()
print("=" * 66)
print("6. Draw only ever sees the live pool")
print("=" * 66)
live = db.total_tickets(RID)
pool_rows = db.drum_list(RID)
chk("drum size == total_tickets", len(pool_rows), live)
winners = db.draw_winners(RID)
chk("winners drawn", len(winners), 2)
won = {w["ticket_number"] for w in winners}
unsold = set(nums[7:])
chk("no unsold stub won", bool(won & unsold), False)
chk("every winner was in the live drum", won <= {d["ticket_number"] for d in pool_rows}, True)
for w in winners:
    print(f"     prize {w['prize_slot']}: {w['ticket_number']}  {w['buyer_name']}")

blocked = None
try:
    db.seed_printed_tickets(RID, 10)
except ValueError as e:
    blocked = str(e)
chk("no new stock after the draw", blocked is not None, True)

print()
print("=" * 66)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 66)
raise SystemExit(1 if F else 0)
