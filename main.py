"""Raffle Sales App -- FastAPI with multi-method payments."""

import hashlib
import hmac
import os
import time
from urllib.parse import quote

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import (HTMLResponse, RedirectResponse, JSONResponse,
                               PlainTextResponse)
import db
import payments
import mailer
import sweepstakes as sw
from odds import compute_odds, marginal_ticket_value, pct
import views

app = FastAPI(title="Raffle Sales App")
app.mount("/static", StaticFiles(directory="static"), name="static")
db.init_db()


# ---------------------------------------------------------------- admin auth

ADMIN_COOKIE = "sweeps_admin"
ADMIN_SESSION_SECONDS = int(os.environ.get("ADMIN_SESSION_SECONDS", "28800"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_SESSION_SECRET = os.environ.get("ADMIN_SESSION_SECRET", "")
ADMIN_COOKIE_SECURE = os.environ.get("ADMIN_COOKIE_SECURE", "1") != "0"
LOGIN_FAILURES = {}


def _admin_auth_configured():
    return bool(ADMIN_PASSWORD and ADMIN_SESSION_SECRET)


def _sign_session(expiry):
    msg = f"admin:{expiry}".encode()
    return hmac.new(ADMIN_SESSION_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _make_session_cookie():
    expiry = int(time.time()) + ADMIN_SESSION_SECONDS
    return f"admin:{expiry}:{_sign_session(expiry)}"


def _valid_session_cookie(value):
    if not _admin_auth_configured() or not value:
        return False
    try:
        who, expiry_s, sig = value.split(":", 2)
        expiry = int(expiry_s)
    except Exception:
        return False
    if who != "admin" or expiry < int(time.time()):
        return False
    return hmac.compare_digest(sig, _sign_session(expiry))


def _admin_protected_path(path):
    return path.startswith("/admin") or path.startswith("/api/raffle/")


def _client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _login_limited(ip):
    now = time.time()
    failures = [t for t in LOGIN_FAILURES.get(ip, []) if now - t < 900]
    LOGIN_FAILURES[ip] = failures
    return len(failures) >= 8


def _record_login_failure(ip):
    now = time.time()
    failures = [t for t in LOGIN_FAILURES.get(ip, []) if now - t < 900]
    failures.append(now)
    LOGIN_FAILURES[ip] = failures


def _clear_login_failures(ip):
    LOGIN_FAILURES.pop(ip, None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def require_admin_login(request: Request, call_next):
    """Protect every /admin route except login/logout.

    Central middleware is deliberate: new admin routes are protected by
    default. If production secrets are missing, admin fails closed with 503.
    """
    path = request.url.path
    if _admin_protected_path(path) and path not in ("/admin/login", "/admin/logout"):
        if not _admin_auth_configured():
            return PlainTextResponse(
                "Admin authentication is not configured. Set ADMIN_PASSWORD and ADMIN_SESSION_SECRET.",
                status_code=503)
        if not _valid_session_cookie(request.cookies.get(ADMIN_COOKIE, "")):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Admin login required"}, status_code=401)
            if request.method.upper() == "GET":
                return RedirectResponse(f"/admin/login?next={quote(path)}", status_code=303)
            return JSONResponse({"detail": "Admin login required"}, status_code=401)
    return await call_next(request)


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(next: str = "/admin/6"):
    return views.page_admin_login(next)


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(""), next: str = Form("/admin/6")):
    if not _admin_auth_configured():
        raise HTTPException(503, "Admin authentication is not configured")
    ip = _client_ip(request)
    if _login_limited(ip):
        return HTMLResponse(views.page_admin_login(next, "Too many failed attempts. Try again later."), status_code=429)
    if not hmac.compare_digest(password, ADMIN_PASSWORD):
        _record_login_failure(ip)
        return HTMLResponse(views.page_admin_login(next, "Incorrect password"), status_code=401)
    _clear_login_failures(ip)
    if not next.startswith("/admin") or next.startswith("/admin/login"):
        next = "/admin/6"
    resp = RedirectResponse(next, status_code=303)
    resp.set_cookie(
        ADMIN_COOKIE,
        _make_session_cookie(),
        max_age=ADMIN_SESSION_SECONDS,
        httponly=True,
        secure=ADMIN_COOKIE_SECURE,
        samesite="lax",
    )
    return resp


@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


# ---------------------------------------------------------------- public

@app.get("/", response_class=HTMLResponse)
def home():
    return views.page_home(db.list_raffles(), payments.MOCK_MODE)


@app.get("/raffle/{rid}", response_class=HTMLResponse)
def buy_page(rid: int, qty: int = 1):
    raffle = db.get_raffle(rid)
    if not raffle:
        raise HTTPException(404, "Raffle not found")
    qty = max(1, min(qty, 1000))
    # Pool size and revenue are intentionally NOT passed to the buy page --
    # buyers should not see how many tickets are sold or how much was raised.
    # The odds preview still needs the real pool internally.
    total = db.total_tickets(rid)
    preview = compute_odds(total + qty, qty, raffle["num_prizes"])
    return views.page_buy(raffle, qty, preview,
                          payments.available_methods(), payments.MOCK_MODE)


@app.post("/buy")
def buy(raffle_id: int = Form(...), name: str = Form(""),
        email: str = Form(""), phone: str = Form(""),
        address: str = Form(""),
        quantity: int = Form(1), payment_method: str = Form("card")):
    if not name.strip():
        raise HTTPException(400, "Name is required")
    # Email + phone are required on BOTH entry paths so a winner can be
    # contacted. Street address is NOT required here -- donations happen
    # live/online, so there is nothing to mail back.
    if not sw.EMAIL_RE.match(email.strip().lower()):
        raise HTTPException(400, "A valid email address is required")
    ok, msg = sw.validate_phone(phone)
    if not ok:
        raise HTTPException(400, msg)
    if quantity < 1 or quantity > 1000:
        raise HTTPException(400, "Quantity must be between 1 and 1000")
    m = payments.method_info(payment_method)
    if not m:
        raise HTTPException(400, f"Unknown payment method: {payment_method}")
    # SECURITY: 'comp' is admin-only. A buyer must never be able to POST
    # payment_method=comp and hand themselves free tickets.
    if not payments.is_public(payment_method):
        raise HTTPException(403, "That payment method is not available")
    if not payments.method_ready(payment_method):
        raise HTTPException(503, "That payment method is not configured yet")

    raffle = db.get_raffle(raffle_id)
    if not raffle:
        raise HTTPException(404, "Raffle not found")

    # Entry period applies to donated entries exactly as it does to mail-in.
    allowed, period_msg = sw.entry_allowed(raffle)
    if not allowed:
        raise HTTPException(400, period_msg)

    # HOUSEHOLD CAP -- enforced on the DONATED path as well as the mail-in
    # path. Enforcing it on only one side would make that side inferior and
    # break the equal-dignity requirement the sweepstakes depends on.
    try:
        hh_limit = raffle["entry_limit_per_household"] or 0
    except (KeyError, IndexError):
        hh_limit = 0
    if hh_limit:
        held = db.entries_for_household(raffle_id, address, email)
        if held + quantity > hh_limit:
            raise HTTPException(
                400,
                f"Limit {hh_limit} entry(ies) per household. "
                f"This household already holds {held}.")

    memo = payments.gen_memo_code() if m["kind"] == "offline" else None
    try:
        order = db.create_order(raffle_id, name.strip(),
                                email.strip() or None, phone.strip() or None,
                                quantity, payment_method, memo)
    except ValueError as e:
        raise HTTPException(400, str(e))

    code = order["lookup_code"]
    if address.strip():
        db.set_buyer_address(order["buyer_id"], address)

    if m["kind"] == "offline":
        _email_receipt(code)          # pending-payment instructions
        return RedirectResponse(f"/pay/{code}", status_code=303)

    if m["kind"] == "stripe":
        url, ref = payments.create_stripe_checkout(
            order, raffle,
            success_url=f"/paid/{code}",
            cancel_url=f"/cancelled/{code}",
            method_key=payment_method)
    else:  # paypal / venmo
        url, ref = payments.create_paypal_order(
            order, raffle,
            return_url=f"/paid/{code}", cancel_url=f"/cancelled/{code}")

    db.set_provider_ref(code, ref)
    return RedirectResponse(url, status_code=303)


def _email_receipt(code):
    """Send a receipt email. Never let a mail failure break a purchase."""
    try:
        order = db.get_order_by_lookup(code)
        if not order or not order.get("buyer_email"):
            return {"sent": False, "reason": "no email on file"}
        odds = None
        if order["payment_status"] == "paid":
            total = db.total_tickets(order["raffle_id"])
            mine = db.buyer_ticket_count(order["raffle_id"], order["buyer_id"])
            odds = compute_odds(total, mine, order["num_prizes"])
        return mailer.send_receipt(order, odds)
    except Exception as e:
        return {"sent": False, "reason": f"{type(e).__name__}: {e}"}


@app.get("/pay/{code}", response_class=HTMLResponse)
def pay_offline(code: str):
    """Zelle / cash instructions page."""
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Order not found")
    inst = payments.offline_instructions(order["payment_method"], order)
    return views.page_offline_pay(order, inst)


@app.get("/mock-pay/{code}", response_class=HTMLResponse)
def mock_pay(code: str, session: str = "", method: str = "card"):
    """Local simulator standing in for the hosted gateway.

    Disabled by default in deployed environments. Enable only for local demos
    with ALLOW_MOCK_PAYMENTS=1.
    """
    if not payments.MOCK_MODE:
        raise HTTPException(404, "Not found")
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Order not found")
    return views.page_mock_gateway(order, session, method)


@app.post("/mock-pay/{code}/complete")
def mock_complete(code: str):
    if not payments.MOCK_MODE:
        raise HTTPException(400, "mock gateway disabled")
    if db.confirm_payment(code, "mock_" + code, source="mock_gateway"):
        _email_receipt(code)
    return RedirectResponse(f"/paid/{code}", status_code=303)


@app.get("/paid/{code}")
def paid(code: str):
    """Gateway success return. Confirmation still comes from the webhook --
    this just routes the buyer to their receipt."""
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Order not found")
    # PayPal/Venmo capture happens on return, not via webhook
    if order["payment_method"] == "venmo" and order["payment_status"] != "paid":
        if payments.capture_paypal_order(order["provider_ref"]):
            if db.confirm_payment(code, order["provider_ref"],
                                  source="paypal_capture"):
                _email_receipt(code)
    return RedirectResponse(f"/receipt/{code}", status_code=303)


@app.get("/cancelled/{code}", response_class=HTMLResponse)
def cancelled(code: str):
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Order not found")
    if order["payment_status"] == "pending":
        db.cancel_order(code, "abandoned at gateway")
    return views.page_cancelled(order)


@app.post("/webhook/stripe")
async def webhook_stripe(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = payments.verify_stripe_webhook(payload, sig)
    except ValueError as e:
        raise HTTPException(400, f"webhook verification failed: {e}")

    if event.get("type") == "checkout.session.completed":
        obj = event["data"]["object"]
        code = (obj.get("client_reference_id")
                or obj.get("metadata", {}).get("lookup_code"))
        if code:
            if db.confirm_payment(code,
                                  obj.get("payment_intent") or obj.get("id"),
                                  source="stripe_webhook"):
                _email_receipt(code)
    return {"received": True}


@app.get("/receipt/{code}", response_class=HTMLResponse)
def receipt(code: str):
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Receipt not found")
    rid = order["raffle_id"]
    total = db.total_tickets(rid)
    mine = db.buyer_ticket_count(rid, order["buyer_id"])
    p = order["num_prizes"]
    o = compute_odds(total, mine, p)
    marginal = marginal_ticket_value(total, mine, p) if total else 0.0
    inst = (payments.offline_instructions(order["payment_method"], order)
            if order["payment_status"] == "pending"
            and payments.is_offline(order["payment_method"]) else None)
    return views.page_receipt(order, o, marginal, db.get_winners(rid), inst)


@app.get("/lookup", response_class=HTMLResponse)
def lookup(code: str = ""):
    if code:
        if db.get_order_by_lookup(code):
            return RedirectResponse(f"/receipt/{code.strip().upper()}",
                                    status_code=303)
        return views.page_lookup(error="No receipt found for that code.")
    return views.page_lookup()


# ---------------------------------------------------------------- admin

@app.get("/admin/{rid}", response_class=HTMLResponse)
def admin(rid: int):
    raffle = db.get_raffle(rid)
    if not raffle:
        raise HTTPException(404, "Raffle not found")
    total = db.total_tickets(rid)
    board = db.leaderboard(rid)
    for b in board:
        o = compute_odds(total, b["tickets"], raffle["num_prizes"])
        b["odds"] = o["at_least_one"]
        b["expected"] = o["expected_prizes"]
    return views.page_admin(raffle, total, db.pending_tickets(rid),
                            db.revenue(rid), db.pending_revenue(rid), board,
                            db.pending_orders(rid), db.payment_breakdown(rid),
                            db.get_winners(rid), db.comp_stats(rid))


@app.post("/admin/confirm/{code}")
def admin_confirm(code: str):
    try:
        if db.confirm_payment(code, "admin-confirmed", source="admin"):
            _email_receipt(code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    order = db.get_order_by_lookup(code)
    return RedirectResponse(f"/admin/{order['raffle_id']}", status_code=303)


@app.post("/admin/reject/{code}")
def admin_reject(code: str):
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Order not found")
    try:
        db.cancel_order(code, "rejected by admin")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(f"/admin/{order['raffle_id']}", status_code=303)


@app.get("/enter/{rid}", response_class=HTMLResponse)
def free_entry_form(rid: int, err: str = "", ok: str = ""):
    """PUBLIC free-entry page. This is the AMOE -- the legal free path.

    It must be reachable without payment, without an account, and with
    no more friction than the purchase page.
    """
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")
    allowed, period_msg = sw.entry_allowed(s)
    return views.page_free_entry(s, allowed, period_msg, err, ok)


@app.post("/admin/{rid}/prizes")
def admin_update_prizes(rid: int,
                        prize_1: str = Form(""), prize_1_url: str = Form(""),
                        prize_1_img: str = Form(""),
                        prize_2: str = Form(""), prize_2_url: str = Form(""),
                        prize_2_img: str = Form(""),
                        prize_3: str = Form(""), prize_3_url: str = Form(""),
                        prize_3_img: str = Form(""),
                        prize_4: str = Form(""), prize_4_url: str = Form(""),
                        prize_4_img: str = Form(""),
                        prize_arv_total: float = Form(0)):
    """Update prize names, their optional links, and total ARV.

    num_prizes is recomputed from how many prize NAMES are filled in --
    a mismatch between num_prizes and actual prizes would make the odds
    engine compute against prizes that don't exist.

    URLs are sanitised at render time by views.safe_url(); we store what
    the admin typed so they can see and correct it.
    """
    names = [prize_1.strip(), prize_2.strip(), prize_3.strip(), prize_4.strip()]
    urls = [prize_1_url.strip(), prize_2_url.strip(),
            prize_3_url.strip(), prize_4_url.strip()]
    imgs = [prize_1_img.strip(), prize_2_img.strip(),
            prize_3_img.strip(), prize_4_img.strip()]
    n = sum(1 for x in names if x)
    if n < 1:
        raise HTTPException(400, "At least one prize is required")

    conn = db.connect()
    conn.execute(
        """UPDATE raffles SET prize_1=?,prize_2=?,prize_3=?,prize_4=?,
           prize_1_url=?,prize_2_url=?,prize_3_url=?,prize_4_url=?,
           prize_1_img=?,prize_2_img=?,prize_3_img=?,prize_4_img=?,
           num_prizes=?,prize_arv_total=? WHERE id=?""",
        (*[x or None for x in names], *urls, *imgs, n, prize_arv_total, rid))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/admin/{rid}", status_code=303)


@app.post("/admin/{rid}/mailin")
def admin_record_mailin(rid: int, name: str = Form(""), email: str = Form(""),
                        phone: str = Form(""), address: str = Form(""),
                        postmark: str = Form("")):
    """Record a mail-in free entry that physically arrived.

    The AMOE is MAIL-IN, so entries are created here by an administrator
    opening the mail -- not by a public web form. Everything else about
    the entry is identical to a purchased one: same pool, same odds.

    Postmark date is captured because the Official Rules require the
    entry to be postmarked within the Entry Period.
    """
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")

    def reject(reason, msg):
        db.log_amoe_rejection(rid, name, email, "mail", reason)
        return RedirectResponse(f"/admin/{rid}?err={quote(msg)}", status_code=303)

    # Required on both paths: name, email, phone. Address is optional --
    # keeping the requirements identical on the free and donated paths is
    # what preserves the AMOE.
    valid, msg = sw.validate_amoe(name, email, address, phone,
                                  require_address=False, require_phone=True)
    if not valid:
        return reject("validation failed", msg)

    email_l = email.strip().lower()

    # HOUSEHOLD CAP -- identical rule and identical numbers as the donated
    # path. Address comes off the envelope, so household matching works.
    try:
        hh_limit = s["entry_limit_per_household"] or 0
    except (KeyError, IndexError):
        hh_limit = 0
    if hh_limit:
        held = db.entries_for_household(rid, address, email_l)
        if held >= hh_limit:
            return reject("household limit",
                          f"This household already holds {held} entry(ies) "
                          f"(limit {hh_limit}).")

    # Postmark must fall inside the Entry Period -- the Official Rules
    # say so, and an entry postmarked late is not eligible. We warn rather
    # than hard-block so the admin can still record and adjudicate it.
    warn = ""
    pm = sw.parse_dt(postmark) if postmark else None
    if pm:
        end = sw.parse_dt(s["end_at"])
        start = sw.parse_dt(s["start_at"])
        if end and pm > end:
            warn = " WARNING: postmark is AFTER the entry period closed."
        elif start and pm < start:
            warn = " WARNING: postmark is BEFORE the entry period opened."

    try:
        res = db.amoe_entry(rid, name.strip(), email_l, phone, address,
                            "mail", sw.AMOE_TICKETS_PER_REQUEST,
                            postmark_date=postmark.strip(),
                            recorded_by="admin")
    except ValueError as e:
        return reject("db error", str(e))

    if address.strip():
        db.set_buyer_address(res["buyer_id"], address)

    _email_receipt(res["lookup_code"])
    return RedirectResponse(f"/admin/{rid}/mailin/{res['lookup_code']}?w={quote(warn)}",
                            status_code=303)


@app.get("/admin/{rid}/mailin/{code}", response_class=HTMLResponse)
def mailin_confirmation(rid: int, code: str, w: str = ""):
    """Printable confirmation showing the generated entry code.

    Print this and file it with the physical entry card -- it links the
    mailed-in paper to the ticket numbers in the drawing.
    """
    o = db.get_order_by_lookup(code)
    if not o:
        raise HTTPException(404, "Entry not found")
    total = db.total_tickets(rid)
    mine = db.buyer_ticket_count(rid, o["buyer_id"])
    odds = compute_odds(total, mine, o["num_prizes"])
    return views.page_mailin_confirm(o, odds, w)


@app.get("/admin/{rid}/mailin-log", response_class=HTMLResponse)
def mailin_log_page(rid: int):
    """Full mail-in compliance log."""
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")
    return views.page_mailin_log(s, db.mailin_log(rid), db.amoe_stats(rid))


@app.get("/admin/{rid}/mailin-log.csv", response_class=PlainTextResponse)
def mailin_log_csv(rid: int):
    rows = db.mailin_log(rid)
    out = ["entry_code,receipt_id,name,email,phone,postmark_date,received_date,recorded_at,tickets"]
    for r in rows:
        def q(v):
            v = str(v or "")
            return '"' + v.replace('"', '""') + '"' if "," in v or '"' in v else v
        out.append(",".join(q(r.get(k, "")) for k in
                            ["lookup_code", "receipt_id", "name", "email",
                             "phone", "postmark_date", "received_date",
                             "created_at", "quantity"]))
    return "\n".join(out)


@app.get("/rules/{rid}", response_class=HTMLResponse)
def official_rules(rid: int):
    """Official Rules. Must be publicly reachable and linked from
    every entry surface."""
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")
    prizes = [s[f"prize_{i}"] for i in range(1, 5) if s[f"prize_{i}"]]
    total = db.total_tickets(rid)
    text = sw.build_rules(s, prizes, total)
    complete, missing = sw.rules_completeness(s)
    return views.page_rules(s, text, complete, missing)


@app.get("/rules/{rid}/text", response_class=PlainTextResponse)
def official_rules_text(rid: int):
    """Plain-text Official Rules -- for printing or mailing."""
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")
    prizes = [s[f"prize_{i}"] for i in range(1, 5) if s[f"prize_{i}"]]
    return sw.build_rules(s, prizes, db.total_tickets(rid))


@app.get("/admin/{rid}/details", response_class=HTMLResponse)
def sweeps_details(rid: int, saved: str = ""):
    """Sweepstakes Details editor -- sponsor, mail-in address, dates."""
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")
    complete, missing = sw.rules_completeness(s)
    return views.page_sweeps_details(s, complete, missing, saved)


@app.post("/admin/{rid}/details")
def sweeps_details_save(rid: int,
                        name: str = Form(""),
                        sponsor_name: str = Form(""),
                        sponsor_address: str = Form(""),
                        sponsor_email: str = Form(""),
                        mail_name: str = Form(""),
                        mail_attn: str = Form(""),
                        mail_street: str = Form(""),
                        mail_city: str = Form(""),
                        mail_state: str = Form(""),
                        mail_zip: str = Form(""),
                        start_at: str = Form(""),
                        end_at: str = Form(""),
                        prize_arv_total: float = Form(0),
                        entry_limit_per_household: int = Form(0),
                        eligibility_text: str = Form(""),
                        winner_selection_text: str = Form("")):
    s = db.get_raffle(rid)
    if not s:
        raise HTTPException(404, "Sweepstakes not found")
    if not name.strip():
        raise HTTPException(400, "Sweepstakes name is required")

    # datetime-local posts "YYYY-MM-DDTHH:MM" with no timezone. Treat it as
    # UTC so period comparisons stay consistent with parse_dt().
    def norm(v):
        v = v.strip()
        if not v:
            return None
        return v if ("+" in v or v.endswith("Z")) else v + ":00+00:00"

    db.update_sweepstakes(
        rid,
        name=name.strip(),
        sponsor_name=sponsor_name.strip(),
        sponsor_address=sponsor_address.strip(),
        sponsor_email=sponsor_email.strip(),
        start_at=norm(start_at),
        end_at=norm(end_at),
        prize_arv_total=prize_arv_total,
        entry_limit_per_household=entry_limit_per_household,
        eligibility_text=eligibility_text.strip() or sw.DEFAULT_ELIGIBILITY,
        winner_selection_text=(winner_selection_text.strip()
                               or sw.DEFAULT_WINNER_SELECTION),
    )

    # Mail-in address lives on the raffles row so each sweepstakes can
    # have its own AMOE destination.
    conn = db.connect()
    conn.execute(
        """UPDATE raffles SET mail_name=?,mail_attn=?,mail_street=?,
           mail_city=?,mail_state=?,mail_zip=? WHERE id=?""",
        (mail_name.strip(), mail_attn.strip() or "Free Entry",
         mail_street.strip(), mail_city.strip(),
         mail_state.strip().upper(), mail_zip.strip(), rid))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/admin/{rid}/details?saved=1", status_code=303)


@app.post("/admin/{rid}/giveaway")
def admin_giveaway(rid: int, name: str = Form(""), email: str = Form(""),
                   phone: str = Form(""), quantity: int = Form(1),
                   note: str = Form("")):
    """Issue free giveaway tickets at an event. Admin only."""
    if not name.strip():
        raise HTTPException(400, "Recipient name is required")
    if quantity < 1 or quantity > 1000:
        raise HTTPException(400, "Quantity must be between 1 and 1000")
    try:
        res = db.issue_comp_tickets(rid, name.strip(), email.strip() or None,
                                    phone.strip() or None, quantity,
                                    note.strip() or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _email_receipt(res["lookup_code"])
    return RedirectResponse(f"/giveaway/{res['lookup_code']}", status_code=303)


@app.get("/giveaway/{code}", response_class=HTMLResponse)
def giveaway_slip(code: str):
    """Printable hand-out slip for a giveaway ticket."""
    order = db.get_order_by_lookup(code)
    if not order:
        raise HTTPException(404, "Giveaway not found")
    if order["payment_method"] != "comp":
        return RedirectResponse(f"/receipt/{code}", status_code=303)
    total = db.total_tickets(order["raffle_id"])
    mine = db.buyer_ticket_count(order["raffle_id"], order["buyer_id"])
    o = compute_odds(total, mine, order["num_prizes"])
    return views.page_giveaway_slip(order, o)


@app.get("/admin/{rid}/drum", response_class=HTMLResponse)
def drum(rid: int):
    raffle = db.get_raffle(rid)
    if not raffle:
        raise HTTPException(404, "Raffle not found")
    return views.page_drum(raffle, db.drum_list(rid), db.pending_tickets(rid),
                           db.comp_stats(rid))


@app.get("/admin/{rid}/drum.csv")
def drum_csv(rid: int):
    rows = db.drum_list(rid)
    out = ["ticket_number,buyer_name,phone,email,receipt_id,payment_method,type"]
    for r in rows:
        vals = [r["ticket_number"], r["buyer_name"], r["buyer_phone"] or "",
                r["buyer_email"] or "", r["receipt_id"], r["payment_method"],
                "GIVEAWAY" if r["is_comp"] else "PAID"]
        out.append(",".join('"' + str(v).replace('"', '""') + '"' for v in vals))
    return PlainTextResponse("\n".join(out), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="raffle_{rid}_drum.csv"'})


@app.post("/admin/{rid}/draw")
def draw(rid: int):
    try:
        winners_list = db.draw_winners(rid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Notify each winner (grouped -- one email even if they won twice)
    try:
        raffle = db.get_raffle(rid)
        by_ticket = {}
        for w in winners_list:
            by_ticket.setdefault(w["ticket_number"], []).append(w)
        for tn, wins in by_ticket.items():
            for row in db.drum_list(rid):
                if row["ticket_number"] == tn and row.get("buyer_email"):
                    o = db.get_order_by_lookup_for_receipt(row["receipt_id"])
                    if o:
                        mailer.send_winner_notice(o, wins, raffle["name"])
                    break
    except Exception:
        pass  # a mail failure must never block the draw
    return RedirectResponse(f"/admin/{rid}/winners", status_code=303)


@app.get("/admin/{rid}/winners", response_class=HTMLResponse)
def winners(rid: int):
    raffle = db.get_raffle(rid)
    if not raffle:
        raise HTTPException(404, "Raffle not found")
    return views.page_winners(raffle, db.get_winners(rid))


@app.post("/admin/create")
def create(name: str = Form(...), ticket_price: float = Form(10.0),
           prize_1: str = Form("Prize 1"), prize_2: str = Form("Prize 2"),
           prize_3: str = Form("Prize 3"), prize_4: str = Form("Prize 4")):
    rid = db.create_raffle(name, ticket_price, 4,
                           [prize_1, prize_2, prize_3, prize_4])
    return RedirectResponse(f"/admin/{rid}", status_code=303)


# ---------------------------------------------------------------- API

@app.get("/api/odds")
def api_odds(raffle_id: int, tickets: int):
    raffle = db.get_raffle(raffle_id)
    if not raffle:
        raise HTTPException(404, "Raffle not found")
    total = db.total_tickets(raffle_id)
    o = compute_odds(total + tickets, tickets, raffle["num_prizes"])
    return JSONResponse({
        "if_you_buy": tickets, "pool_would_be": total + tickets,
        "chance_at_least_one_prize": round(o["at_least_one"], 6),
        "chance_pretty": pct(o["at_least_one"]),
        "expected_prizes": round(o["expected_prizes"], 4),
        "per_prize": round(o["per_prize"], 6),
    })


@app.get("/api/raffle/{rid}/stats")
def api_stats(rid: int):
    raffle = db.get_raffle(rid)
    if not raffle:
        raise HTTPException(404, "Raffle not found")
    return {
        "raffle": raffle["name"], "status": raffle["status"],
        "tickets_sold": db.total_tickets(rid),
        "tickets_pending": db.pending_tickets(rid),
        "revenue": db.revenue(rid),
        "revenue_pending": db.pending_revenue(rid),
        "num_prizes": raffle["num_prizes"],
        "buyers": len(db.leaderboard(rid)),
        "tickets_comp": db.comp_stats(rid)["comp"],
        "tickets_purchased": db.comp_stats(rid)["paid"],
    }


@app.get("/api/methods")
def api_methods():
    return {"mock_mode": payments.MOCK_MODE,
            "methods": payments.available_methods()}
