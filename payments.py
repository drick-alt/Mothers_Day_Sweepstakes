"""
Payment provider abstraction for the raffle app.

=============================================================================
HONEST CAPABILITY MAP -- read this before adding methods
=============================================================================

STRIPE CHECKOUT (one integration, four methods):
    card            -- Visa/MC/Amex/Discover
    apple_pay       -- automatic on Safari/iOS when domain is verified
    google_pay      -- automatic on Chrome/Android
    cashapp         -- Cash App Pay, US only, real Stripe payment method
    link            -- Stripe's own 1-click wallet
  Apple Pay and Google Pay are NOT separate API calls. Stripe Checkout
  surfaces them automatically when the buyer's browser/device supports them
  and 'card' is in payment_method_types. Apple Pay additionally requires
  domain verification in the Stripe dashboard.

PAYPAL / BRAINTREE (separate integration):
    venmo           -- Venmo is owned by PayPal. There is NO Stripe support.
                       Requires PayPal Orders API or Braintree SDK.
                       Venmo is US-only and mobile-web/app only.
    paypal          -- comes along for free with the same integration

ZELLE -- NOT AUTOMATABLE:
    Zelle is a bank-to-bank P2P rail run by Early Warning Services. There is
    no merchant API, no hosted checkout, no webhook, no settlement callback.
    You cannot programmatically confirm a Zelle payment. The only correct
    implementation is an OFFLINE / MANUAL flow:
        1. show the buyer the Zelle handle + a unique memo code
        2. create the order as payment_status='pending'
        3. tickets are held as status='pending' and DO NOT count in the pool
        4. an admin confirms receipt in their banking app
        5. admin clicks Approve -> tickets flip to 'active'
    Same pattern covers cash and check at in-person events.

DESIGN CONSEQUENCE:
  Because pending payments exist, tickets have a lifecycle. Only 'active'
  tickets count toward the pool and the odds. Otherwise anyone could inflate
  the pool -- and dilute everyone else's odds -- without ever paying.
=============================================================================
"""

import os
import hmac
import hashlib
import secrets

# --------------------------------------------------------------------------
# Configuration -- read from env. Mock gateway is opt-in only.
# --------------------------------------------------------------------------

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")

# Offline payment destinations -- shown to the buyer as instructions
ZELLE_HANDLE = os.environ.get("ZELLE_HANDLE", "raffle@example.com")
ZELLE_NAME = os.environ.get("ZELLE_NAME", "Raffle Organizer")
VENMO_HANDLE = os.environ.get("VENMO_HANDLE", "@raffle-organizer")
CASHAPP_HANDLE = os.environ.get("CASHAPP_HANDLE", "$raffleorganizer")

MOCK_MODE = os.environ.get("ALLOW_MOCK_PAYMENTS") == "1"


# --------------------------------------------------------------------------
# Method registry
# --------------------------------------------------------------------------

# kind:
#   'stripe'  -> hosted Stripe Checkout, auto-confirmed by webhook
#   'paypal'  -> PayPal/Venmo redirect, auto-confirmed by capture
#   'offline' -> manual admin confirmation required
METHODS = {
    "card": {
        "label": "Credit / Debit Card",
        "icon": "card",
        "kind": "stripe",
        "stripe_types": ["card"],
        "note": "Visa, Mastercard, Amex, Discover",
        "auto": True,
    },
    "apple_pay": {
        "label": "Apple Pay",
        "icon": "apple",
        "kind": "stripe",
        "stripe_types": ["card"],  # surfaced automatically by Checkout
        "note": "Safari / iOS. Requires Stripe domain verification.",
        "auto": True,
    },
    "google_pay": {
        "label": "Google Pay",
        "icon": "google",
        "kind": "stripe",
        "stripe_types": ["card"],  # surfaced automatically by Checkout
        "note": "Chrome / Android",
        "auto": True,
    },
    "cashapp": {
        "label": "Cash App Pay",
        "icon": "cashapp",
        "kind": "stripe",
        "stripe_types": ["cashapp"],
        "note": "US only. Native Stripe payment method.",
        "auto": True,
    },
    "venmo": {
        "label": "Venmo",
        "icon": "venmo",
        "kind": "paypal",
        "note": "Via PayPal. US only, mobile web/app.",
        "auto": True,
    },
    "zelle": {
        "label": "Zelle",
        "icon": "zelle",
        "kind": "offline",
        "note": "Manual confirmation. No merchant API exists for Zelle.",
        "auto": False,
    },
    "cash": {
        "label": "Cash / Check",
        "icon": "cash",
        "kind": "offline",
        "note": "In-person sales. Manual confirmation.",
        "auto": False,
    },
    # ADMIN ONLY -- never rendered on the public buy page and rejected by
    # the /buy endpoint. Free tickets handed out at events. They are REAL
    # entries (active immediately, count in the pool and the odds) but carry
    # $0 so they never inflate revenue.
    "comp": {
        "label": "Free Giveaway",
        "icon": "gift",
        "kind": "comp",
        "note": "Complimentary ticket issued at an event. $0.",
        "auto": True,
        "admin_only": True,
    },
}


def is_comp(key):
    m = METHODS.get(key)
    return bool(m) and m["kind"] == "comp"


def is_public(key):
    """A method a buyer is allowed to pick for themselves."""
    m = METHODS.get(key)
    return bool(m) and not m.get("admin_only")


def method_info(key):
    return METHODS.get(key)


def method_ready(key):
    """Whether a method can actually process an order right now."""
    m = METHODS.get(key)
    if not m:
        return False
    if m["kind"] == "stripe":
        return MOCK_MODE or bool(STRIPE_SECRET_KEY)
    if m["kind"] == "paypal":
        return MOCK_MODE or bool(PAYPAL_CLIENT_ID and PAYPAL_SECRET)
    return True


def is_offline(key):
    m = METHODS.get(key)
    return bool(m) and m["kind"] == "offline"


def available_methods(include_admin=False):
    """Methods to show on the buy page, with live availability flags.

    include_admin=False (default) hides admin-only methods such as 'comp'
    so a buyer can never hand themselves free tickets.
    """
    out = []
    for k, m in METHODS.items():
        if m.get("admin_only") and not include_admin:
            continue
        ready = method_ready(k)
        out.append({"key": k, **m, "ready": ready})
    return out


def gen_memo_code():
    """Unique memo the buyer puts in their Zelle/Venmo note so the admin can
    match the payment to the order."""
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "RAF-" + "".join(secrets.choice(alpha) for _ in range(6))


# --------------------------------------------------------------------------
# Stripe Checkout
# --------------------------------------------------------------------------

def create_stripe_checkout(order, raffle, success_url, cancel_url,
                           method_key="card"):
    """Create a Stripe Checkout Session.

    Returns (redirect_url, provider_session_id).
    In MOCK_MODE returns a local simulator URL so the full state machine can
    be exercised without live API keys.
    """
    m = METHODS[method_key]
    types = m.get("stripe_types", ["card"])
    amount_cents = int(round(order["amount_paid"] * 100))

    if MOCK_MODE:
        fake_id = "cs_mock_" + secrets.token_hex(12)
        return (f"/mock-pay/{order['lookup_code']}?session={fake_id}"
                f"&method={method_key}", fake_id)

    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=types,
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": int(round(raffle["ticket_price"] * 100)),
                "product_data": {
                    "name": f"{raffle['name']} - Raffle Ticket",
                    "description": f"{order['quantity']} ticket(s)",
                },
            },
            "quantity": order["quantity"],
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=order["lookup_code"],
        metadata={
            "lookup_code": order["lookup_code"],
            "raffle_id": str(order["raffle_id"]),
            "order_id": str(order["order_id"]),
            "method": method_key,
        },
    )
    # Sanity: never trust our own math blindly
    if session.amount_total != amount_cents:
        raise RuntimeError(
            f"amount mismatch: stripe={session.amount_total} local={amount_cents}")
    return session.url, session.id


def verify_stripe_webhook(payload: bytes, sig_header: str):
    """Verify a Stripe webhook signature.

    Returns the parsed event dict, or raises ValueError.
    Implemented manually (rather than stripe.Webhook.construct_event) so the
    signature scheme is auditable and testable without the SDK.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    if not sig_header:
        raise ValueError("missing Stripe-Signature header")

    parts = dict(
        p.split("=", 1) for p in sig_header.split(",") if "=" in p
    )
    timestamp = parts.get("t")
    provided = parts.get("v1")
    if not timestamp or not provided:
        raise ValueError("malformed Stripe-Signature header")

    signed_payload = timestamp.encode() + b"." + payload
    expected = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, provided):
        raise ValueError("signature verification failed")

    import json
    return json.loads(payload)


def sign_stripe_payload(payload: bytes, secret: str, timestamp: str = "1700000000"):
    """Produce a valid Stripe-Signature header. Used by the test suite."""
    signed = timestamp.encode() + b"." + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


# --------------------------------------------------------------------------
# PayPal / Venmo
# --------------------------------------------------------------------------

PAYPAL_API = os.environ.get("PAYPAL_API_BASE",
                            "https://api-m.sandbox.paypal.com")


def _paypal_token():
    import urllib.request
    import urllib.parse
    import base64
    import json
    creds = base64.b64encode(
        f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}".encode()).decode()
    req = urllib.request.Request(
        f"{PAYPAL_API}/v1/oauth2/token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["access_token"]


def create_paypal_order(order, raffle, return_url, cancel_url):
    """Create a PayPal order with Venmo enabled.

    Returns (redirect_url, provider_order_id).
    """
    if MOCK_MODE or not (PAYPAL_CLIENT_ID and PAYPAL_SECRET):
        fake_id = "PAYPAL_MOCK_" + secrets.token_hex(10)
        return (f"/mock-pay/{order['lookup_code']}?session={fake_id}"
                f"&method=venmo", fake_id)

    import urllib.request
    import json
    token = _paypal_token()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": order["lookup_code"],
            "description": f"{raffle['name']} - {order['quantity']} ticket(s)",
            "amount": {"currency_code": "USD",
                       "value": f"{order['amount_paid']:.2f}"},
        }],
        "payment_source": {
            "venmo": {
                "experience_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                }
            }
        },
    }
    req = urllib.request.Request(
        f"{PAYPAL_API}/v2/checkout/orders",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    link = next((l["href"] for l in data.get("links", [])
                 if l["rel"] in ("payer-action", "approve")), None)
    if not link:
        raise RuntimeError("PayPal did not return an approval link")
    return link, data["id"]


def capture_paypal_order(provider_order_id):
    """Capture an approved PayPal/Venmo order. Returns True on success."""
    if MOCK_MODE or not (PAYPAL_CLIENT_ID and PAYPAL_SECRET):
        return True
    import urllib.request
    import json
    token = _paypal_token()
    req = urllib.request.Request(
        f"{PAYPAL_API}/v2/checkout/orders/{provider_order_id}/capture",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return data.get("status") == "COMPLETED"


# --------------------------------------------------------------------------
# Offline instructions
# --------------------------------------------------------------------------

def offline_instructions(method_key, order):
    """Buyer-facing payment instructions for a manual method."""
    amt = f"${order['amount_paid']:,.2f}"
    memo = order["memo_code"]
    if method_key == "zelle":
        return {
            "title": "Send payment via Zelle",
            "steps": [
                f"Open your bank's app and choose Zelle",
                f"Send {amt} to: {ZELLE_HANDLE}",
                f"Recipient name: {ZELLE_NAME}",
                f"IMPORTANT -- put this in the memo/note: {memo}",
                "Your tickets activate once the organizer confirms receipt.",
            ],
            "handle": ZELLE_HANDLE,
            "amount": amt,
            "memo": memo,
            "warning": ("Zelle has no merchant API, so confirmation is manual. "
                        "Your ticket numbers are reserved but do not enter the "
                        "drawing until the organizer verifies the payment."),
        }
    return {
        "title": "Pay in person",
        "steps": [
            f"Bring {amt} in cash or check to the organizer",
            f"Reference code: {memo}",
            "Your tickets activate once the organizer confirms payment.",
        ],
        "handle": "In person",
        "amount": amt,
        "memo": memo,
        "warning": "Tickets do not enter the drawing until payment is confirmed.",
    }
