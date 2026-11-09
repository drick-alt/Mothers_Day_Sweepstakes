"""Buyer identity must follow the submitted entrant name.

Historically the app matched buyers by email only. If AJ Holt entered once with
an email address, a later entrant using that same email would get attached to
AJ's buyer record and receipts/admin would still show AJ Holt. The matching key
must include the entrant name so one shared email can support multiple entrants.
"""

import db

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


def lookup_name(order):
    row = db.get_order_by_lookup(order["lookup_code"])
    assert row is not None
    return row["buyer_name"], row["buyer_phone"], row["buyer_id"]


db.init_db()
RID = db.create_raffle("BuyerIdentityTest", 10.0, 1, ["Prize"])

print("=" * 70)
print("1. Same email but different entrant names creates distinct buyer rows")
print("=" * 70)
email = "shared@example.com"
aj = db.create_order(RID, "AJ Holt", email, "7705550001", 1, "zelle", "RAF-AJ")
new = db.create_order(RID, "Taylor Smith", email, "7705550002", 1, "zelle", "RAF-TS")
aj_name, aj_phone, aj_bid = lookup_name(aj)
new_name, new_phone, new_bid = lookup_name(new)
chk("first order keeps AJ name", aj_name, "AJ Holt")
chk("second order uses submitted entrant name", new_name, "Taylor Smith")
chk("different names do not share buyer row", aj_bid == new_bid, False)
chk("second order has submitted phone", new_phone, "7705550002")

print()
print("=" * 70)
print("2. Same email and same entrant reuses buyer row and refreshes phone")
print("=" * 70)
repeat = db.create_order(RID, "Taylor Smith", email, "7705550099", 1, "zelle", "RAF-RE")
repeat_name, repeat_phone, repeat_bid = lookup_name(repeat)
chk("repeat order keeps same entrant", repeat_name, "Taylor Smith")
chk("repeat order reuses same buyer row", repeat_bid, new_bid)
chk("repeat order refreshes phone", repeat_phone, "7705550099")

print()
print(f"RESULTS: {P} passed, {F} failed")
raise SystemExit(1 if F else 0)
