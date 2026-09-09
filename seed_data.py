"""Optional production seed data.

Render starts with an empty persistent disk unless a DB file is uploaded. This
module lets a fresh deployment create the Mother's Day Sweepstakes record once,
without committing raffle.db to GitHub.

Seeding only runs when RAFFLE_SEED_ON_INIT=1 and the raffles table is empty.
"""

MOTHERS_DAY_RAFFLE = {
    "id": 6,
    "name": "Mother's Day Sweepstakes Drawing",
    "ticket_price": 10.0,
    "num_prizes": 3,
    "prize_1": "Adventure Outdoors Gift Card (ARV $895)",
    "prize_2": "MCM Dessau Drawstring Handbag (ARV $1,100)",
    "prize_3": "$500 Visa Gift Card",
    "prize_4": None,
    "status": "open",
    "created_at": "2026-09-02T12:15:11",
    "sponsor_name": "Titan Cybersecurity LLC",
    "sponsor_address": "Lawrenceville, GA 30045",
    "sponsor_email": "jb@titancybersecurity.com",
    "start_at": "2026-09-07T18:54:00+00:00",
    "end_at": "2027-05-09T03:59:00+00:00",
    "prize_arv_total": 2495.0,
    "eligibility_text": (
        "Open only to legal residents of the United States who are 18 years "
        "of age or older at the time of entry. Void where prohibited by law. "
        "Employees of the Sponsor and their immediate family members are not "
        "eligible."
    ),
    "void_where": "",
    "entry_limit_per_person": 0,
    "amoe_enabled": 1,
    "winner_selection_text": (
        "Winners will be selected in a random drawing from among all eligible "
        "entries received during the Entry Period. The drawing will be "
        "conducted using a cryptographically secure random number generator. "
        "Odds of winning depend on the total number of eligible entries received."
    ),
    "rules_published": 0,
    "prize_1_url": "https://shop.adventureoutdoors.us/manufacturer/smith-wesson/detail/f485f8f9-fe24-4683-9217-38d1ba09652d/efc6952e-9182-44fd-bce8-915d78bb8ccc",
    "prize_2_url": "https://us.mcmworldwide.com/en_US/bags/all-bags/dessau-drawstring-bag-in-visetos/MWDGSDU03CO001.html?cgid=bags-all-bags&sz=96&start=0",
    "prize_3_url": "https://www.giftcards.com/visa-gift-cards",
    "prize_4_url": "",
    "prize_1_img": "/static/prizes/adventure_outdoors_logo.jpg",
    "prize_2_img": "/static/prizes/mcm_handbag.jpg",
    "prize_3_img": "/static/prizes/visa_giftcard_500.svg",
    "prize_4_img": "",
    "mail_name": "Mother's Day Sweepstakes Drawing",
    "mail_attn": "Free Entry",
    "mail_street": "5456 Peachtree Blvd, Suite 134",
    "mail_city": "Atlanta",
    "mail_state": "GA",
    "mail_zip": "30341",
    "entry_limit_per_household": 1,
}


def seed_if_empty(conn):
    """Insert the default sweepstakes only when no raffle rows exist."""
    count = conn.execute("SELECT COUNT(*) FROM raffles").fetchone()[0]
    if count:
        return False

    data = MOTHERS_DAY_RAFFLE
    cols = list(data)
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO raffles ({','.join(cols)}) VALUES ({placeholders})",
        [data[c] for c in cols],
    )
    conn.commit()
    return True
