"""Purchase-page hit counter tests.

The public ticket purchase page should count visits for admin-only analytics,
without exposing raw IP addresses or changing sweepstakes odds/ticket counts.
"""
import os

SCRATCH = "/tmp/hit_count_test.db"
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["RAFFLE_DB_PATH"] = SCRATCH
os.environ["SWEEPS_IP_SALT"] = "hit-test-salt"

import db
import views
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


db.init_db()
conn = db.connect()
conn.execute("""INSERT INTO raffles (id,name,ticket_price,num_prizes,
    prize_1,prize_2,prize_3,status,created_at) VALUES
    (1,'Hit Count Test',10.0,3,'Bag','TV','Gift Card','open',?)""", (db.now(),))
conn.commit(); conn.close()

print("=" * 70)
print("1. Hits are recorded and classified")
print("=" * 70)
db.record_raffle_page_hit(1, "/raffle/1", "203.0.113.10", "Mozilla/5.0", "")
db.record_raffle_page_hit(1, "/raffle/1", "203.0.113.10", "Mozilla/5.0", "")
db.record_raffle_page_hit(1, "/raffle/1", "198.51.100.99", "TelegramBot (like TwitterBot)", "")
stats = db.raffle_page_hit_stats(1)
chk("total hits", stats["total"], 3)
chk("visitor hits excludes bot", stats["human_hits"], 2)
chk("bot/preview hits", stats["bot_hits"], 1)
chk("unique hashed IPs", stats["unique_ips"], 2)
chk("recent rows limited", len(stats["recent"]), 3)

print("\n" + "=" * 70)
print("2. Raw IP addresses are not stored")
print("=" * 70)
conn = db.connect()
raw_hits = conn.execute("""SELECT COUNT(*) c FROM raffle_page_hits
                           WHERE ip_hash IN ('203.0.113.10','198.51.100.99')""").fetchone()["c"]
hashed = conn.execute("SELECT ip_hash FROM raffle_page_hits LIMIT 1").fetchone()["ip_hash"]
conn.close()
chk("no raw IP stored", raw_hits, 0)
chk("hash length", len(hashed), 32)

print("\n" + "=" * 70)
print("3. Tracking does not affect ticket odds/pool")
print("=" * 70)
chk("active tickets still zero", db.total_tickets(1), 0)
odds = compute_odds(db.total_tickets(1) + 1, 1, 3)
chk("odds unaffected structurally", odds["num_prizes"], 3)

print("\n" + "=" * 70)
print("4. Admin dashboard renders hit-count card")
print("=" * 70)
raffle = db.get_raffle(1)
assert raffle is not None
html = views.page_admin(
    raffle, db.total_tickets(1), db.pending_tickets(1), db.revenue(1),
    db.pending_revenue(1), [], [], [], [], db.comp_stats(1),
    db.printed_counts(1), stats)
chk("admin has traffic card", "Ticket purchase link traffic" in html, True)
chk("admin has total hits", "Total hits" in html and ">3<" in html, True)
chk("admin has bot label", "bot/preview" in html, True)
chk("public raw IP absent from admin", "203.0.113.10" in html, False)

print("\nRESULTS:", P, "passed,", F, "failed")
raise SystemExit(1 if F else 0)
