# Security Audit — Mother's Day Sweepstakes App

Date: 2026-09-10
Target: https://mothers-day-sweepstakes.onrender.com
Repo: https://github.com/drick-alt/Mothers_Day_Sweepstakes

## Executive Summary

This was an authorized OWASP-style application security pass focused on whether
an unauthenticated user could manipulate the sweepstakes, tickets, revenue, odds,
or administrative controls.

One critical issue was reproduced and fixed:

- **CRITICAL — public mock payment gateway was enabled whenever Stripe was not
  configured.** A public user could create a card order and call
  `/mock-pay/{code}/complete`, making tickets active and increasing revenue/stats
  without paying. This was reproduced safely against a disposable local DB, then
  fixed and verified on Render.

Two additional hardening changes were applied:

- Public aggregate statistics are now admin-only.
- Security headers, Secure admin cookies, and admin login throttling were added.

Current live state after remediation:

```text
mock_mode: False
card/apple_pay/google_pay/cashapp/venmo ready: False until real provider keys exist
zelle/cash ready: True manual confirmation only
public /api/raffle/6/stats: 401 Admin login required
crafted card buy without Stripe keys: 503 That payment method is not configured yet
/mock-pay/FAKE: 404
/mock-pay/FAKE/complete: 400 mock gateway disabled
admin stats with cookie: 200
```

## Verification Performed

### Static / dependency checks

```text
py_compile main.py db.py payments.py views.py sweepstakes.py mailer.py seed_data.py
imports OK
pip-audit -r requirements.txt: No known vulnerabilities found
bandit: High findings reduced from 1 to 0
```

Dependency fix:

```text
python-multipart 0.0.29 -> 0.0.31
```

### Regression tests

```text
test_odds.py           PASS
test_payments.py       38 passed, 0 failed
test_giveaway.py       28 passed, 0 failed
test_sweepstakes.py    105 passed, 0 failed
```

### Live Render checks after remediation

```text
content-security-policy: default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'
referrer-policy: same-origin
strict-transport-security: max-age=31536000; includeSubDomains
x-content-type-options: nosniff
x-frame-options: DENY

mock_mode: False
{'card': False, 'apple_pay': False, 'google_pay': False, 'cashapp': False, 'venmo': False, 'zelle': True, 'cash': True}

public stats: 401 {"detail":"Admin login required"}
card buy: 503 {"detail":"That payment method is not configured yet"}
mock GET: 404 {"detail":"Not found"}
mock POST: 400 {"detail":"mock gateway disabled"}
set-cookie: sweeps_admin=***; HttpOnly; Max-Age=28800; Path=/; SameSite=lax; Secure
admin stats with cookie: 200
```

## Findings and Remediation

### CRITICAL — Mock payment gateway allowed unpaid ticket activation

**Status:** Fixed and verified live.

**Affected routes:**

```text
POST /buy
GET /mock-pay/{code}
POST /mock-pay/{code}/complete
```

**Before fix:**

The app used:

```python
MOCK_MODE = not bool(STRIPE_SECRET_KEY)
```

Because Render had no Stripe key yet, the public internet was in mock mode.

**Safe reproduction against disposable local DB:**

```text
METHODS 200 mock_mode True
BUY_CARD 303 /mock-pay/243ZSZB7?session=cs_mock_...&method=card
MOCK_COMPLETE 303 /paid/243ZSZB7
STATS_AFTER tickets_sold=1 revenue=10.0
DB state: 243ZSZB7|paid|card|10.0|1|active|active
```

**Impact:**

A public user could create apparently paid/active tickets without a real payment,
which directly manipulates:

- active entry pool
- revenue
- odds
- winner eligibility

**Fix:**

Mock gateway is now opt-in only:

```python
MOCK_MODE = os.environ.get("ALLOW_MOCK_PAYMENTS") == "1"
```

Server-side readiness is enforced in `/buy`:

```python
if not payments.method_ready(payment_method):
    raise HTTPException(503, "That payment method is not configured yet")
```

Mock gateway routes fail closed unless explicitly enabled.

### HIGH — Public aggregate stats endpoint exposed revenue/ticket/buyer totals

**Status:** Fixed and verified live.

**Affected route:**

```text
GET /api/raffle/{rid}/stats
```

**Impact:**

Exposed business aggregates that should be admin-only:

- tickets sold
- tickets pending
- revenue
- pending revenue
- buyer count

**Fix:**

`/api/raffle/*` is now protected by the admin session middleware. Public
`/api/odds` and `/api/methods` remain accessible.

Live verification:

```text
public stats: 401 {"detail":"Admin login required"}
admin stats with cookie: 200
```

### MEDIUM — Admin cookie missing Secure flag

**Status:** Fixed and verified live.

Admin session cookies now use:

```text
HttpOnly; SameSite=lax; Secure
```

`ADMIN_COOKIE_SECURE=0` may be used for local HTTP-only development; production
should keep the default secure behavior.

### MEDIUM — Missing browser security headers

**Status:** Fixed and verified live.

Added:

```text
Content-Security-Policy
Strict-Transport-Security
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
```

### MEDIUM — Dependency with known vulnerabilities

**Status:** Fixed.

```text
python-multipart==0.0.29 -> python-multipart==0.0.31
pip-audit: No known vulnerabilities found
```

### MEDIUM — shell=True in Himalaya mail backend

**Status:** Fixed.

Replaced shell redirection:

```python
subprocess.run(f"himalaya message send < {tmp}", shell=True, ...)
```

with argument-based execution and stdin:

```python
subprocess.run(["himalaya", "message", "send"], stdin=raw, ...)
```

Bandit high findings went from 1 to 0.

### LOW / Remaining Hygiene — Bandit false positives / acceptable risks

Remaining Bandit findings are mostly controlled dynamic SQL where column/table
names are selected from hardcoded allowlists, PayPal URL calls to hardcoded
HTTPS API base, test-only random usage, and intentional mail-failure isolation.
They should be documented or marked `# nosec` only after a second review.

## What Is Genuinely Good

- Payment confirmation is idempotent; duplicate webhook confirmations do not
  double-activate tickets.
- Pending tickets do not affect odds or drawing eligibility.
- Admin-only comp/giveaway route is not available through the public `/buy` path.
- Prize URLs and images are scheme-sanitized; `javascript:` and `data:` payloads
  are rejected by tests.
- Stripe webhook signature verification rejects forged/tampered payloads in tests.
- Admin routes are centrally protected by middleware, so future `/admin/*` routes
  fail closed by default.

## Remaining Work Before Trusting Real Money

1. Replace the temporary admin password in Render.
2. Add real Stripe credentials and webhook secret.
3. Verify real Stripe checkout with a test-mode key first, then live key.
4. Run an authenticated DAST pass with OWASP ZAP against a staging copy.
5. Add CI to run unit tests, pip-audit, and Bandit on every push.
6. Add backup/restore procedure for `/data/raffle.db`.
7. Consider moving from SQLite to managed Postgres before higher-volume public launch.
8. Have counsel review sweepstakes rules, AMOE language, and donation wording.

## Current Go/No-Go

Do not take real online payments yet because Stripe keys are not configured.
Manual Zelle/cash flows are still possible, but require disciplined admin
confirmation and operational controls.

After Stripe test-mode verification and admin password rotation, the app will be
in a much safer state for a limited $3,000-value campaign.
