"""
Sweepstakes compliance layer.

=============================================================================
THE LEGAL MODEL -- read this before changing anything in here
=============================================================================

An illegal lottery requires THREE elements simultaneously:

    PRIZE  +  CHANCE  +  CONSIDERATION  =  lottery (regulated / often illegal)

A sweepstakes removes CONSIDERATION. That is the ONLY structural difference.
Everything in this module exists to make the removal of consideration real
rather than cosmetic.

CONSIDERATION IS REMOVED BY THE AMOE
------------------------------------
AMOE = Alternative Method of Entry. A free path to enter that must be:

  1. EQUAL IN DIGNITY   A free entrant's odds must be IDENTICAL to a paying
                        entrant's. Not "a smaller pool". Not "fewer entries".
                        Identical. If free entries are worth less, courts can
                        find consideration survived and you are running an
                        unlicensed lottery.

  2. NOT BURDENSOME     A reasonable person must be able to use it. A web
                        form or a 3x5 mail-in card qualifies. "Watch 20 ads"
                        or "drive to our office during business hours" does
                        not.

  3. CLEARLY DISCLOSED  "NO PURCHASE NECESSARY" must appear before the point
                        of purchase, not buried in a footer.

THE INVARIANT THIS MODULE PROTECTS
----------------------------------
    An AMOE entry and a purchased entry produce the SAME kind of ticket,
    in the SAME pool, with the SAME odds.

We enforce this by making AMOE entries create ordinary active tickets --
the exact same code path as a paid entry, just with amount_paid = 0.

WHAT WE DELIBERATELY DO *NOT* DO
--------------------------------
  * We do NOT give AMOE entrants fewer tickets than a purchase would.
  * We do NOT put AMOE entries in a separate drawing.
  * We do NOT require the AMOE entrant to do more work than a buyer.
  * We do NOT rate-limit AMOE more aggressively than we would purchases.

Rate limiting exists ONLY to stop automated abuse (one bot claiming
100,000 entries), and the per-person entry cap applies EQUALLY to paid
and free entries. An entry cap that binds only free entrants would
destroy equal dignity.

=============================================================================
NOT LEGAL ADVICE. Sweepstakes law is state-specific. Several states impose
registration and bonding above a total ARV threshold (New York and Florida
are the commonly cited $5,000 examples). Georgia has its own treatment of
promotional sweepstakes. Have a licensed attorney in the operating state
review the Official Rules and the AMOE before running this publicly.
=============================================================================
"""

import hashlib
import os
import re
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# MAIL-IN AMOE ADDRESS
# ---------------------------------------------------------------------------
# The free entry path is MAIL-IN. This address appears in the Official Rules
# and on the free-entry page, and is where hand-printed entry cards are sent.
#
# Set via env in production so it can be corrected without a code change.
MAIL_NAME   = os.environ.get("SWEEPS_MAIL_NAME",   "Mother's Day Sweepstakes Drawing")
MAIL_ATTN   = os.environ.get("SWEEPS_MAIL_ATTN",   "Free Entry")
MAIL_STREET = os.environ.get("SWEEPS_MAIL_STREET", "5456 Peachtree Blvd, Suite 134")
MAIL_CITY   = os.environ.get("SWEEPS_MAIL_CITY",   "Atlanta")
MAIL_STATE  = os.environ.get("SWEEPS_MAIL_STATE",  "GA")
MAIL_ZIP    = os.environ.get("SWEEPS_MAIL_ZIP",    "30341")


def _f(rec, key, fallback):
    """Read a field from a sqlite3.Row-ish record, tolerating absence."""
    if rec is None:
        return fallback
    try:
        v = rec[key]
    except (KeyError, IndexError, TypeError):
        return fallback
    return (v or "").strip() or fallback


def mail_address_lines(rec=None):
    """Mail-in address lines.

    Per-sweepstakes values from the DB win; the env-var defaults are the
    fallback so an un-migrated record still renders something sane.

    An undeliverable address here is a DEFECTIVE AMOE -- if free entries
    cannot physically arrive, the free path isn't real and the promotion
    structurally reverts to a lottery. Treat edits to this with care.
    """
    name = _f(rec, "mail_name", MAIL_NAME)
    attn = _f(rec, "mail_attn", MAIL_ATTN)
    street = _f(rec, "mail_street", MAIL_STREET)
    city = _f(rec, "mail_city", MAIL_CITY)
    state = _f(rec, "mail_state", MAIL_STATE)
    zipc = _f(rec, "mail_zip", MAIL_ZIP)
    return [name, f"ATTN: {attn}", street, f"{city}, {state} {zipc}"]


def mail_address_block(rec=None, sep="\n"):
    return sep.join(mail_address_lines(rec))


# What a hand-printed entry card must contain. Keep this SHORT -- a long
# list of required items makes the free path burdensome and weakens the AMOE.
MAIL_REQUIRED_FIELDS = [
    "Your full name",
    "Your complete mailing address",
    "Your email address",
    "Your daytime phone number",
    "Your date of birth",
    'The words "FREE ENTRY REQUEST"',
]

# Salt for IP hashing. We never store raw IPs -- only a salted hash, so the
# abuse-prevention signal exists without retaining PII we don't need.
IP_SALT = os.environ.get("SWEEPS_IP_SALT", "change-me-in-production")

# Anti-abuse thresholds. These are ABUSE controls, not entry restrictions.
# They must never be tighter than what a purchaser faces.
MAX_AMOE_PER_IP_PER_DAY = 10      # one household / office NAT
AMOE_TICKETS_PER_REQUEST = 1      # one free entry per request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def hash_ip(ip: str) -> str:
    """Salted hash of a client IP. We keep the signal, not the PII."""
    if not ip:
        return ""
    return hashlib.sha256(f"{IP_SALT}:{ip}".encode()).hexdigest()[:32]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Entry period
# --------------------------------------------------------------------------

def parse_dt(v):
    """Parse an ISO timestamp, tolerating None/empty and naive values."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError):
        return None


def period_status(sweeps):
    """Where are we relative to the entry period?

    Returns (status, message) where status is one of:
        'not_started' | 'open' | 'ended' | 'undefined'

    A sweepstakes with no defined end date is a compliance defect -- we
    surface it as 'undefined' rather than silently treating it as open.
    """
    start = parse_dt(sweeps.get("start_at"))
    end = parse_dt(sweeps.get("end_at"))
    now = datetime.now(timezone.utc)

    if not end:
        return "undefined", ("No entry period defined. A sweepstakes must "
                             "have a stated start and end date.")
    if start and now < start:
        return "not_started", f"Entry opens {start.strftime('%B %d, %Y at %I:%M %p UTC')}."
    if now > end:
        return "ended", f"Entry closed {end.strftime('%B %d, %Y at %I:%M %p UTC')}."
    return "open", f"Entry closes {end.strftime('%B %d, %Y at %I:%M %p UTC')}."


def entry_allowed(sweeps):
    """True if entries (paid OR free) may be accepted right now.

    Applies identically to both paths -- if purchases are closed, AMOE is
    closed, and vice versa. Divergence here would break equal dignity.
    """
    status, msg = period_status(sweeps)
    if sweeps.get("status") != "open":
        return False, "This sweepstakes is closed."
    if status == "ended":
        return False, msg
    if status == "not_started":
        return False, msg
    return True, msg


# --------------------------------------------------------------------------
# AMOE validation
# --------------------------------------------------------------------------

# A phone number needs at least 10 digits to be a usable US number.
# We count digits rather than pattern-match so (770) 555-1234,
# 770-555-1234, and 7705551234 all pass.
def validate_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 10:
        return False, "Please enter a valid phone number (at least 10 digits)."
    if len(digits) > 15:
        return False, "Phone number is too long."
    return True, ""


def validate_address(address):
    """A mail-in return address must be plausibly mailable.

    Requires a street number and at least two more tokens. This will not
    catch a determined fake -- USPS validation would be needed for that --
    but it stops blanks, single words, and obvious junk.
    """
    a = (address or "").strip()
    if len(a) < 8:
        return False, "Please enter the full return address from the envelope."
    if not re.search(r"\d", a):
        return False, "Return address must include a street number."
    if len(a.split()) < 3:
        return False, "Return address looks incomplete (street, city, state)."
    if len(a) > 300:
        return False, "Address is too long."
    return True, ""


def validate_amoe(name, email, address="", phone="", require_address=False,
                  require_phone=True):
    """Validate a free-entry request.

    REQUIRED on both entry paths: name, email, phone.
    OPTIONAL on both entry paths: street address.

    Address is deliberately optional so the two paths stay symmetric --
    requiring more of a free entrant than of a donor would make the free
    path inferior and erode the AMOE. When an address IS supplied it is
    still used for household matching; when it is absent the household cap
    falls back to the email address.
    """
    name = (name or "").strip()
    email = (email or "").strip().lower()

    if len(name) < 2:
        return False, "Please enter your full name."
    if len(name) > 100:
        return False, "Name is too long."
    if not EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if len(email) > 200:
        return False, "Email is too long."
    if require_phone:
        ok, msg = validate_phone(phone)
        if not ok:
            return False, msg
    if require_address:
        ok, msg = validate_address(address)
        if not ok:
            return False, msg
    return True, ""


# --------------------------------------------------------------------------
# Official Rules
# --------------------------------------------------------------------------

def rules_completeness(sweeps):
    """Check whether the Official Rules have everything they need.

    Returns (ok, missing_list). Used to block publishing a sweepstakes
    that isn't legally presentable, and to show the admin what's missing.
    """
    missing = []
    if not (sweeps.get("sponsor_name") or "").strip():
        missing.append("Sponsor name")
    if not (sweeps.get("sponsor_address") or "").strip():
        missing.append("Sponsor address")
    if not sweeps.get("start_at"):
        missing.append("Entry period start date")
    if not sweeps.get("end_at"):
        missing.append("Entry period end date")
    if not (sweeps.get("prize_arv_total") or 0) > 0:
        missing.append("Total prize ARV (approximate retail value)")
    if not (sweeps.get("eligibility_text") or "").strip():
        missing.append("Eligibility requirements")
    if not (sweeps.get("winner_selection_text") or "").strip():
        missing.append("Winner selection method")
    return (len(missing) == 0), missing


DEFAULT_ELIGIBILITY = (
    "Open only to legal residents of the United States who are 18 years of "
    "age or older at the time of entry. Void where prohibited by law. "
    "Employees of the Sponsor and their immediate family members are not "
    "eligible."
)

DEFAULT_WINNER_SELECTION = (
    "Winners will be selected in a random drawing from among all eligible "
    "entries received during the Entry Period. The drawing will be conducted "
    "using a cryptographically secure random number generator. Odds of "
    "winning depend on the total number of eligible entries received."
)


def build_rules(sweeps, prizes, total_entries=0):
    """Generate Official Rules text from the sweepstakes record.

    Every numbered section below exists because sweepstakes rules are
    expected to disclose it. Removing sections weakens the promotion's
    legal footing.
    """
    start = parse_dt(sweeps.get("start_at"))
    end = parse_dt(sweeps.get("end_at"))
    fmt = "%B %d, %Y at %I:%M %p UTC"
    start_s = start.strftime(fmt) if start else "[NOT SET]"
    end_s = end.strftime(fmt) if end else "[NOT SET]"

    arv = sweeps.get("prize_arv_total") or 0
    sponsor = sweeps.get("sponsor_name") or "[SPONSOR NAME NOT SET]"
    addr = sweeps.get("sponsor_address") or "[SPONSOR ADDRESS NOT SET]"
    email = sweeps.get("sponsor_email") or ""
    price = sweeps.get("ticket_price") or 0

    prize_lines = "\n".join(
        f"   Prize {i}: {p}" for i, p in enumerate(prizes, 1)
    ) or "   [NO PRIZES DEFINED]"

    odds = ("Odds of winning depend on the number of eligible entries "
            "received during the Entry Period.")
    if total_entries:
        odds += f" As of the generation of these rules, {total_entries} entries have been received."

    mail_block = "\n           ".join(mail_address_lines(sweeps))
    limit = (sweeps.get("entry_limit_per_household")
             or sweeps.get("entry_limit_per_person") or 0)
    if limit == 1:
        limit_text = HOUSEHOLD_LIMIT_NOTE
    elif limit:
        limit_text = (f"Limit {limit} total entries per household for the "
                      f"duration of the Entry Period, regardless of method "
                      f"of entry. This limit applies equally to entries "
                      f"obtained by mail and entries obtained with a donation.")
    else:
        limit_text = "There is no limit on the number of entries per household."

    return f"""OFFICIAL RULES
{sweeps.get('name', 'Sweepstakes')}

NO PURCHASE OR PAYMENT OF ANY KIND IS NECESSARY TO ENTER OR WIN.
A PURCHASE OR PAYMENT WILL NOT INCREASE YOUR CHANCES OF WINNING.
VOID WHERE PROHIBITED BY LAW.

1. SPONSOR
   {sponsor}
   {addr}
   {email}

2. ENTRY PERIOD
   The Sweepstakes begins {start_s} and ends {end_s} (the "Entry Period").
   Entries submitted before or after the Entry Period will not be eligible.
   Sponsor's computer is the official time-keeping device for this Sweepstakes.

3. ELIGIBILITY
   {sweeps.get('eligibility_text') or DEFAULT_ELIGIBILITY}

4. HOW TO ENTER

   There are two (2) methods of entry. BOTH METHODS HAVE AN EQUAL CHANCE
   OF WINNING. Entries received by either method are placed into the same
   pool and are indistinguishable at the time of the drawing.

   (a) FREE METHOD OF ENTRY BY MAIL (NO PURCHASE NECESSARY)
       To enter free of charge, hand print the following on a plain 3" x 5"
       card or piece of paper:

           - Your full name
           - Your complete mailing address
           - Your email address
           - Your daytime phone number
           - Your date of birth
           - The words "FREE ENTRY REQUEST"

       Mail the card in a hand-addressed envelope with proper postage to:

           {mail_block}

       Limit one (1) entry per outer mailing envelope. Each mail-in entry
       must be mailed separately. Mail-in entries should be received by the
       drawing date to be included in the drawing.

       Mail-in entries receive one (1) entry at no cost and have the SAME
       chance of winning as entries obtained by purchase. Sponsor is not
       responsible for lost, late, misdirected, damaged, illegible, or
       postage-due mail.

   (b) ENTRY WITH PURCHASE
       Purchase one or more entries at ${price:.2f} per entry. Purchasing
       does NOT improve your odds per entry; it only allows you to obtain
       additional entries in a single transaction.

   {limit_text}

   Entries generated by script, macro, bot, or other automated means are
   void and will be disqualified.

5. PRIZES
{prize_lines}

   Total Approximate Retail Value (ARV) of all prizes: ${arv:,.2f}

   Prizes are non-transferable. No substitution or cash equivalent except
   at Sponsor's sole discretion. All federal, state, and local taxes on
   prizes are the sole responsibility of the winner.

6. WINNER SELECTION
   {sweeps.get('winner_selection_text') or DEFAULT_WINNER_SELECTION}

   {odds}

7. WINNER NOTIFICATION
   Winners will be notified by the email address supplied at entry.
   If a winner cannot be contacted, does not respond, or is found to be
   ineligible, the prize may be forfeited and an alternate winner selected.

8. PRIVACY
   Information collected from entrants is subject to the Sponsor's privacy
   practices and is used for the administration of this Sweepstakes and
   winner notification.

9. GENERAL CONDITIONS
   By entering, entrants agree to be bound by these Official Rules and by
   the decisions of the Sponsor, which are final and binding in all matters
   relating to this Sweepstakes.

   {sweeps.get('void_where') or 'Void where prohibited or restricted by law.'}

10. GOVERNING LAW
    This Sweepstakes is governed by the laws of the State of Georgia,
    United States, without regard to conflict of law principles.

--------------------------------------------------------------------------
NOTICE: These rules are generated from a template and have NOT been
reviewed by an attorney. Sweepstakes law varies by state and several
states require registration and/or bonding above certain prize values.
Have counsel licensed in your operating state review these rules before
running this promotion publicly.
--------------------------------------------------------------------------
"""


NO_PURCHASE_SHORT = ("NO PURCHASE NECESSARY. A purchase will not increase "
                     "your chances of winning. Void where prohibited.")


# ---------------------------------------------------------------------------
# HOUSEHOLD IDENTITY
# ---------------------------------------------------------------------------
# A "1 entry per household" limit needs a definition of household. We use the
# normalised street address when we have one, and fall back to the email
# address when we don't.
#
# CRITICAL: whatever this limit is, it MUST bind paid and free entrants
# EQUALLY. A cap that restricts only mail-in entrants would make the free
# path worse than the paid path -- that reintroduces consideration and turns
# the promotion back into a lottery. See db.entries_for_household().

# Strip punctuation and unit designators. The trailing (?=\d|\b) lets this
# match both "apt 4" and the glued form "apt4".
_ADDR_NOISE = re.compile(
    r"[.,#]|(?:apt|apartment|unit|ste|suite|no)(?=\s*\d|\b)",
    re.IGNORECASE)
_WS = re.compile(r"\s+")

_ADDR_ABBREV = {
    "street": "st", "avenue": "ave", "boulevard": "blvd", "drive": "dr",
    "road": "rd", "lane": "ln", "court": "ct", "circle": "cir",
    "place": "pl", "parkway": "pkwy", "highway": "hwy", "terrace": "ter",
    "north": "n", "south": "s", "east": "e", "west": "w",
}


def household_key(address="", email=""):
    """Stable key identifying a household.

    Address-based when an address is supplied (so two people in the same
    home share a key), else email-based. Normalisation collapses common
    variations: '123 Peachtree Street, Apt 4' and '123 peachtree st apt4'
    resolve to the same household.

    This is deliberately fuzzy. It will not catch someone determined to
    evade it -- that is what the postmark record and audit log are for.
    """
    a = (address or "").strip().lower()
    if a:
        a = _ADDR_NOISE.sub(" ", a)
        toks = [_ADDR_ABBREV.get(t, t) for t in _WS.split(a) if t]
        return "addr:" + " ".join(toks)
    e = (email or "").strip().lower()
    return f"email:{e}" if e else ""


HOUSEHOLD_LIMIT_NOTE = (
    "Limit one (1) entry per household for the duration of the Entry Period, "
    "regardless of method of entry. This limit applies equally to entries "
    "obtained by mail and entries obtained with a donation."
)
