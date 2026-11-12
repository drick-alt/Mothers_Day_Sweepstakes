"""Create-raffle controls must be admin-only.

Participants can visit the public homepage to donate/enter or look up receipts,
but should not see campaign-management tools such as creating another raffle.
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


db.init_db()
RID = db.create_raffle("Visibility Test", 10.0, 2, ["A", "B"])
raffle = db.get_raffle(RID)

print("=" * 70)
print("1. Public homepage has no create-raffle controls")
print("=" * 70)
public_html = views.page_home([raffle], mock=False)
chk("public donate link still present", f'/raffle/{RID}' in public_html, True)
chk("public lookup form still present", 'action="/lookup"' in public_html, True)
chk("public create title absent", "Create a sweepstakes" in public_html, False)
chk("public create another absent", "Create another raffle" in public_html, False)
chk("public admin create form action absent", 'action="/admin/create"' in public_html, False)
chk("public admin link absent", f'/admin/{RID}' in public_html, False)

print()
print("=" * 70)
print("2. Admin dashboard keeps create-raffle controls")
print("=" * 70)
admin_html = views.page_admin(
    raffle,
    total=0,
    pend_t=0,
    rev=0,
    pend_rev=0,
    board=[],
    pending=[],
    breakdown=[],
    winners=[],
    comp=db.comp_stats(RID),
    printed=db.printed_counts(RID),
    hits=db.raffle_page_hit_stats(RID),
    seller_board=[],
)
chk("admin create card present", "Create another raffle" in admin_html, True)
chk("admin create form action present", 'action="/admin/create"' in admin_html, True)
chk("admin-only note present", "Participants cannot see this form" in admin_html, True)
chk("admin live clock present", 'id="admin-live-clock"' in admin_html, True)
chk("admin live clock time element present", 'id="admin-live-clock-time"' in admin_html, True)
chk("admin live clock date element present", 'id="admin-live-clock-date"' in admin_html, True)
chk("admin live clock ticks every second", "setInterval(tick, 1000)" in admin_html, True)
chk("admin live clock near top", admin_html.find('id="admin-live-clock"') < admin_html.find("Paid Tickets Sold"), True)

print()
print("=" * 70)
print(f"RESULTS: {P} passed, {F} failed")
print("=" * 70)
raise SystemExit(1 if F else 0)
