"""Sweepstakes compliance tests.

The critical test in this file is EQUAL DIGNITY: an AMOE (free) entrant
must have exactly the same odds as a purchaser holding the same number
of entries. If that test ever fails, the promotion is legally a lottery,
not a sweepstakes.
"""

from datetime import datetime, timedelta, timezone

import db
import sweepstakes as sw
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


def chk(m, cond):
    ok(m) if cond else no(m)


def eq(m, got, want):
    ok(f"{m} ({got})") if got == want else no(f"{m}: got {got!r} want {want!r}")


print("=" * 64)
print("SWEEPSTAKES COMPLIANCE TESTS")
print("=" * 64)

# ---------------------------------------------------------------- setup
rid = db.create_raffle("Compliance Test Sweepstakes", 25.0, 4,
                       ["Prize A", "Prize B", "Prize C", "Prize D"])
now = datetime.now(timezone.utc)
db.update_sweepstakes(
    rid,
    sponsor_name="Test Sponsor LLC",
    sponsor_address="123 Main St, Lawrenceville, GA 30045",
    sponsor_email="sponsor@example.com",
    start_at=(now - timedelta(days=1)).isoformat(),
    end_at=(now + timedelta(days=30)).isoformat(),
    prize_arv_total=4500.00,
    eligibility_text=sw.DEFAULT_ELIGIBILITY,
    winner_selection_text=sw.DEFAULT_WINNER_SELECTION,
)

print("\n1. EQUAL DIGNITY -- the core legal requirement")
print("-" * 64)

# Two entrants, same number of entries, different methods.
paid = db.create_order(rid, "Paid Patty", "patty@test.com", "555-0001",
                       5, "card")
db.confirm_payment(paid["lookup_code"], "test_ref", "test")
free = db.amoe_entry(rid, "Free Fred", "fred@test.com", ip_hash="hash_fred",
                     quantity=5)

total = db.total_tickets(rid)
p_ct = db.buyer_ticket_count(rid, paid["buyer_id"])
f_ct = db.buyer_ticket_count(rid, free["buyer_id"])

eq("paid entrant holds 5 entries", p_ct, 5)
eq("free entrant holds 5 entries", f_ct, 5)

p_odds = compute_odds(total, p_ct, 4)
f_odds = compute_odds(total, f_ct, 4)

print(f"      pool={total}  paid={pct(p_odds['at_least_one'])}  "
      f"free={pct(f_odds['at_least_one'])}")
chk("*** ODDS ARE IDENTICAL (equal dignity) ***",
    p_odds["at_least_one"] == f_odds["at_least_one"])
chk("expected prizes identical",
    p_odds["expected_prizes"] == f_odds["expected_prizes"])

# The free entry must be a REAL active ticket in the SAME pool.
drum = db.drum_list(rid)
free_in_drum = [t for t in drum if t["buyer_name"] == "Free Fred"]
eq("free entries appear in the drawing pool", len(free_in_drum), 5)

paid_in_drum = [t for t in drum if t["buyer_name"] == "Paid Patty"]
eq("paid entries appear in the drawing pool", len(paid_in_drum), 5)

# Revenue must NOT include the free entry.
rev = db.revenue(rid)
eq("free entry contributes $0 revenue", rev, 125.0)

print("\n2. AMOE validation (must not be burdensome)")
print("-" * 64)

# REQUIRED on both paths: name, email, phone. Address is OPTIONAL on both,
# so the free path is never more burdensome than the donated one.
good, _ = sw.validate_amoe("Jane Doe", "jane@example.com",
                           "99 Real St, Atlanta GA 30341", "7705551234")
chk("valid name+email+address+phone accepted", good)

bad, msg = sw.validate_amoe("", "jane@example.com")
chk("empty name rejected", not bad)

bad, msg = sw.validate_amoe("Jane Doe", "not-an-email")
chk("malformed email rejected", not bad)

bad, msg = sw.validate_amoe("J", "jane@example.com")
chk("single-char name rejected", not bad)

good, _ = sw.validate_amoe("Jane Doe", "jane@example.com", "", "7705551234")
chk("address NOT required for mail-in (paths stay symmetric)", good)

bad, msg = sw.validate_amoe("Jane Doe", "jane@example.com",
                            "99 Real St, Atlanta GA 30341", "")
chk("phone IS required for mail-in", not bad)

good, _ = sw.validate_amoe("Jane Doe", "jane@example.com", "", "7705551234",
                           require_address=False)
chk("address NOT required on the donated path either", good)

print("\n3. Entry period enforcement")
print("-" * 64)

s = db.get_raffle(rid)
allowed, msg = sw.entry_allowed(s)
chk("entry allowed inside period", allowed)

status, _ = sw.period_status(s)
eq("period status is open", status, "open")

# Ended sweepstakes
db.update_sweepstakes(rid, end_at=(now - timedelta(days=1)).isoformat())
s2 = db.get_raffle(rid)
status2, _ = sw.period_status(s2)
eq("expired period detected", status2, "ended")
allowed2, _ = sw.entry_allowed(s2)
chk("entry blocked after end date", not allowed2)

# Not yet started
db.update_sweepstakes(rid,
                      start_at=(now + timedelta(days=5)).isoformat(),
                      end_at=(now + timedelta(days=30)).isoformat())
s3 = db.get_raffle(rid)
status3, _ = sw.period_status(s3)
eq("future period detected", status3, "not_started")
allowed3, _ = sw.entry_allowed(s3)
chk("entry blocked before start date", not allowed3)

# Missing end date is a compliance defect, not "open forever"
db.update_sweepstakes(rid, start_at=None, end_at=None)
s4 = db.get_raffle(rid)
status4, _ = sw.period_status(s4)
eq("missing end date flagged as undefined", status4, "undefined")

# restore a valid window
db.update_sweepstakes(rid,
                      start_at=(now - timedelta(days=1)).isoformat(),
                      end_at=(now + timedelta(days=30)).isoformat())

print("\n4. Official Rules completeness")
print("-" * 64)

s5 = db.get_raffle(rid)
complete, missing = sw.rules_completeness(s5)
chk("fully-populated sweepstakes passes completeness", complete)
if not complete:
    print(f"        missing: {missing}")

rid2 = db.create_raffle("Incomplete Sweeps", 10.0, 1, ["Thing"])
s6 = db.get_raffle(rid2)
complete2, missing2 = sw.rules_completeness(s6)
chk("bare sweepstakes fails completeness", not complete2)
chk("sponsor name flagged missing", "Sponsor name" in missing2)
chk("end date flagged missing", "Entry period end date" in missing2)
chk("ARV flagged missing",
    any("ARV" in m for m in missing2))

print("\n5. Official Rules content")
print("-" * 64)

rules = sw.build_rules(s5, ["Prize A", "Prize B", "Prize C", "Prize D"],
                       total_entries=total)

chk("NO PURCHASE NECESSARY present",
    "NO PURCHASE OR PAYMENT OF ANY KIND IS NECESSARY" in rules)
chk("states purchase does not improve odds",
    "WILL NOT INCREASE YOUR CHANCES" in rules)
chk("VOID WHERE PROHIBITED present", "VOID WHERE PROHIBITED" in rules)
chk("free method of entry described",
    "FREE METHOD OF ENTRY BY MAIL" in rules)
chk("mail-in address present in rules",
    "5456 Peachtree Blvd" in rules and "Atlanta, GA" in rules)
# Guard against the invalid-ZIP regression: 31413 does not exist
# (verified 404 via zippopotam.us). An undeliverable AMOE address
# defeats the entire sweepstakes structure.
chk("mail ZIP is the verified Atlanta ZIP (30341)",
    sw.MAIL_ZIP == "30341")
chk("known-bad ZIP 31413 is NOT in the rules",
    "31413" not in rules)
chk("received-by-drawing-date deadline stated",
    "received by the\n       drawing date to be included in the drawing" in rules)
chk("one entry per envelope stated",
    "one (1) entry per outer mailing envelope" in rules)
chk("mail-in equal chance stated",
    "SAME\n       chance of winning" in rules or "SAME" in rules)
chk("lost mail disclaimer present",
    "not\n       responsible for lost" in rules or "responsible for lost" in rules)
chk("equal chance stated explicitly",
    "EQUAL CHANCE" in rules and "OF WINNING" in rules)
chk("sponsor identified", "Test Sponsor LLC" in rules)
chk("sponsor address present", "Lawrenceville" in rules)
chk("ARV disclosed", "4,500.00" in rules)
chk("entry period disclosed", "Entry Period" in rules)
chk("winner selection described", "random drawing" in rules.lower())
chk("bot entries voided", "automated means" in rules)
chk("attorney-review warning present",
    "NOT been\nreviewed by an attorney" in rules or
    "reviewed by an attorney" in rules)

print("\n6. Abuse controls (must not restrict free path unfairly)")
print("-" * 64)

n_before = db.amoe_count_for_ip(rid, "hash_abuse")
eq("new IP starts at 0 grants", n_before, 0)

for i in range(3):
    db.amoe_entry(rid, f"User {i}", f"u{i}@abuse.com", ip_hash="hash_abuse")
n_after = db.amoe_count_for_ip(rid, "hash_abuse")
eq("IP grant count tracked", n_after, 3)

chk("IP limit is a real threshold", sw.MAX_AMOE_PER_IP_PER_DAY > 0)
chk("IP limit generous enough for shared NAT",
    sw.MAX_AMOE_PER_IP_PER_DAY >= 5)

# entry cap counts BOTH paid and free -- must not bind only free entrants
cap_paid = db.entries_for_email(rid, "patty@test.com")
cap_free = db.entries_for_email(rid, "fred@test.com")
eq("entry cap counts paid entries", cap_paid, 5)
eq("entry cap counts free entries equally", cap_free, 5)

print("\n7. Audit trail")
print("-" * 64)

db.log_amoe_rejection(rid, "Bad Actor", "bad@test.com", "hash_bad",
                      "rate limit exceeded")
st = db.amoe_stats(rid)
chk("granted requests logged", st["granted"] >= 4)
chk("rejected requests logged", st["rejected"] >= 1)
eq("total = granted + rejected", st["total"], st["granted"] + st["rejected"])

print("\n8. entry_source separates AMOE from admin comp")
print("-" * 64)

comp = db.issue_comp_tickets(rid, "Event Ed", "ed@test.com", "", 2,
                             "event booth")
import sqlite3
conn = db.connect()
rows = conn.execute(
    "SELECT entry_source, COUNT(*) c FROM orders WHERE raffle_id=? GROUP BY entry_source",
    (rid,)).fetchall()
conn.close()
srcs = {r["entry_source"]: r["c"] for r in rows}
print(f"      {dict(srcs)}")
chk("'amoe' source recorded", srcs.get("amoe", 0) >= 4)
chk("'comp' source recorded", srcs.get("comp", 0) >= 1)
chk("'purchase' source recorded", srcs.get("purchase", 0) >= 1)
chk("amoe and comp are distinguishable",
    "amoe" in srcs and "comp" in srcs)

print("\n7a. Required-field validation (address / phone)")
print("-" * 64)

# phone: digit-count based so formatting variations pass
for good in ["7705551234", "(770) 555-1234", "770-555-1234", "+1 770 555 1234"]:
    chk(f"phone accepted: {good}", sw.validate_phone(good)[0])
for bad in ["", "555", "abc", "12345"]:
    chk(f"phone rejected: {bad!r}", not sw.validate_phone(bad)[0])

# address: must be plausibly mailable
for good in ["99 Real Street, Atlanta GA 30341",
             "5456 Peachtree Blvd Suite 134 Atlanta GA 30341"]:
    chk(f"address accepted: {good[:28]}", sw.validate_address(good)[0])
for bad in ["", "Atlanta", "Peachtree Blvd Atlanta GA", "99 St"]:
    chk(f"address rejected: {bad!r}", not sw.validate_address(bad)[0])

# Both paths: email + phone required, address optional
_full_ok, _ = sw.validate_amoe("Jane Doe", "j@d.com",
                               "99 Real St, Atlanta GA 30341", "7705551234")
chk("accepts full details", _full_ok)
chk("accepts no address (optional on both paths)",
    sw.validate_amoe("Jane Doe", "j@d.com", "", "7705551234")[0])
chk("rejects missing phone",
    not sw.validate_amoe("Jane Doe", "j@d.com",
                         "99 Real St, Atlanta GA 30341", "")[0])
chk("rejects missing email",
    not sw.validate_amoe("Jane Doe", "", "", "7705551234")[0])

print("\n7b. Household cap -- must bind BOTH paths equally")
print("-" * 64)

# normalisation
eq("apt variants normalise together",
   sw.household_key("123 Peachtree Street, Apt 4"),
   sw.household_key("123 peachtree st apt4"))
eq("street abbrev normalises",
   sw.household_key("456 Main St."), sw.household_key("456 main street"))
chk("different homes stay distinct",
    sw.household_key("123 Main St") != sw.household_key("125 Main St"))
eq("falls back to email with no address",
   sw.household_key("", "a@b.com"), "email:a@b.com")
eq("empty in, empty out", sw.household_key("", ""), "")

# equal enforcement on a fresh sweepstakes
hrid = db.create_raffle("Household Cap Test", 10.0, 2, ["A", "B"])
db.update_sweepstakes(hrid, entry_limit_per_household=1,
                      sponsor_name="S", sponsor_address="A",
                      start_at=(now - timedelta(days=1)).isoformat(),
                      end_at=(now + timedelta(days=10)).isoformat(),
                      prize_arv_total=100,
                      eligibility_text=sw.DEFAULT_ELIGIBILITY,
                      winner_selection_text=sw.DEFAULT_WINNER_SELECTION)

o1 = db.create_order(hrid, "Donor", "d1@hh.com", "", 1, "card")
db.confirm_payment(o1["lookup_code"], "ref", "test")
db.set_buyer_address(o1["buyer_id"], "500 Shared Rd")
eq("household holds 1 after donated entry",
   db.entries_for_household(hrid, "500 Shared Rd", ""), 1)

# same household via a DIFFERENT email + address spelling
eq("cap sees the household regardless of email/spelling",
   db.entries_for_household(hrid, "500 shared road", "other@hh.com"), 1)

# pending must count, or the cap is bypassable with unpaid orders
o2 = db.create_order(hrid, "Pending Guy", "d2@hh.com", "", 1, "zelle")
db.set_buyer_address(o2["buyer_id"], "600 Pending Ave")
eq("PENDING entries consume the household slot",
   db.entries_for_household(hrid, "600 Pending Ave", ""), 1)

# a free mail-in entry also occupies a slot
a1 = db.amoe_entry(hrid, "Mailer", "m1@hh.com", "", "700 Mail St", "mail", 1)
db.set_buyer_address(a1["buyer_id"], "700 Mail St")
eq("mail-in entry consumes the household slot",
   db.entries_for_household(hrid, "700 Mail St", ""), 1)

# rules language reflects the household limit
hs = db.get_raffle(hrid)
hrules = sw.build_rules(hs, ["A", "B"])
chk("rules state one entry per household",
    "one (1) entry per household" in hrules)
chk("rules state the cap applies to BOTH methods",
    "applies equally to entries" in hrules)

print("\n8b. Prize link URL sanitiser (XSS guard)")
print("-" * 64)
import views as _v
for bad in ["javascript:alert(1)", "JaVaScRiPt:alert(1)",
            "data:text/html,<script>", "vbscript:msgbox",
            "file:///etc/passwd"]:
    chk(f"rejects {bad[:22]}", _v.safe_url(bad) == "")
eq("bare domain gets https", _v.safe_url("coach.com/x"), "https://coach.com/x")
eq("https passes through", _v.safe_url("https://a.com"), "https://a.com")
eq("http passes through", _v.safe_url("http://a.com"), "http://a.com")
eq("protocol-relative becomes https", _v.safe_url("//cdn.a.com/x"),
   "https://cdn.a.com/x")
eq("empty stays empty", _v.safe_url(""), "")

print("\n8c. Prize image URL sanitiser (safe_img)")
print("-" * 64)
chk("local static path passes", _v.safe_img("/static/prizes/x.jpg") == "/static/prizes/x.jpg")
chk("rejects javascript: as image src", _v.safe_img("javascript:alert(1)") == "")
eq("bare domain gets https (image)", _v.safe_img("cdn.example.com/x.jpg"),
   "https://cdn.example.com/x.jpg")
eq("empty stays empty (image)", _v.safe_img(""), "")

print("\n9. IP hashing (no raw PII stored)")
print("-" * 64)

h = sw.hash_ip("192.168.1.50")
chk("IP is hashed, not stored raw", "192.168" not in h)
eq("hash is stable", h, sw.hash_ip("192.168.1.50"))
chk("different IPs hash differently", h != sw.hash_ip("192.168.1.51"))
eq("empty IP yields empty hash", sw.hash_ip(""), "")

print()
print("=" * 64)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 64)
raise SystemExit(1 if F else 0)
