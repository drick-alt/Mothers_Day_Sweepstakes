"""
Email receipts for the raffle app.

DELIVERY BACKENDS
-----------------
  smtp      -- standard SMTP, configured via env vars
  himalaya  -- shells out to the himalaya CLI (already configured on this box)
  preview   -- writes the .eml to disk and sends nothing (DEFAULT)

Default is 'preview' so the app can never accidentally email real buyers
during testing. Set RAFFLE_MAIL_BACKEND to switch.

WHY BOTH TEXT AND HTML
----------------------
Every message is multipart/alternative. Plain text matters here: a raffle
receipt's most important payload is the lookup code and ticket numbers, and
those must survive an email client that blocks HTML or images.
"""

import os
import re
import subprocess
import smtplib
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from datetime import datetime, timezone

BACKEND = os.environ.get("RAFFLE_MAIL_BACKEND", "preview")
FROM_ADDR = os.environ.get("RAFFLE_MAIL_FROM", "raffle@example.com")
FROM_NAME = os.environ.get("RAFFLE_MAIL_FROM_NAME", "Raffle Organizer")
BASE_URL = os.environ.get("RAFFLE_BASE_URL", "http://localhost:8901")
REPLY_TO = os.environ.get("RAFFLE_MAIL_REPLY_TO", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

PREVIEW_DIR = Path(__file__).parent / "outbox"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(addr):
    return bool(addr) and bool(_EMAIL_RE.match(addr.strip()))


# --------------------------------------------------------------------------
# Message bodies
# --------------------------------------------------------------------------

def _ticket_block_text(nums, per_line=6):
    out, row = [], []
    for n in nums:
        row.append(n)
        if len(row) == per_line:
            out.append("   " + "  ".join(row))
            row = []
    if row:
        out.append("   " + "  ".join(row))
    return "\n".join(out)


def build_receipt(order, odds=None):
    """Purchase receipt. Returns (subject, text, html)."""
    is_comp = order["payment_method"] == "comp"
    is_pending = order["payment_status"] == "pending"
    nums = [t["ticket_number"] for t in order.get("ticket_rows", [])] \
        or order.get("ticket_numbers", [])
    qty = order["quantity"]
    link = f"{BASE_URL}/receipt/{order['lookup_code']}"

    if is_comp:
        subject = f"Your free raffle ticket{'s' if qty != 1 else ''} - {order['raffle_name']}"
        headline = f"You received {qty} free ticket{'s' if qty != 1 else ''}!"
    elif is_pending:
        subject = f"Action needed: complete your payment - {order['raffle_name']}"
        headline = "Almost there - we need your payment"
    else:
        subject = f"Your raffle tickets - {order['raffle_name']}"
        headline = f"You're in! {qty} ticket{'s' if qty != 1 else ''} confirmed"

    # ---------------- plain text ----------------
    L = []
    L.append(headline)
    L.append("=" * len(headline))
    L.append("")
    L.append(f"Raffle:  {order['raffle_name']}")
    L.append(f"Name:    {order['buyer_name']}")
    L.append(f"Tickets: {qty}")
    if is_comp:
        L.append("Amount:  FREE - complimentary ticket (no purchase necessary)")
    else:
        L.append(f"Amount:  ${order['amount_paid']:,.2f}")
        L.append(f"Method:  {order['payment_method']}")
    L.append(f"Receipt: {order['receipt_id']}")
    L.append("")

    if is_pending:
        L.append("*** YOUR TICKETS ARE NOT ACTIVE YET ***")
        L.append("")
        L.append(f"Send ${order['amount_paid']:,.2f} and include this code in the memo:")
        L.append("")
        L.append(f"    MEMO CODE:  {order['memo_code']}")
        L.append("")
        L.append("Your ticket numbers are reserved, but they do not enter the")
        L.append("drawing until the organizer confirms your payment.")
        L.append("")

    L.append("YOUR TICKET NUMBERS")
    L.append("-" * 40)
    L.append(_ticket_block_text(nums))
    L.append("")
    L.append("CHECK YOUR TICKETS ANYTIME")
    L.append("-" * 40)
    L.append(f"Lookup code:  {order['lookup_code']}")
    L.append(f"Link:         {link}")
    L.append("")
    L.append("Save this code. It's how you check your odds and see if you won.")
    L.append("")

    if odds and not is_pending:
        L.append("YOUR CURRENT ODDS")
        L.append("-" * 40)
        L.append(f"Chance to win at least one prize:  {odds['at_least_one'] * 100:.2f}%")
        L.append(f"Expected prizes:                   {odds['expected_prizes']:.3f}")
        L.append("")
        L.append("Odds change as more tickets sell. Check your link for live numbers.")
        L.append("")

    L.append("-" * 40)
    L.append(FROM_NAME)
    text = "\n".join(L)

    # ---------------- html ----------------
    # EMAIL-SAFE RULES APPLIED HERE:
    #  * TABLE layout, not divs -- Outlook uses the Word renderer and
    #    ignores div-based/flex layout entirely
    #  * LIGHT theme -- Gmail strips <body> background styling, so a dark
    #    design collapses to dark-text-on-white and becomes unreadable
    #  * inline styles only, no <style> block (Gmail strips <head>)
    #  * bgcolor attributes alongside CSS for older clients
    #  * 600px fixed width -- safe maximum across clients
    #  * no gradients, no web fonts, no background images

    chips = ""
    for i, n in enumerate(nums):
        if i % 4 == 0 and i > 0:
            chips += "</tr><tr>"
        chips += (f'<td width="25%" style="padding:3px">'
                  f'<div style="font-family:Consolas,Monaco,monospace;'
                  f'font-size:13px;background:#f1f5f9;color:#0f172a;'
                  f'border:1px solid #cbd5e1;border-radius:5px;'
                  f'padding:8px 4px;text-align:center">{n}</div></td>')
    pad = len(nums) % 4
    if pad:
        chips += '<td width="25%"></td>' * (4 - pad)

    accent = "#7c3aed" if is_comp else ("#d97706" if is_pending else "#059669")

    pending_html = ""
    if is_pending:
        pending_html = f"""
  <tr><td style="padding:0 28px 20px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0" bgcolor="#fffbeb"
      style="background:#fffbeb;border:1px solid #fbbf24;border-radius:8px">
      <tr><td style="padding:18px">
        <div style="font-family:Arial,sans-serif;font-size:13px;
          font-weight:bold;color:#92400e;letter-spacing:.5px">
          YOUR TICKETS ARE NOT ACTIVE YET</div>
        <div style="font-family:Arial,sans-serif;font-size:14px;
          color:#92400e;padding:10px 0 12px">
          Send <b>${order['amount_paid']:,.2f}</b> and put this code in the memo:</div>
        <div style="font-family:Consolas,Monaco,monospace;font-size:19px;
          font-weight:bold;color:#92400e;background:#ffffff;
          border:2px solid #fbbf24;border-radius:6px;padding:11px 16px;
          display:inline-block">{order['memo_code']}</div>
        <div style="font-family:Arial,sans-serif;font-size:12px;
          color:#a16207;padding-top:12px;line-height:1.5">
          Your numbers are reserved, but they do not enter the drawing
          until the organizer confirms payment.</div>
      </td></tr>
    </table>
  </td></tr>"""

    odds_html = ""
    if odds and not is_pending:
        odds_html = f"""
  <tr><td style="padding:0 28px 20px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0" bgcolor="#ecfdf5"
      style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px">
      <tr><td align="center" style="padding:22px">
        <div style="font-family:Arial,sans-serif;font-size:11px;
          letter-spacing:1.5px;color:#047857;font-weight:bold">
          YOUR CHANCE TO WIN</div>
        <div style="font-family:Arial,sans-serif;font-size:44px;
          font-weight:bold;color:#059669;padding:8px 0 4px;line-height:1">
          {odds['at_least_one'] * 100:.1f}%</div>
        <div style="font-family:Arial,sans-serif;font-size:14px;color:#047857">
          to win at least one prize</div>
        <div style="font-family:Arial,sans-serif;font-size:12px;
          color:#059669;padding-top:10px">
          Expected prizes: {odds['expected_prizes']:.2f}</div>
      </td></tr>
    </table>
  </td></tr>"""

    comp_html = ""
    if is_comp:
        comp_html = """
  <tr><td style="padding:0 28px 20px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0" bgcolor="#f5f3ff"
      style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:8px">
      <tr><td align="center" style="padding:18px">
        <div style="font-family:Arial,sans-serif;font-size:11px;
          letter-spacing:2px;color:#6d28d9;font-weight:bold">
          FREE GIVEAWAY TICKET</div>
        <div style="font-family:Arial,sans-serif;font-size:14px;
          color:#5b21b6;padding-top:6px">
          Value $0.00 &middot; No purchase necessary</div>
      </td></tr>
    </table>
  </td></tr>"""

    amount_row = "FREE" if is_comp else f"${order['amount_paid']:,.2f}"
    method_row = ""
    if not is_comp:
        method_row = f"""
      <tr><td style="font-family:Arial,sans-serif;font-size:14px;
        color:#64748b;padding:7px 0;border-bottom:1px solid #f1f5f9">Method</td>
        <td align="right" style="font-family:Arial,sans-serif;font-size:14px;
        color:#0f172a;padding:7px 0;border-bottom:1px solid #f1f5f9">
        {order['payment_method']}</td></tr>"""

    plural = "S" if qty != 1 else ""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#f1f5f9" bgcolor="#f1f5f9">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  border="0" bgcolor="#f1f5f9" style="background:#f1f5f9;padding:24px 12px">
<tr><td align="center">

<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
  bgcolor="#ffffff" style="width:600px;max-width:600px;background:#ffffff;
  border-radius:12px;overflow:hidden">

  <tr><td bgcolor="{accent}" style="background:{accent};padding:30px 28px">
    <div style="font-family:Arial,sans-serif;font-size:23px;font-weight:bold;
      color:#ffffff;line-height:1.3">{headline}</div>
    <div style="font-family:Arial,sans-serif;font-size:14px;
      color:#ffffff;padding-top:6px">{order['raffle_name']}</div>
  </td></tr>

  {comp_html}{pending_html}

  <tr><td style="padding:24px 28px 20px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#64748b;
        padding:7px 0;border-bottom:1px solid #f1f5f9">Name</td>
        <td align="right" style="font-family:Arial,sans-serif;font-size:14px;
        color:#0f172a;font-weight:bold;padding:7px 0;
        border-bottom:1px solid #f1f5f9">{order['buyer_name']}</td></tr>
      <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#64748b;
        padding:7px 0;border-bottom:1px solid #f1f5f9">Tickets</td>
        <td align="right" style="font-family:Arial,sans-serif;font-size:14px;
        color:#0f172a;font-weight:bold;padding:7px 0;
        border-bottom:1px solid #f1f5f9">{qty}</td></tr>
      <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#64748b;
        padding:7px 0;border-bottom:1px solid #f1f5f9">Amount</td>
        <td align="right" style="font-family:Arial,sans-serif;font-size:14px;
        color:#0f172a;font-weight:bold;padding:7px 0;
        border-bottom:1px solid #f1f5f9">{amount_row}</td></tr>
      {method_row}
      <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#64748b;
        padding:7px 0">Receipt</td>
        <td align="right" style="font-family:Consolas,Monaco,monospace;
        font-size:12px;color:#64748b;padding:7px 0">{order['receipt_id']}</td></tr>
    </table>
  </td></tr>

  {odds_html}

  <tr><td style="padding:0 28px 20px">
    <div style="font-family:Arial,sans-serif;font-size:12px;font-weight:bold;
      letter-spacing:1px;color:#64748b;padding-bottom:10px">
      YOUR TICKET NUMBER{plural}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0"><tr>{chips}</tr></table>
  </td></tr>

  <tr><td style="padding:0 28px 24px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0" bgcolor="#f8fafc"
      style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
      <tr><td align="center" style="padding:22px">
        <div style="font-family:Arial,sans-serif;font-size:12px;color:#64748b;
          padding-bottom:10px">Save this code to check your tickets anytime</div>
        <div style="font-family:Consolas,Monaco,monospace;font-size:26px;
          font-weight:bold;letter-spacing:4px;color:#0f172a;background:#ffffff;
          border:2px solid #cbd5e1;border-radius:8px;padding:13px 22px;
          display:inline-block">{order['lookup_code']}</div>
        <div style="padding-top:18px">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"
            align="center"><tr>
            <td bgcolor="#2563eb" style="background:#2563eb;border-radius:8px">
              <a href="{link}" target="_blank"
                style="display:inline-block;font-family:Arial,sans-serif;
                font-size:15px;font-weight:bold;color:#ffffff;
                text-decoration:none;padding:14px 32px">View My Tickets</a>
            </td></tr></table>
        </div>
      </td></tr>
    </table>
  </td></tr>

  <tr><td bgcolor="#f8fafc" style="background:#f8fafc;padding:20px 28px;
    border-top:1px solid #e2e8f0">
    <div style="font-family:Arial,sans-serif;font-size:12px;color:#94a3b8;
      text-align:center;line-height:1.6">{FROM_NAME}<br>
      <span style="color:#cbd5e1">If you didn't request this, ignore this email.</span>
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""

    return subject, text, html


def build_winner_notice(order, wins, raffle_name):
    """Sent to a buyer who won. wins = [{prize_name, ticket_number}]."""
    subject = f"You won! - {raffle_name}"
    L = ["YOU WON!", "========", "",
         f"Raffle: {raffle_name}", f"Name:   {order['buyer_name']}", ""]
    for w in wins:
        L.append(f"  {w['prize_name']}  (ticket {w['ticket_number']})")
    L.append("")
    L.append("The organizer will contact you about claiming your prize.")
    L.append("")
    L.append(f"Your tickets: {BASE_URL}/receipt/{order['lookup_code']}")
    text = "\n".join(L)

    rows = "".join(
        f'<tr><td style="padding:8px;color:#fff;font-weight:600">{w["prize_name"]}</td>'
        f'<td style="padding:8px;font-family:monospace;color:#9aa3b2;'
        f'text-align:right">{w["ticket_number"]}</td></tr>' for w in wins)

    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:24px;
background:#0f1117;font-family:-apple-system,sans-serif">
  <div style="max-width:560px;margin:0 auto">
    <div style="background:linear-gradient(135deg,#064e3b,#059669);
      border-radius:12px;padding:28px;text-align:center;margin-bottom:18px">
      <div style="color:#a7f3d0;font-size:13px;text-transform:uppercase;
        letter-spacing:2px">Congratulations</div>
      <div style="color:#fff;font-size:34px;font-weight:800;margin:8px 0">
        You Won!</div>
      <div style="color:#d1fae5;font-size:15px">{raffle_name}</div>
    </div>
    <div style="background:#171a23;border:1px solid #262b38;border-radius:10px;
      padding:18px;margin-bottom:18px">
      <table style="width:100%;border-collapse:collapse">{rows}</table>
    </div>
    <p style="color:#9aa3b2;font-size:14px;text-align:center">
      The organizer will contact you about claiming your prize.</p>
    <p style="text-align:center;margin-top:18px">
      <a href="{BASE_URL}/receipt/{order['lookup_code']}"
        style="display:inline-block;background:#2563eb;color:#fff;
        text-decoration:none;padding:12px 22px;border-radius:8px;
        font-weight:600">View my tickets</a></p>
  </div>
</body></html>"""
    return subject, text, html


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------

def _compose(to_addr, subject, text, html):
    msg = EmailMessage()
    msg["From"] = f"{FROM_NAME} <{FROM_ADDR}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    # Date and Message-ID are REQUIRED for good deliverability. Gmail and
    # Outlook penalize or silently drop mail that lacks them -- this is the
    # single most common reason a "successfully sent" message never arrives.
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    domain = FROM_ADDR.split("@")[-1] if "@" in FROM_ADDR else "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    if REPLY_TO:
        msg["Reply-To"] = REPLY_TO
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send(to_addr, subject, text, html):
    """Deliver a message. Returns a dict describing what happened.

    Never raises on delivery failure -- a broken mail server must not break
    a ticket purchase. Failures are reported in the return value.
    """
    if not valid_email(to_addr):
        return {"sent": False, "backend": BACKEND, "reason": "invalid or missing email"}

    msg = _compose(to_addr, subject, text, html)

    try:
        if BACKEND == "preview":
            PREVIEW_DIR.mkdir(exist_ok=True)
            stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
            safe = re.sub(r"[^a-zA-Z0-9]", "_", to_addr)[:40]
            path = PREVIEW_DIR / f"{stamp}_{safe}.eml"
            path.write_bytes(bytes(msg))
            return {"sent": True, "backend": "preview", "path": str(path)}

        if BACKEND == "himalaya":
            # CRITICAL: use `message send`, NOT `template send`.
            #
            # `template send` expects himalaya's MML template syntax. Feeding
            # it a fully-formed MIME message makes himalaya treat the whole
            # thing as a template BODY and re-wrap it -- the HTML part arrives
            # as an unnamed "noname" attachment instead of rendering inline.
            #
            # `message send` takes raw RFC-5322 MIME and transmits it as-is.
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tf:
                tf.write(bytes(msg))
                tmp = tf.name
            try:
                with open(tmp, "rb") as raw:
                    p = subprocess.run(["himalaya", "message", "send"],
                                       stdin=raw, capture_output=True,
                                       timeout=90, check=False)
                if p.returncode != 0:
                    return {"sent": False, "backend": "himalaya",
                            "reason": (p.stderr or p.stdout).decode()[:300]}
                return {"sent": True, "backend": "himalaya", "to": to_addr}
            finally:
                os.unlink(tmp)

        if BACKEND == "smtp":
            if not SMTP_HOST:
                return {"sent": False, "backend": "smtp", "reason": "SMTP_HOST not set"}
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.starttls()
                if SMTP_USER:
                    s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
            return {"sent": True, "backend": "smtp"}

        return {"sent": False, "backend": BACKEND, "reason": "unknown backend"}

    except Exception as e:
        return {"sent": False, "backend": BACKEND, "reason": f"{type(e).__name__}: {e}"}


def send_receipt(order, odds=None):
    subject, text, html = build_receipt(order, odds)
    return send(order.get("buyer_email"), subject, text, html)


def send_winner_notice(order, wins, raffle_name):
    subject, text, html = build_winner_notice(order, wins, raffle_name)
    return send(order.get("buyer_email"), subject, text, html)
