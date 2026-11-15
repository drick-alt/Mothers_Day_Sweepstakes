"""Buyer-facing Cash App/Zelle payment instruction clarity tests."""

import os
import tempfile

fd, path = tempfile.mkstemp(prefix="raffle_offline_pay_", suffix=".db")
os.close(fd)
os.environ["RAFFLE_DB_PATH"] = path

import db  # noqa: E402
import payments  # noqa: E402
import views  # noqa: E402

FAILS = []


def chk(label, got, want=True):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got={got!r}")
    if not ok:
        FAILS.append(label)


db.init_db()
RID = db.create_raffle("OfflinePay", 10.0, 3, ["Bag", "TV", "Visa"])

print("=" * 70)
print("1. Cash App payment page clearly tells buyer to copy/paste RAF memo")
print("=" * 70)
cashapp = db.create_order(RID, "Cash Buyer", "cash@example.com", "7705550001", 2,
                          "cashapp", "RAF-CASH1")
order = db.get_order_by_lookup(cashapp["lookup_code"])
assert order is not None
inst = payments.offline_instructions("cashapp", order)
html = views.page_offline_pay(order, inst)
for needle in [
    "Step 1: Copy this RAF memo code",
    "RAF-CASH1",
    "Open Cash App",
    "paste this RAF code into the memo / notes field before you send",
    "Paste RAF-CASH1 into the Cash App note / memo section",
    "This is how we match your payment to your tickets",
]:
    chk(f"Cash App page contains {needle}", needle in html)

print()
print("=" * 70)
print("2. Zelle payment page clearly tells buyer to copy/paste RAF memo")
print("=" * 70)
zelle = db.create_order(RID, "Zelle Buyer", "zelle@example.com", "7705550002", 3,
                        "zelle", "RAF-ZELLE1")
order = db.get_order_by_lookup(zelle["lookup_code"])
assert order is not None
inst = payments.offline_instructions("zelle", order)
html = views.page_offline_pay(order, inst)
for needle in [
    "Step 1: Copy this RAF memo code",
    "RAF-ZELLE1",
    "Open Zelle",
    "paste this RAF code into the memo / notes field before you send",
    "Paste RAF-ZELLE1 into the Zelle memo / notes section",
    "This is how we match your payment to your tickets",
]:
    chk(f"Zelle page contains {needle}", needle in html)

print()
print("=" * 70)
if FAILS:
    print(f"RESULTS: {len(FAILS)} failed -> {FAILS}")
    raise SystemExit(1)
print("RESULTS: offline payment instruction tests passed")
print("=" * 70)
