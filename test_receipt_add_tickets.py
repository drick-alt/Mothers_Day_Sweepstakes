"""Receipt page layout and add-on ticket purchase tests."""

import os
import tempfile

fd, path = tempfile.mkstemp(prefix="raffle_receipt_add_", suffix=".db")
os.close(fd)
os.environ["RAFFLE_DB_PATH"] = path

import db  # noqa: E402
import views  # noqa: E402
from odds import compute_odds  # noqa: E402

FAILS = []


def chk(label, got, want=None):
    if want is None:
        want = True
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got={got!r}")
    if not ok:
        FAILS.append(label)


def contains_in_order(haystack, first, second):
    a = haystack.find(first)
    b = haystack.find(second)
    return a >= 0 and b >= 0 and a < b


db.init_db()
RID = db.create_raffle("ReceiptAdd", 10.0, 3, ["Bag", "TV", "Visa"])

print("=" * 70)
print("1. Receipt layout shows entrant info before saved code and add form")
print("=" * 70)
root = db.create_order(RID, "Repeat Buyer", "repeat@example.com", "7705550101", 2,
                       "cash", "RAF-ROOT", seller_member="On Point")
db.confirm_payment(root["lookup_code"], "manual", source="test")
receipt = db.get_receipt_bundle(root["lookup_code"])
assert receipt is not None
html = views.page_receipt(
    receipt,
    compute_odds(db.total_tickets(RID), db.buyer_ticket_count(RID, receipt["buyer_id"]), receipt["num_prizes"]),
    0.0,
    [],
    None,
    [{"key": "cash", "label": "Cash / Check", "note": "Manual", "ready": True}],
)
chk("receipt has entrant tile", "Entrant" in html)
chk("receipt has save-code tile", "Save this code to get back to your tickets" in html)
chk("entrant tile appears before save-code tile", contains_in_order(html, "Entrant", "Save this code to get back to your tickets"))
chk("receipt add form present", f'action="/receipt/{root["lookup_code"]}/add-tickets"' in html)
chk("purchase more copy present", "Purchase more tickets with this code" in html)

print()
print("=" * 70)
print("2. Add-on order stays connected to original lookup code")
print("=" * 70)
addon = db.create_addon_order(root["lookup_code"], 3, "zelle", "RAF-ADDON")
chk("addon points at root code", addon["parent_lookup_code"], root["lookup_code"])
bundle = db.get_receipt_bundle(root["lookup_code"])
assert bundle is not None
chk("bundle keeps public lookup code", bundle["lookup_code"], root["lookup_code"])
chk("bundle aggregates quantity", bundle["quantity"], 5)
chk("bundle aggregates amount", bundle["amount_paid"], 50.0)
chk("bundle includes both order codes", len(bundle["order_lookup_codes"]), 2)
chk("bundle shows paid+pending as pending", bundle["payment_status"], "pending")
chk("pending add-on does not enter live pool", db.total_tickets(RID), 2)
chk("pending add-on ticket rows included on receipt", len(bundle["ticket_rows"]), 5)
html2 = views.page_receipt(
    bundle,
    compute_odds(db.total_tickets(RID), db.buyer_ticket_count(RID, bundle["buyer_id"]), bundle["num_prizes"]),
    0.0,
    [],
    None,
    [{"key": "cash", "label": "Cash / Check", "note": "Manual", "ready": True}],
)
chk("receipt still displays original code after add-on", f'<div class="code">{root["lookup_code"]}</div>' in html2)
chk("dashed pending note shown", "Dashed = pending payment" in html2)

print()
print("=" * 70)
print("3. Add-on tickets activate after add-on payment confirms")
print("=" * 70)
db.confirm_payment(addon["lookup_code"], "manual", source="test")
bundle = db.get_receipt_bundle(addon["lookup_code"])
assert bundle is not None
chk("child receipt canonicalizes to root code", bundle["lookup_code"], root["lookup_code"])
chk("bundle becomes paid when all orders paid", bundle["payment_status"], "paid")
chk("all five tickets now live", db.total_tickets(RID), 5)
chk("buyer owns five active tickets", db.buyer_ticket_count(RID, bundle["buyer_id"]), 5)

print()
print("=" * 70)
if FAILS:
    print(f"RESULTS: {len(FAILS)} failed -> {FAILS}")
    raise SystemExit(1)
print("RESULTS: all receipt add-ticket tests passed")
print("=" * 70)
