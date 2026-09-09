"""HTML rendering. Server-rendered, no build step."""

from html import escape
from odds import pct

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0f1117;color:#e6e8ee;line-height:1.6;padding:20px}
.wrap{max-width:920px;margin:0 auto}
a{color:#6ea8fe;text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:28px;margin-bottom:6px;color:#fff}
h2{font-size:20px;margin:24px 0 12px;color:#fff}
.sub{color:#9aa3b2;margin-bottom:24px}
.card{background:#171a23;border:1px solid #262b38;border-radius:12px;padding:20px;margin-bottom:16px}
.flyer{display:block;width:100%;border-radius:14px;border:1px solid #40351f;box-shadow:0 18px 45px rgba(0,0,0,.45);margin:0 0 14px}
.flyer-note{font-size:13px;color:#cbd5e1;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat{background:#1d2130;border:1px solid #2b3142;border-radius:10px;padding:14px}
.stat .label{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#8b93a5}
.stat .value{font-size:24px;font-weight:700;color:#fff;margin-top:4px}
.big{font-size:44px;font-weight:800;color:#4ade80;line-height:1.1}
.big.warn{color:#fbbf24}.big.low{color:#f87171}
label{display:block;font-size:13px;color:#9aa3b2;margin:12px 0 4px}
input,select{width:100%;padding:10px 12px;background:#0f1117;border:1px solid #2b3142;
border-radius:8px;color:#e6e8ee;font-size:15px}
button{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:12px 20px;
font-size:15px;font-weight:600;cursor:pointer;margin-top:16px}
button:hover{background:#1d4ed8}
button.danger{background:#dc2626}button.danger:hover{background:#b91c1c}
button.ok{background:#059669}button.ok:hover{background:#047857}
button.sm{padding:6px 12px;font-size:13px;margin:0}
table{width:100%;border-collapse:collapse;margin-top:12px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;
color:#8b93a5;padding:8px;border-bottom:1px solid #2b3142}
td{padding:8px;border-bottom:1px solid #1d2130;font-size:14px}
.ticket{display:inline-block;background:#1d2130;border:1px solid #2b3142;
border-radius:6px;padding:6px 10px;margin:3px;font-family:monospace;font-size:14px}
.ticket.pending{opacity:.45;border-style:dashed}
.code{font-family:monospace;font-size:22px;letter-spacing:3px;color:#4ade80;
background:#0f1117;padding:10px 16px;border-radius:8px;display:inline-block;border:1px solid #2b3142}
.memo{font-family:monospace;font-size:20px;color:#fbbf24;background:#0f1117;
padding:10px 16px;border-radius:8px;display:inline-block;border:1px solid #3b2f0b}
.err{background:#3b1219;border:1px solid #7f1d1d;color:#fca5a5;padding:12px;border-radius:8px;margin-bottom:16px}
.warn{background:#3b2f0b;border:1px solid #78350f;color:#fcd34d;padding:12px;border-radius:8px;margin-bottom:16px}
.info{background:#0c2a3d;border:1px solid #075985;color:#7dd3fc;padding:12px;border-radius:8px;margin-bottom:16px}
.nav{margin-bottom:20px;font-size:14px}
.badge{display:inline-block;padding:3px 10px;border-radius:99px;font-size:11px;font-weight:600;text-transform:uppercase}
.badge.open,.badge.paid{background:#064e3b;color:#4ade80}
.badge.drawn,.badge.pending{background:#3b2f0b;color:#fbbf24}
.badge.cancelled{background:#3b1219;color:#fca5a5}
.pm{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:8px}
.pm label{display:flex;align-items:center;gap:8px;background:#1d2130;border:1px solid #2b3142;
border-radius:10px;padding:12px;cursor:pointer;margin:0;color:#e6e8ee;font-size:14px}
.pm label:hover{border-color:#3b82f6}
.pm input{width:auto;margin:0}
.pm .n{font-size:11px;color:#8b93a5;display:block;margin-top:2px}
.badge.comp{background:#3b1f4d;color:#d8b4fe}
.gift{background:linear-gradient(135deg,#4c1d95,#6d28d9);border:1px solid #7c3aed;
border-radius:12px;padding:24px;text-align:center;margin-bottom:16px}
.gift .t{font-size:13px;text-transform:uppercase;letter-spacing:2px;color:#d8b4fe}
.gift .n{font-size:34px;font-weight:800;color:#fff;margin:8px 0}
.gift .s{color:#e9d5ff;font-size:14px}
.slip{border:2px dashed #7c3aed;border-radius:12px;padding:20px;margin:12px 0}
tr.comp td{background:#1a1428}
ol{padding-left:22px}ol li{margin:6px 0}
.npn{background:#1e3a5f;border:2px solid #3b82f6;border-radius:8px;padding:14px;margin-bottom:18px;text-align:center}
.npn b{color:#93c5fd;font-size:15px;letter-spacing:.5px;display:block;margin-bottom:4px}
.npn span{font-size:12px;color:#cbd5e1}
.npn a{color:#60a5fa;font-weight:600}
.freebox{background:#064e3b;border:2px solid #10b981;border-radius:10px;padding:20px;margin:18px 0}
.freebox h3{color:#6ee7b7;margin:0 0 8px}
.freebox p{font-size:13px;color:#d1fae5;margin-bottom:12px}
.rules{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:20px;
  font-family:ui-monospace,Menlo,monospace;font-size:12px;line-height:1.7;
  white-space:pre-wrap;color:#cbd5e1;max-height:70vh;overflow-y:auto}
.cwarn{background:#450a0a;border:2px solid #dc2626;border-radius:8px;padding:14px;margin:14px 0}
.cwarn b{color:#fca5a5}
.cwarn ul{margin:8px 0 0 18px;font-size:13px;color:#fecaca}
.period{background:#1e293b;border-left:4px solid #3b82f6;padding:10px 14px;
  border-radius:0 6px 6px 0;margin-bottom:16px;font-size:13px;color:#cbd5e1}
.errbox{background:#450a0a;border:1px solid #dc2626;border-radius:6px;padding:12px;margin-bottom:14px;color:#fca5a5;font-size:13px}
@media print{body{background:#fff;color:#000}.noprint{display:none}
.card{border:1px solid #ccc;background:#fff}td,th{color:#000}}
"""


def shell(title, body, nav=""):
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style></head>'
            f'<body><div class="wrap">{nav}{body}</div></body></html>')


def _oc(v):
    return "big" if v >= 0.25 else ("big warn" if v >= 0.05 else "big low")


def _mock_banner(mock):
    if not mock:
        return ""
    return ('<div class="warn"><b>TEST MODE</b> &mdash; no Stripe/PayPal keys '
            'configured. Card, Apple Pay, Google Pay, Cash App and Venmo route '
            'to a local simulator. Zelle and cash work normally (they are manual '
            'by design). Set STRIPE_SECRET_KEY to go live.</div>')


def page_home(raffles, mock=False):
    rows = ""
    for r in raffles:
        rows += (f'<div class="card"><h2 style="margin-top:0">{escape(r["name"])} '
                 f'<span class="badge {r["status"]}">{r["status"]}</span></h2>'
                 f'<p class="sub">${r["ticket_price"]:.2f} per ticket &middot; '
                 f'{r["num_prizes"]} prizes</p>'
                 f'<a href="/raffle/{r["id"]}">Donate &amp; enter &rarr;</a> &nbsp;|&nbsp; '
                 f'<a href="/admin/{r["id"]}">Admin</a></div>')
    if not raffles:
        rows = '<div class="card"><p>No sweepstakes yet.</p></div>'
    return shell("Sweepstakes", f"""<h1>Sweepstakes</h1>
<p class="sub">Donate to enter, track your odds, print the drum list.</p>
{_mock_banner(mock)}
<div class="card"><form method="get" action="/lookup">
<label>Already bought? Enter your lookup code</label>
<input name="code" placeholder="ABCD2345" style="text-transform:uppercase">
<button type="submit">Find my tickets</button></form></div>
{rows}
<div class="card"><h2 style="margin-top:0">Create a sweepstakes</h2>
<form method="post" action="/admin/create">
<label>Sweepstakes name</label><input name="name" required>
<label>Ticket price ($)</label><input name="ticket_price" type="number" step="0.01" value="10.00">
<label>Prize 1</label><input name="prize_1" value="Grand Prize">
<label>Prize 2</label><input name="prize_2" value="Second Prize">
<label>Prize 3</label><input name="prize_3" value="Third Prize">
<label>Prize 4</label><input name="prize_4" value="Fourth Prize">
<button type="submit">Create Sweepstakes</button></form></div>""")


def page_buy(raffle, qty, preview, methods, mock=False):
    prizes = prize_items(raffle)
    v = preview["at_least_one"]

    pm = ""
    for i, m in enumerate(methods):
        if not m["ready"]:
            continue
        checked = "checked" if m["key"] == "card" else ""
        pm += (f'<label><input type="radio" name="payment_method" '
               f'value="{m["key"]}" {checked}><span>{escape(m["label"])}'
               f'<span class="n">{escape(m["note"])}</span></span></label>')

    return shell(raffle["name"], f"""
<h1>{escape(raffle['name'])}</h1>
<p class="sub">${raffle['ticket_price']:.2f} suggested donation per entry &middot; {raffle['num_prizes']} prizes
&middot; <span class="badge {raffle['status']}">{raffle['status']}</span></p>
{_mock_banner(mock)}
<div class="card"><h2 style="margin-top:0">Mother's Day Sweepstakes Drawing</h2>
<img class="flyer" src="/static/prizes/mothers_day_sweepstakes_drawing_flyer_v2.png"
     alt="Mother's Day Sweepstakes Drawing flyer showing the prize drawing">
<div class="flyer-note">Prize details:</div>{prizes}</div>
<div class="card"><h2 style="margin-top:0">If you enter with {qty} entry(ies) right now</h2>
<div class="{_oc(v)}">{pct(v)}</div>
<p class="sub">chance to win at least one prize</p>
<p style="font-size:13px;color:#8b93a5">Expected prizes: {preview['expected_prizes']:.3f}
&middot; Per-prize: {pct(preview['per_prize'])}</p></div>
<div class="card"><h2 style="margin-top:0">Donate &amp; enter</h2>
<form method="post" action="/buy">
<input type="hidden" name="raffle_id" value="{raffle['id']}">
<label>Your name *</label><input name="name" required>
<label>Email *</label>
<input name="email" type="email" placeholder="for your receipt" required>
<label>Phone *</label>
<input name="phone" type="tel" placeholder="So we can reach you if you win" required>
<label>Street address</label>
<input name="address" placeholder="Optional">
<label>How many entries?</label>
<input name="quantity" type="number" min="1" max="1000" value="{qty}" required>
<label style="margin-top:18px">Donation method</label><div class="pm">{pm}</div>
<button type="submit">Continue to Donation</button></form>
<p style="font-size:12px;color:#8b93a5;margin-top:12px">Preview odds for entries:
<a href="/raffle/{raffle['id']}?qty=1">1</a> &middot;
<a href="/raffle/{raffle['id']}?qty=5">5</a> &middot;
<a href="/raffle/{raffle['id']}?qty=10">10</a> &middot;
<a href="/raffle/{raffle['id']}?qty=25">25</a></p></div>
{npn_banner(raffle["id"])}""",
    nav='<div class="nav"><a href="/">&larr; All sweepstakes</a></div>')


def page_offline_pay(order, inst):
    steps = "".join(f"<li>{escape(s)}</li>" for s in inst["steps"])
    return shell(inst["title"], f"""
<h1>{escape(inst['title'])}</h1>
<p class="sub">{escape(order['raffle_name'])} &mdash; {order['quantity']} ticket(s)</p>
<div class="warn">{escape(inst['warning'])}</div>
<div class="card"><div class="grid">
<div class="stat"><div class="label">Amount Due</div><div class="value">{inst['amount']}</div></div>
<div class="stat"><div class="label">Send To</div>
<div class="value" style="font-size:15px">{escape(inst['handle'])}</div></div>
</div>
<p style="margin-top:18px;font-size:13px;color:#9aa3b2">Put this code in the payment memo:</p>
<div class="memo">{escape(inst['memo'])}</div></div>
<div class="card"><h2 style="margin-top:0">Steps</h2><ol>{steps}</ol></div>
<div class="card"><p style="font-size:13px;color:#9aa3b2">Save your lookup code:</p>
<div class="code">{escape(order['lookup_code'])}</div>
<p style="margin-top:14px"><a href="/receipt/{escape(order['lookup_code'])}">
View my receipt &rarr;</a></p></div>""",
    nav='<div class="nav"><a href="/">&larr; All sweepstakes</a></div>')


def page_mock_gateway(order, session, method):
    return shell("Test Payment", f"""
<h1>Test Payment Gateway</h1>
<p class="sub">Simulator &mdash; no real money moves</p>
<div class="info">This stands in for {escape(method)} checkout because no live
API keys are configured. Clicking Pay fires the same code path a real webhook
would.</div>
<div class="card"><div class="grid">
<div class="stat"><div class="label">Amount</div>
<div class="value">${order['amount_paid']:,.2f}</div></div>
<div class="stat"><div class="label">Method</div>
<div class="value" style="font-size:16px">{escape(method)}</div></div>
<div class="stat"><div class="label">Tickets</div><div class="value">{order['quantity']}</div></div>
</div>
<p style="font-size:12px;color:#8b93a5;margin-top:12px">session: {escape(session)}</p>
<form method="post" action="/mock-pay/{escape(order['lookup_code'])}/complete">
<button type="submit" class="ok">Pay ${order['amount_paid']:,.2f}</button></form>
<p style="margin-top:12px"><a href="/cancelled/{escape(order['lookup_code'])}">
Cancel payment</a></p></div>""")


def page_cancelled(order):
    return shell("Payment Cancelled", f"""
<h1>Payment cancelled</h1>
<p class="sub">{escape(order['raffle_name'])}</p>
<div class="err">Your order was cancelled and the reserved tickets were released.
Nothing was charged.</div>
<div class="card"><p><a href="/raffle/{order['raffle_id']}">
&larr; Back to buy tickets</a></p></div>""")


def page_receipt(order, o, marginal, winners, offline_inst=None):
    ps = order["payment_status"]
    tix = "".join(
        f'<span class="ticket{" pending" if t["status"] != "active" else ""}">'
        f'{escape(t["ticket_number"])}</span>' for t in order["ticket_rows"])

    banner = ""
    if ps == "pending":
        banner = ('<div class="warn"><b>PAYMENT PENDING</b> &mdash; your ticket '
                  'numbers are reserved but are <b>not in the drawing yet</b> and '
                  'do not count toward the pool until payment is confirmed.</div>')
    elif ps == "cancelled":
        banner = '<div class="err"><b>CANCELLED</b> &mdash; this order was voided.</div>'

    inst_html = ""
    if offline_inst:
        steps = "".join(f"<li>{escape(s)}</li>" for s in offline_inst["steps"])
        inst_html = (f'<div class="card"><h2 style="margin-top:0">'
                     f'{escape(offline_inst["title"])}</h2>'
                     f'<p style="font-size:13px;color:#9aa3b2">Memo code:</p>'
                     f'<div class="memo">{escape(offline_inst["memo"])}</div>'
                     f'<ol style="margin-top:14px">{steps}</ol></div>')

    odds_html = ""
    if ps == "paid":
        v = o["at_least_one"]
        dist = "".join(f"<tr><td>Win exactly {j}</td><td>{pct(pr)}</td></tr>"
                       for j, pr in sorted(o["distribution"].items()) if pr > 1e-7)
        odds_html = f"""
<div class="card"><h2 style="margin-top:0">Your chance to win</h2>
<div class="{_oc(v)}">{pct(v)}</div>
<p class="sub">to win at least one of {o['num_prizes']} prizes</p>
<div class="grid">
<div class="stat"><div class="label">Your tickets</div><div class="value">{o['my_tickets']}</div></div>
<div class="stat"><div class="label">Odds</div><div class="value" style="font-size:18px">
{('1 in ' + format(o['one_in'], '.1f')) if o['one_in'] else '-'}</div></div>
<div class="stat"><div class="label">Expected prizes</div><div class="value">{o['expected_prizes']:.3f}</div></div>
</div>
<p style="font-size:13px;color:#8b93a5;margin-top:14px">One more ticket would add
<b style="color:#4ade80">{pct(marginal)}</b>.</p></div>
<div class="card"><h2 style="margin-top:0">Exact outcome breakdown</h2>
<table><tr><th>Outcome</th><th>Probability</th></tr>{dist}</table></div>"""

    win_html = ""
    if winners:
        mine = {t["ticket_number"] for t in order["ticket_rows"]
                if t["status"] == "active"}
        rows = "".join(
            f"<tr><td>{escape(w['prize_name'])}</td><td>{escape(w['ticket_number'])}</td>"
            f"<td>{escape(w['buyer_name'])}"
            f"{'&nbsp;&larr; <b style=color:#4ade80>YOU WON!</b>' if w['ticket_number'] in mine else ''}"
            f"</td></tr>" for w in winners)
        win_html = (f'<div class="card"><h2 style="margin-top:0">Winners</h2><table>'
                    f'<tr><th>Prize</th><th>Ticket</th><th>Winner</th></tr>{rows}</table></div>')

    return shell("Your Receipt", f"""
<h1>Receipt <span class="badge {ps}">{ps}</span></h1>
<p class="sub">{escape(order['raffle_name'])}</p>
{banner}
<div class="card"><p style="font-size:13px;color:#8b93a5;margin-bottom:8px">
Save this code to get back to your tickets:</p>
<div class="code">{escape(order['lookup_code'])}</div>
<p style="font-size:12px;color:#8b93a5;margin-top:10px">
Receipt: {escape(order['receipt_id'])} &middot;
{'<b style="color:#d8b4fe">FREE GIVEAWAY TICKET</b>' if order['payment_method'] == 'comp'
 else 'Paid via: ' + escape(order['payment_method'])}</p></div>
<div class="card"><div class="grid">
<div class="stat"><div class="label">Entrant</div>
<div class="value" style="font-size:16px">{escape(order['buyer_name'])}</div></div>
<div class="stat"><div class="label">Tickets</div><div class="value">{order['quantity']}</div></div>
<div class="stat"><div class="label">Amount</div>
<div class="value">${order['amount_paid']:,.2f}</div></div>
</div></div>
{inst_html}{odds_html}
<div class="card"><h2 style="margin-top:0">Your tickets</h2><div>{tix}</div>
{'<p style="font-size:12px;color:#8b93a5;margin-top:10px">Dashed = pending payment</p>' if ps != 'paid' else ''}
</div>{win_html}""",
    nav='<div class="nav"><a href="/">&larr; All sweepstakes</a></div>')


def page_giveaway_slip(order, o):
    """Printable slip handed to someone at an event."""
    tix = "".join(f'<span class="ticket">{escape(t["ticket_number"])}</span>'
                  for t in order["ticket_rows"])
    v = o["at_least_one"]
    return shell("Free Raffle Ticket", f"""
<div class="gift"><div class="t">Free Giveaway Ticket</div>
<div class="n">{order['quantity']} Ticket{'s' if order['quantity'] != 1 else ''}</div>
<div class="s">{escape(order['raffle_name'])}</div></div>

<div class="card slip">
<p style="font-size:13px;color:#9aa3b2">Issued to</p>
<h2 style="margin:4px 0 16px">{escape(order['buyer_name'])}</h2>
<p style="font-size:13px;color:#9aa3b2">Ticket number{'s' if order['quantity'] != 1 else ''}</p>
<div style="margin:8px 0 18px">{tix}</div>
<p style="font-size:13px;color:#9aa3b2">Check your odds anytime with this code:</p>
<div class="code">{escape(order['lookup_code'])}</div>
<p style="font-size:12px;color:#8b93a5;margin-top:14px">
Receipt {escape(order['receipt_id'])} &middot; Value $0.00 &middot; No purchase necessary</p>
</div>

<div class="card"><h2 style="margin-top:0">Current chance to win</h2>
<div class="{_oc(v)}">{pct(v)}</div>
<p class="sub">to win one of {o['num_prizes']} prizes &middot;
pool is {o['total_tickets']} tickets</p>
<p style="font-size:13px;color:#8b93a5">This is a real entry &mdash; it counts
exactly like a purchased ticket.</p></div>

<div class="noprint"><button onclick="window.print()">Print this slip</button>
&nbsp; <a href="/receipt/{escape(order['lookup_code'])}">Full receipt &rarr;</a>
&nbsp; <a href="/admin/{order['raffle_id']}">&larr; Admin</a></div>""")


def page_lookup(error=None):
    err = f'<div class="err">{escape(error)}</div>' if error else ""
    return shell("Find My Tickets", f"""<h1>Find my tickets</h1>
<p class="sub">Enter the lookup code from your receipt.</p>{err}
<div class="card"><form method="get" action="/lookup">
<label>Lookup code</label>
<input name="code" required placeholder="ABCD2345" style="text-transform:uppercase">
<button type="submit">Find my tickets</button></form></div>""",
    nav='<div class="nav"><a href="/">&larr; All sweepstakes</a></div>')



# Human labels for payment methods shown in the admin entrants table.
# 'amoe' is the mail-in FREE entry path -- it must be visibly labelled as
# free so nobody mistakes a mail-in entrant for a non-payer in arrears.
METHOD_LABELS = {
    "card": "Card", "apple_pay": "Apple Pay", "google_pay": "Google Pay",
    "cashapp": "Cash App", "venmo": "Venmo", "zelle": "Zelle",
    "cash": "Cash", "comp": "Giveaway", "amoe": "AMOE (mail-in)",
}
# free methods get a distinct colour so they read as $0 at a glance
METHOD_FREE = {"amoe", "comp"}


def method_badges(methods):
    """Render a buyer's payment method(s) as small badges."""
    if not methods:
        return '<span style="color:#64748b">-</span>'
    out = []
    for m in str(methods).split(","):
        m = m.strip()
        if not m:
            continue
        label = METHOD_LABELS.get(m, m)
        if m == "amoe":
            css = "background:#064e3b;color:#6ee7b7;border:1px solid #10b981"
        elif m == "comp":
            css = "background:#2e1065;color:#c4b5fd;border:1px solid #7c3aed"
        else:
            css = "background:#1e293b;color:#cbd5e1;border:1px solid #475569"
        out.append(f'<span style="{css};border-radius:5px;padding:2px 7px;'
                   f'font-size:11px;white-space:nowrap;margin-right:4px;'
                   f'display:inline-block">{escape(label)}</span>')
    return "".join(out)


def page_admin(raffle, total, pend_t, rev, pend_rev, board, pending, breakdown,
               winners, comp=None):
    rows = "".join(f"<tr><td>{escape(b['buyer_name'])}</td>"
                   f"<td>{method_badges(b.get('methods'))}</td>"
                   f"<td>{b['tickets']}</td>"
                   f"<td>{pct(b['odds'])}</td><td>{b['expected']:.3f}</td></tr>"
                   for b in board) or \
        '<tr><td colspan="5" style="color:#8b93a5">No entries yet.</td></tr>'

    pend_html = ""
    if pending:
        pr = ""
        for o in pending:
            pr += (f"<tr><td>{escape(o['buyer_name'])}</td>"
                   f"<td>{escape(o['payment_method'])}</td>"
                   f"<td>{o['quantity']}</td><td>${o['amount_paid']:,.2f}</td>"
                   f"<td><code>{escape(o['memo_code'] or '-')}</code></td>"
                   f"<td><form method='post' action='/admin/confirm/{escape(o['lookup_code'])}' "
                   f"style='display:inline'><button class='ok sm' type='submit'>Approve</button></form> "
                   f"<form method='post' action='/admin/reject/{escape(o['lookup_code'])}' "
                   f"style='display:inline' onsubmit=\"return confirm('Reject this order?')\">"
                   f"<button class='danger sm' type='submit'>Reject</button></form></td></tr>")
        pend_html = f"""<div class="card"><h2 style="margin-top:0">
Pending approvals ({len(pending)})</h2>
<p class="sub">Zelle/cash orders awaiting your confirmation. Match the memo code
in your banking app, then Approve.</p>
<table><tr><th>Entrant</th><th>Method</th><th>Qty</th><th>Amount</th>
<th>Memo</th><th>Action</th></tr>{pr}</table></div>"""

    bd = "".join(f"<tr><td>{escape(b['payment_method'])}</td>"
                 f"<td><span class='badge {b['payment_status']}'>{b['payment_status']}</span></td>"
                 f"<td>{b['orders']}</td><td>{b['tickets']}</td>"
                 f"<td>${b['amount']:,.2f}</td></tr>" for b in breakdown)

    comp = comp or {"comp": 0, "paid": 0}
    comp_tile = (f'<div class="stat"><div class="label">Giveaway</div>'
                 f'<div class="value" style="color:#d8b4fe">{comp["comp"]}</div></div>')

    prize_rows = ""
    for i in range(1, 5):
        try:
            u = raffle[f"prize_{i}_url"] or ""
        except (KeyError, IndexError):
            u = ""
        try:
            im = raffle[f"prize_{i}_img"] or ""
        except (KeyError, IndexError):
            im = ""
        prize_rows += (
            f'<label>Prize {i}</label>'
            f'<input name="prize_{i}" value="{escape(raffle[f"prize_{i}"] or "")}" '
            f'placeholder="Prize name">'
            f'<input name="prize_{i}_url" value="{escape(u)}" '
            f'placeholder="Link to the store/product page (optional)" '
            f'style="margin-top:4px">'
            f'<input name="prize_{i}_img" value="{escape(im)}" '
            f'placeholder="Image URL or /static/prizes/filename.jpg (optional)" '
            f'style="margin-top:4px;margin-bottom:14px">')

    details_html = f"""<div class="card">
<h2 style="margin-top:0"><a href="/admin/{raffle['id']}/details"
   style="color:#60a5fa">Sweepstakes Details &rarr;</a></h2>
<p class="sub">Sponsor info, <b>free-entry mail-in address</b>, entry period,
eligibility, and ARV. These feed the Official Rules.</p>
<p style="font-size:13px;color:#94a3b8">
Mail-in address: <span style="font-family:ui-monospace,Menlo,monospace;
color:#6ee7b7">{escape(", ".join(__import__("sweepstakes").mail_address_lines(raffle)[2:]))}</span>
</p></div>"""

    prize_html = f"""<div class="card"><h2 style="margin-top:0">
Prizes &amp; links</h2>
<p class="sub">Add a URL to make the prize name clickable on the entry
pages. Leave blank for plain text. Only http/https links are accepted.</p>
<form method="post" action="/admin/{raffle['id']}/prizes">
{prize_rows}
<label>Total ARV ($)</label>
<input name="prize_arv_total" type="number" step="0.01" min="0"
       value="{raffle['prize_arv_total'] or 0:.2f}">
<button type="submit">Save Prizes</button></form></div>"""

    give_html = f"""<div class="card"><h2 style="margin-top:0">
Record a mail-in free entry (AMOE)</h2>
<p class="sub">Open the envelope, enter the details, and an entry code is
generated. Mail-in entries have the <b>same odds</b> as donated entries.</p>
<form method="post" action="/admin/{raffle['id']}/mailin">
<label>Entrant name *</label><input name="name" required>
<label>Email * (entry code is emailed here)</label>
<input name="email" type="email" required>
<label>Phone *</label><input name="phone" type="tel" required>
<label>Return mailing address (from the envelope)</label>
<input name="address" placeholder="Optional - recommended for household matching">
<label>Postmark date * (from the envelope)</label>
<input name="postmark" type="date" required>
<button type="submit" class="ok">Generate Entry Code</button></form>
<p style="font-size:12px;color:#94a3b8;margin-top:10px">
One entry per outer envelope. Postmark must fall inside the entry period.
&nbsp;·&nbsp; <a href="/admin/{raffle['id']}/mailin-log">View mail-in log</a>
</p>
</div>

<div class="card"><h2 style="margin-top:0">
Issue free giveaway tickets</h2>
<p style="font-size:13px;color:#94a3b8">For in-person events. These are
discretionary gifts, tracked separately from mail-in AMOE entries.</p>
<form method="post" action="/admin/{raffle['id']}/giveaway">
<label>Recipient name *</label><input name="name" required>
<label>Email (optional)</label><input name="email" type="email">
<label>Phone (optional)</label><input name="phone">
<label>How many entries?</label>
<input name="quantity" type="number" min="1" max="1000" value="1" required>
<label>Note (e.g. which event)</label><input name="note" placeholder="Fall Festival booth">
<button type="submit">Issue Free Tickets</button></form></div>"""

    draw_btn = ""
    if raffle["status"] == "open" and total > 0:
        draw_btn = (f"<form method='post' action='/admin/{raffle['id']}/draw' "
                    f"onsubmit=\"return confirm('Draw winners now? Cannot be undone.')\">"
                    f"<button type='submit' class='danger'>Draw Winners</button></form>"
                    f"<p style='font-size:12px;color:#8b93a5;margin-top:8px'>"
                    f"Pool: {comp['paid']} donated + {comp['comp']} giveaway "
                    f"= {total} eligible."
                    f"{f' {pend_t} pending ticket(s) are excluded.' if pend_t else ''}</p>")
    elif winners:
        draw_btn = f'<p><a href="/admin/{raffle["id"]}/winners">View winners &rarr;</a></p>'

    return shell(f"Admin - {raffle['name']}", f"""
<h1>{escape(raffle['name'])} <span class="badge {raffle['status']}">{raffle['status']}</span></h1>
<p class="sub">Admin dashboard &middot; <a href="/admin/logout">Log out</a></p>
<div class="card"><div class="grid">
<div class="stat"><div class="label">Paid Tickets</div><div class="value">{total}</div></div>
<div class="stat"><div class="label">Pending</div>
<div class="value" style="color:#fbbf24">{pend_t}</div></div>
<div class="stat"><div class="label">Revenue</div><div class="value">${rev:,.2f}</div></div>
<div class="stat"><div class="label">Unconfirmed</div>
<div class="value" style="color:#fbbf24;font-size:20px">${pend_rev:,.2f}</div></div>
<div class="stat"><div class="label">Entrants</div><div class="value">{len(board)}</div></div>
{comp_tile}
</div></div>
{details_html}
{prize_html}
{give_html}
{pend_html}
<div class="card"><h2 style="margin-top:0">Drum list</h2>
<p class="sub">Paid tickets only. {pend_t} pending excluded.</p>
<a href="/admin/{raffle['id']}/drum">Printable drum list &rarr;</a><br>
<a href="/admin/{raffle['id']}/drum.csv">Download CSV &rarr;</a></div>
<div class="card"><h2 style="margin-top:0">Entrants &amp; odds</h2>
<p class="sub">Method is shown for accounting only &mdash; free entries
(AMOE mail-in and giveaways) have <b>identical odds</b> to donated entries.</p>
<table><tr><th>Entrant</th><th>Method</th><th>Entries</th><th>Win chance</th><th>Exp. prizes</th></tr>
{rows}</table></div>
<div class="card"><h2 style="margin-top:0">Payment methods</h2>
<table><tr><th>Method</th><th>Status</th><th>Orders</th><th>Tickets</th><th>Amount</th></tr>
{bd}</table></div>
<div class="card"><h2 style="margin-top:0">Draw</h2>{draw_btn}</div>""",
    nav='<div class="nav"><a href="/">&larr; All sweepstakes</a></div>')


def page_drum(raffle, tickets, pend=0, comp=None):
    comp = comp or {"comp": 0, "paid": 0}
    rows = ""
    for t in tickets:
        cls = " class='comp'" if t.get("is_comp") else ""
        tag = (' <span class="badge comp">free</span>'
               if t.get("is_comp") else "")
        rows += (f"<tr{cls}><td style='font-family:monospace;font-size:16px'>"
                 f"{escape(t['ticket_number'])}</td>"
                 f"<td>{escape(t['buyer_name'])}{tag}</td>"
                 f"<td>{escape(t['buyer_phone'] or '')}</td></tr>")
    note = (f'<div class="warn noprint">{pend} pending ticket(s) are excluded '
            f'&mdash; unpaid tickets never enter the drum.</div>') if pend else ""
    return shell(f"Drum List - {raffle['name']}", f"""
<h1>{escape(raffle['name'])} &mdash; Drum List</h1>
<p class="sub">{len(tickets)} eligible entries &mdash; {comp['paid']} donated,
{comp['comp']} giveaway &middot; Print, cut on the lines, drop in the drum.</p>
{note}
<div class="noprint" style="margin-bottom:16px">
<button onclick="window.print()">Print this page</button></div>
<div class="card"><table><tr><th>Ticket #</th><th>Name</th><th>Phone</th></tr>
{rows}</table></div>""",
    nav=f'<div class="nav noprint"><a href="/admin/{raffle["id"]}">&larr; Admin</a></div>')


def page_winners(raffle, winners):
    rows = "".join(f"<tr><td><b>{escape(w['prize_name'])}</b></td>"
                   f"<td style='font-family:monospace'>{escape(w['ticket_number'])}</td>"
                   f"<td>{escape(w['buyer_name'])}</td></tr>" for w in winners) or \
        '<tr><td colspan="3" style="color:#8b93a5">Not drawn yet.</td></tr>'
    return shell(f"Winners - {raffle['name']}", f"""
<h1>Winners</h1><p class="sub">{escape(raffle['name'])}</p>
<div class="card"><table><tr><th>Prize</th><th>Ticket</th><th>Winner</th></tr>
{rows}</table></div>""",
    nav=f'<div class="nav"><a href="/admin/{raffle["id"]}">&larr; Admin</a></div>')


# ==========================================================================
# SWEEPSTAKES COMPLIANCE VIEWS
# ==========================================================================

def npn_banner(rid):
    """NO PURCHASE NECESSARY banner.

    This must appear on every page where a purchase can be initiated,
    BEFORE the point of purchase -- not in a footer. It carries the
    link to the free entry path and to the Official Rules.
    """
    return f'''<div class="npn">
<b>Donations are Appreciated</b>
<span>Must be 18 years old to enter.<br>
<a href="/enter/{rid}">Sweepstakes Details</a></span>
</div>'''


def page_free_entry(s, allowed, period_msg, err="", ok=""):
    """The AMOE page -- FREE ENTRY BY MAIL.

    This page does not accept entries. It tells the entrant exactly how to
    mail one in. The instructions are deliberately short: a long list of
    requirements makes the free path burdensome and weakens the AMOE.
    """
    import sweepstakes as sw
    rid = s["id"]
    plist = prize_items(s)
    reqs = "".join(f"<li>{escape(f)}</li>" for f in sw.MAIL_REQUIRED_FIELDS)
    addr = "<br>".join(escape(l) for l in sw.mail_address_lines(s))

    deadline = ""
    end_dt = sw.parse_dt(s.get("end_at"))
    if end_dt:
        deadline = (f'<p style="font-size:13px;color:#fcd34d;margin-top:12px">'
                    f'<b>Deadline:</b> mail-in entries should be received by '
                    f'the drawing date to be included in the drawing.</p>')

    closed = ""
    if not allowed:
        closed = f'<div class="errbox">{escape(period_msg)}</div>'

    return shell(f"Free Entry by Mail - {escape(s['name'])}", f'''
<h1>{escape(s['name'])}</h1>
<div class="period">{escape(period_msg)}</div>
{closed}

<div class="freebox">
<h3>Free Entry by Mail — No Purchase Necessary</h3>
<p><b>A mail-in entry has exactly the same chance of winning as a
purchased entry.</b> Both go into the same pool and are indistinguishable
at the drawing. Purchasing does not improve your odds.</p>

<p style="color:#d1fae5;font-size:13px;margin-top:14px"><b>1.</b> Hand print
the following on a plain 3&quot; x 5&quot; card or piece of paper:</p>
<ul style="padding-left:20px;font-size:13px;color:#a7f3d0">{reqs}</ul>

<p style="color:#d1fae5;font-size:13px;margin-top:14px"><b>2.</b> Mail it in a
hand-addressed envelope with proper postage to:</p>
<div style="background:#022c22;border:1px dashed #10b981;border-radius:8px;
     padding:16px;margin-top:8px;font-family:ui-monospace,Menlo,monospace;
     font-size:14px;line-height:1.8;color:#6ee7b7">{addr}</div>

<p style="font-size:12px;color:#a7f3d0;margin-top:12px">
Limit one entry per outer mailing envelope. Each entry must be mailed
separately.</p>
{deadline}
</div>

<div class="card">
<h2 style="margin-top:0">Prizes</h2>
{plist}
</div>

<div class="card">
<p style="font-size:13px;color:#94a3b8">
Read the <a href="/rules/{rid}">Official Rules</a> before entering.<br>
You may also <a href="/raffle/{rid}">donate to enter</a> &mdash; donating
does <b>not</b> improve your odds of winning.
</p>
</div>
''')


def page_rules(s, text, complete, missing):
    """Official Rules page."""
    rid = s["id"]
    warn = ""
    if not complete:
        items = "".join(f"<li>{escape(m)}</li>" for m in missing)
        warn = f'''<div class="cwarn">
<b>⚠ These Official Rules are incomplete</b>
<ul>{items}</ul>
<p style="font-size:12px;color:#fecaca;margin-top:8px">
An administrator must complete these fields before the sweepstakes
is publicly run.</p>
</div>'''

    return shell(f"Official Rules - {escape(s['name'])}", f'''
<h1>Official Rules</h1>
{warn}
<div class="card">
<div class="rules">{escape(text)}</div>
</div>
<div class="card">
<a href="/rules/{rid}/text" class="btn">Plain text version</a>
<a href="/enter/{rid}" class="btn ok">Enter for free</a>
<a href="/raffle/{rid}" class="btn">Donate &amp; enter</a>
</div>
''')


def page_mailin_confirm(o, odds, warn=""):
    """Printable confirmation for a recorded mail-in entry.

    Print and staple to the physical entry card. This is what links the
    mailed paper to the ticket numbers actually in the drawing.
    """
    import sweepstakes as sw
    tickets = o.get("tickets") or []
    if isinstance(tickets, str):
        tickets = [t for t in tickets.split(",") if t]
    chips = "".join(f'<span class="chip">{escape(str(t))}</span>' for t in tickets)

    warnbox = ""
    if warn.strip():
        warnbox = f'<div class="cwarn"><b>{escape(warn.strip())}</b></div>'

    return shell("Mail-In Entry Recorded", f'''
<h1>Mail-In Entry Recorded</h1>
{warnbox}
<div class="slip">
<p style="font-size:12px;letter-spacing:1px;color:#a78bfa;margin-bottom:6px">
FREE ENTRY &mdash; NO PURCHASE NECESSARY</p>
<h2 style="margin:0 0 12px">{escape(o['buyer_name'])}</h2>

<p style="font-size:13px;color:#94a3b8;margin-bottom:4px">Entry code</p>
<div style="font-family:ui-monospace,Menlo,monospace;font-size:30px;
     font-weight:700;letter-spacing:3px;color:#6ee7b7;margin-bottom:14px">
{escape(o['lookup_code'])}</div>

<table>
<tr><th>Receipt</th><td>{escape(o['receipt_id'])}</td></tr>
<tr><th>Entries</th><td>{o['quantity']}</td></tr>
<tr><th>Value</th><td>$0.00 (free entry)</td></tr>
<tr><th>Chance to win</th><td><b>{pct(odds['at_least_one'])}</b></td></tr>
</table>

<p style="font-size:13px;color:#94a3b8;margin:14px 0 6px">Ticket numbers</p>
<div>{chips}</div>
</div>

<div class="card noprint">
<p style="font-size:13px;color:#94a3b8">
Print this and file it with the physical entry card.<br>
The entry code was also emailed to {escape(o['buyer_email'] or 'no email on file')}.
</p>
<a href="/admin/{o['raffle_id']}" class="btn">Back to admin</a>
<a href="/admin/{o['raffle_id']}/mailin-log" class="btn">Mail-in log</a>
<a href="javascript:window.print()" class="btn ok">Print</a>
</div>
''')


def page_mailin_log(s, rows, stats):
    """Mail-in compliance log -- the audit record for the AMOE."""
    rid = s["id"]
    if rows:
        body = "".join(
            f"<tr><td style='font-family:ui-monospace,Menlo,monospace'>"
            f"{escape(str(r.get('lookup_code') or '-'))}</td>"
            f"<td>{escape(r.get('name') or '')}</td>"
            f"<td>{escape(r.get('email') or '')}</td>"
            f"<td>{escape(str(r.get('postmark_date') or '-'))}</td>"
            f"<td>{escape(str(r.get('received_date') or '-'))}</td>"
            f"<td>{r.get('quantity') or 0}</td></tr>"
            for r in rows)
    else:
        body = ('<tr><td colspan="6" style="color:#94a3b8">'
                'No mail-in entries recorded yet.</td></tr>')

    return shell(f"Mail-In Log - {escape(s['name'])}", f'''
<h1>Mail-In Entry Log</h1>
<p class="sub">{escape(s['name'])}</p>

<div class="card"><div class="grid">
<div class="stat"><div class="label">Entries Granted</div>
  <div class="value">{stats['granted']}</div></div>
<div class="stat"><div class="label">Rejected</div>
  <div class="value">{stats['rejected']}</div></div>
<div class="stat"><div class="label">Total Requests</div>
  <div class="value">{stats['total']}</div></div>
</div></div>

<div class="card">
<table>
<tr><th>Entry Code</th><th>Name</th><th>Email</th>
    <th>Postmark</th><th>Received</th><th>Entries</th></tr>
{body}
</table>
</div>

<div class="card noprint">
<p style="font-size:13px;color:#94a3b8">
This log is the compliance record for the free entry path. Retain it with
the physical entry cards for the duration of the sweepstakes and any
applicable record-retention period.</p>
<a href="/admin/{rid}" class="btn">Back to admin</a>
<a href="/admin/{rid}/mailin-log.csv" class="btn">Export CSV</a>
</div>
''')


def safe_url(u):
    """Return a safe external URL, or '' if it isn't one.

    SECURITY: prize URLs are admin-supplied and rendered into an href.
    Without this, `javascript:` / `data:` schemes would execute in the
    visitor's browser. Only http and https are allowed through.
    """
    u = (u or "").strip()
    if not u:
        return ""
    low = u.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return u
    if low.startswith("//"):
        return "https:" + u
    # Anything else with a scheme separator is rejected outright --
    # javascript:, data:, vbscript:, file: etc. A ':' anywhere before the
    # first '/' also indicates a scheme, so reject that too.
    head = low.split("/", 1)[0]
    if ":" in head:
        return ""
    # bare domain typed by an admin -> assume https
    return "https://" + u


def safe_img(u):
    """Same scheme allow-list as safe_url, plus a bare local /static/ path.

    Prize images can come from an admin-typed external URL OR a file
    uploaded/copied into ./static/prizes -- both need to render safely.
    """
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("/static/"):
        return u
    return safe_url(u)


def prize_items(rec, with_images=True):
    """Render prize <li>s with an optional thumbnail and an optional link.

    Layout is a flex row so a plain-text prize (no image) still lines up
    cleanly with an image'd one.
    """
    out = []
    for i in range(1, 5):
        name = rec[f"prize_{i}"]
        if not name:
            continue
        try:
            url = safe_url(rec[f"prize_{i}_url"])
            img = safe_img(rec[f"prize_{i}_img"]) if with_images else ""
        except (KeyError, IndexError):
            url, img = "", ""

        thumb = ""
        if img:
            thumb = (f'<img src="{escape(img)}" alt="" loading="lazy" '
                     f'style="width:56px;height:40px;object-fit:cover;'
                     f'border-radius:6px;margin-right:10px;flex-shrink:0;'
                     f'border:1px solid #334155">')

        if url:
            label = (f'<a href="{escape(url)}" target="_blank" '
                    f'rel="noopener noreferrer" style="color:#60a5fa">'
                    f'{escape(name)}</a> '
                    f'<span style="font-size:11px;color:#64748b">&#8599; view</span>')
        else:
            label = escape(name)

        out.append(f'<li style="display:flex;align-items:center;'
                   f'margin-bottom:8px;list-style:none">{thumb}<span>{label}</span></li>')
    return f'<ul style="padding-left:0;margin:0">{"".join(out)}</ul>' if out else ""


def page_sweeps_details(s, complete, missing, saved=""):
    """Sweepstakes Details editor -- sponsor, mail-in AMOE address,
    entry period, and eligibility/winner-selection text.

    The mail-in address block is the highest-risk field on this page:
    an undeliverable address defeats the AMOE and, with it, the entire
    sweepstakes structure. It is called out visually for that reason.
    """
    import sweepstakes as sw
    rid = s["id"]

    def g(k, d=""):
        try:
            return s[k] or d
        except (KeyError, IndexError):
            return d

    def dt_local(v):
        """ISO timestamp -> value for <input type=datetime-local>."""
        d = sw.parse_dt(v)
        return d.strftime("%Y-%m-%dT%H:%M") if d else ""

    warn = ""
    if not complete:
        items = "".join(f"<li>{escape(m)}</li>" for m in missing)
        warn = (f'<div class="cwarn"><b>&#9888; Official Rules incomplete</b>'
                f'<ul>{items}</ul></div>')

    ok = ""
    if saved:
        ok = ('<div style="background:#064e3b;border:1px solid #10b981;'
              'border-radius:6px;padding:12px;margin-bottom:14px;'
              'color:#6ee7b7;font-size:13px">Saved.</div>')

    preview = "<br>".join(escape(l) for l in sw.mail_address_lines(s))

    return shell(f"Sweepstakes Details - {escape(s['name'])}", f'''
<h1>Sweepstakes Details</h1>
<p class="sub">{escape(s['name'])}</p>
{ok}{warn}

<form method="post" action="/admin/{rid}/details">

<div class="card"><h2 style="margin-top:0">Sweepstakes name</h2>
<label>Name (shown on every page and in the Official Rules)</label>
<input name="name" value="{escape(s['name'])}" required>
</div>

<div class="card"><h2 style="margin-top:0">Sponsor</h2>
<p class="sub">The Official Rules must identify who is running the promotion.</p>
<label>Sponsor name</label>
<input name="sponsor_name" value="{escape(g('sponsor_name'))}">
<label>Sponsor address</label>
<input name="sponsor_address" value="{escape(g('sponsor_address'))}">
<label>Sponsor email</label>
<input name="sponsor_email" type="email" value="{escape(g('sponsor_email'))}">
</div>

<div class="card" style="border:2px solid #10b981">
<h2 style="margin-top:0">Free entry (AMOE) mail-in address</h2>
<p class="sub"><b>This is where free entries are physically mailed.</b>
It appears on the free-entry page and in Section 4(a) of the Official Rules.
An address that cannot receive mail invalidates the free entry path.</p>
<label>Addressee / organization line</label>
<input name="mail_name" value="{escape(g('mail_name'))}">
<label>ATTN line</label>
<input name="mail_attn" value="{escape(g('mail_attn', 'Free Entry'))}">
<label>Street address (include suite/unit)</label>
<input name="mail_street" value="{escape(g('mail_street'))}">
<div style="display:flex;gap:10px">
  <div style="flex:2"><label>City</label>
    <input name="mail_city" value="{escape(g('mail_city'))}"></div>
  <div style="flex:1"><label>State</label>
    <input name="mail_state" maxlength="2" value="{escape(g('mail_state'))}"></div>
  <div style="flex:1"><label>ZIP</label>
    <input name="mail_zip" maxlength="10" value="{escape(g('mail_zip'))}"></div>
</div>
<p style="font-size:12px;color:#94a3b8;margin-top:12px">Currently renders as:</p>
<div style="background:#022c22;border:1px dashed #10b981;border-radius:8px;
     padding:14px;font-family:ui-monospace,Menlo,monospace;font-size:13px;
     line-height:1.7;color:#6ee7b7">{preview}</div>
</div>

<div class="card"><h2 style="margin-top:0">Entry period</h2>
<p class="sub">A sweepstakes must have a stated start and end. The mail-in
postmark deadline is derived from the end date.</p>
<label>Entry opens</label>
<input name="start_at" type="datetime-local" value="{dt_local(g('start_at'))}">
<label>Entry closes</label>
<input name="end_at" type="datetime-local" value="{dt_local(g('end_at'))}">
</div>

<div class="card"><h2 style="margin-top:0">Disclosures</h2>
<label>Total prize ARV ($)</label>
<input name="prize_arv_total" type="number" step="0.01" min="0"
       value="{g('prize_arv_total', 0) or 0:.2f}">
<label>Entry limit per household (0 = no limit)</label>
<input name="entry_limit_per_household" type="number" min="0"
       value="{g('entry_limit_per_household', 0) or 0}">
<p style="font-size:12px;color:#94a3b8;margin:-6px 0 14px">
Households are matched on street address when supplied, otherwise on email.
This cap applies <b>equally</b> to donated and mail-in entries &mdash; a limit
that bound only free entrants would invalidate the AMOE.</p>
<label>Eligibility</label>
<textarea name="eligibility_text" rows="4" style="width:100%;padding:10px;
  border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;
  font-family:inherit;font-size:14px">{escape(g('eligibility_text'))}</textarea>
<label>Winner selection method</label>
<textarea name="winner_selection_text" rows="4" style="width:100%;padding:10px;
  border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;
  font-family:inherit;font-size:14px">{escape(g('winner_selection_text'))}</textarea>
</div>

<div class="card">
<button type="submit" class="ok">Save Details</button>
<a href="/admin/{rid}" class="btn">Back to admin</a>
<a href="/rules/{rid}" class="btn">Preview Official Rules</a>
</div>
</form>
''')


def page_admin_login(next_url="/admin/6", error=""):
    """Admin login form.

    Password is verified server-side against ADMIN_PASSWORD. The form does not
    reveal whether auth is configured; main.py returns 503 before rendering if
    secrets are missing.
    """
    err = ""
    if error:
        err = (f'<div class="cwarn"><b>{escape(error)}</b></div>')
    next_url = next_url if str(next_url).startswith("/admin") else "/admin/6"
    return shell("Admin Login", f'''
<h1>Admin Login</h1>
<p class="sub">Protected console for payments, mail-in entries, prizes, and drawing.</p>
{err}
<div class="card" style="max-width:520px">
<form method="post" action="/admin/login">
<input type="hidden" name="next" value="{escape(next_url)}">
<label>Admin password</label>
<input name="password" type="password" required autofocus autocomplete="current-password">
<button type="submit" class="ok">Log in</button>
</form>
</div>
<p style="font-size:12px;color:#94a3b8">Sessions expire automatically. Use logout on shared computers.</p>
''')
