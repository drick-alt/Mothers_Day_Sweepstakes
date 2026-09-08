"""Test the payment state machine directly against the DB layer.

Focus: the invariant that pending tickets must never affect the odds.
"""

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
    if got == want:
        ok(f"{label} ({got})")
    else:
        no(f"{label} (got {got!r} want {want!r})")


db.init_db()
RID = db.create_raffle("PaymentTest", 10.0, 4,
                       ["A", "B", "C", "D"])
print(f"test raffle id={RID}\n")

print("=" * 68)
print("1. Baseline")
print("=" * 68)
chk("starts with 0 active", db.total_tickets(RID), 0)
chk("starts with 0 pending", db.pending_tickets(RID), 0)
chk("starts with $0 revenue", db.revenue(RID), 0)

print()
print("=" * 68)
print("2. CRITICAL -- pending tickets must NOT count in the pool")
print("=" * 68)
o1 = db.create_order(RID, "Zelle Zoe", "zoe@t.com", "555", 10,
                     "zelle", payments.gen_memo_code())
chk("10 tickets reserved as pending", db.pending_tickets(RID), 10)
chk("active pool still 0", db.total_tickets(RID), 0)
chk("confirmed revenue still 0", db.revenue(RID), 0)
chk("pending revenue is 100", db.pending_revenue(RID), 100.0)
odds_before = compute_odds(db.total_tickets(RID), 0, 4)["at_least_one"]
chk("odds unaffected by unpaid order", odds_before, 0.0)
print("  -> an unpaid order CANNOT dilute paying buyers. This is the key fix.")

print()
print("=" * 68)
print("3. Paid order activates immediately")
print("=" * 68)
o2 = db.create_order(RID, "Card Carl", "carl@t.com", "555", 5, "card")
db.confirm_payment(o2["lookup_code"], "pi_test_123", source="stripe_webhook")
chk("5 tickets now active", db.total_tickets(RID), 5)
chk("Zoe's 10 still pending", db.pending_tickets(RID), 10)
chk("revenue counts only Carl", db.revenue(RID), 50.0)
carl_odds = compute_odds(db.total_tickets(RID), 5, 4)["at_least_one"]
chk("Carl owns whole active pool -> 100%", round(carl_odds, 6), 1.0)

print()
print("=" * 68)
print("4. Confirming Zelle order dilutes correctly")
print("=" * 68)
before = compute_odds(db.total_tickets(RID), 5, 4)["at_least_one"]
db.confirm_payment(o1["lookup_code"], "zelle-manual", source="admin")
after = compute_odds(db.total_tickets(RID), 5, 4)["at_least_one"]
chk("pool now 15", db.total_tickets(RID), 15)
chk("pending drained to 0", db.pending_tickets(RID), 0)
chk("revenue now 150", db.revenue(RID), 150.0)
print(f"  Carl's odds: {pct(before)} -> {pct(after)}")
if after < before:
    ok("Carl's odds correctly dropped after Zoe paid")
else:
    no("odds did not dilute")

print()
print("=" * 68)
print("5. IDEMPOTENCY -- duplicate webhook must not double-activate")
print("=" * 68)
pool_before = db.total_tickets(RID)
r1 = db.confirm_payment(o2["lookup_code"], "pi_test_123", source="stripe_webhook")
r2 = db.confirm_payment(o2["lookup_code"], "pi_test_123", source="stripe_webhook")
chk("replay returns False", r1, False)
chk("second replay returns False", r2, False)
chk("pool unchanged after 2 replays", db.total_tickets(RID), pool_before)
chk("revenue unchanged", db.revenue(RID), 150.0)
print("  -> Stripe retries webhooks. Without this, a retry would duplicate revenue.")

print()
print("=" * 68)
print("6. Cancel unpaid -> tickets voided")
print("=" * 68)
o3 = db.create_order(RID, "Ghost Gary", "gary@t.com", "555", 7, "zelle",
                     payments.gen_memo_code())
chk("7 pending", db.pending_tickets(RID), 7)
db.cancel_order(o3["lookup_code"], "never paid")
chk("pending back to 0", db.pending_tickets(RID), 0)
chk("active pool untouched", db.total_tickets(RID), 15)

print()
print("=" * 68)
print("7. Cannot cancel a PAID order")
print("=" * 68)
try:
    db.cancel_order(o2["lookup_code"])
    no("paid order was cancellable -- BUG")
except ValueError as e:
    ok(f"paid order refused cancellation ({e})")

print()
print("=" * 68)
print("8. Ticket numbers never reused after cancellation")
print("=" * 68)
o4 = db.create_order(RID, "Next Nina", "nina@t.com", "555", 2, "card")
nums = o4["ticket_numbers"]
print(f"  Gary had 000016-000022 (cancelled), Nina got {nums[0]}-{nums[-1]}")
if int(nums[0]) > 22:
    ok("numbering continued past cancelled block -- no reuse")
else:
    no(f"ticket number collision risk: {nums[0]}")

print()
print("=" * 68)
print("9. Drum list contains ONLY paid tickets")
print("=" * 68)
db.create_order(RID, "Pending Pete", "pete@t.com", "555", 20, "zelle",
                payments.gen_memo_code())
drum = db.drum_list(RID)
chk("drum has 15 (not 35)", len(drum), 15)
names = {d["buyer_name"] for d in drum}
if "Pending Pete" not in names:
    ok("unpaid buyer excluded from drum")
else:
    no("unpaid buyer leaked into drum -- BUG")

print()
print("=" * 68)
print("10. Draw uses only paid tickets")
print("=" * 68)
w = db.draw_winners(RID)
chk("4 winners drawn", len(w), 4)
paid_nums = {d["ticket_number"] for d in drum}
if all(x["ticket_number"] in paid_nums for x in w):
    ok("every winner is a PAID ticket")
else:
    no("an unpaid ticket won -- CRITICAL BUG")
for x in w:
    print(f"    {x['prize_name']}: {x['ticket_number']} -> {x['buyer_name']}")

print()
print("=" * 68)
print("11. Audit trail")
print("=" * 68)
ev = db.order_events(o2["lookup_code"])
kinds = [e["event"] for e in ev]
print(f"  events for Carl's order: {kinds}")
if "order_created" in kinds and "payment_confirmed" in kinds:
    ok("lifecycle logged")
else:
    no("audit trail incomplete")
if kinds.count("confirm_duplicate") == 2:
    ok("both webhook replays logged as duplicates")
else:
    no(f"expected 2 duplicate events, got {kinds.count('confirm_duplicate')}")

print()
print("=" * 68)
print("12. Stripe webhook signature verification")
print("=" * 68)
import json
payments.STRIPE_WEBHOOK_SECRET = "whsec_test_secret"
body = json.dumps({"type": "checkout.session.completed",
                   "data": {"object": {"client_reference_id": "ABC12345"}}}).encode()
good = payments.sign_stripe_payload(body, "whsec_test_secret")
try:
    ev = payments.verify_stripe_webhook(body, good)
    ok("valid signature accepted")
except Exception as e:
    no(f"valid signature rejected: {e}")

try:
    payments.verify_stripe_webhook(body, "t=1700000000,v1=deadbeef")
    no("FORGED signature accepted -- CRITICAL SECURITY BUG")
except ValueError:
    ok("forged signature rejected")

try:
    payments.verify_stripe_webhook(b'{"tampered":true}', good)
    no("tampered payload accepted -- CRITICAL SECURITY BUG")
except ValueError:
    ok("tampered payload rejected")

try:
    payments.verify_stripe_webhook(body, "")
    no("missing signature accepted")
except ValueError:
    ok("missing signature header rejected")

print()
print("=" * 68)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 68)
raise SystemExit(1 if F else 0)
