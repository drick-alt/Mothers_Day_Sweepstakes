# Raffle Sales App

Ticket sales, buyer tracking, printable drum list, and **statistically correct**
win-probability analytics.

## Run it

```bash
cd raffle-app
python3 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]"
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

## Test it

```bash
.venv/bin/python test_odds.py   # math vs 400k-trial Monte Carlo
./e2e_test.sh                   # 30 end-to-end HTTP tests
```

---

## The odds math (the important part)

The obvious formula is **wrong**:

```
WRONG:  P(win) = (my_tickets / total) × num_prizes
```

With 4 tickets out of 10 and 4 prizes that gives **160%** — impossible.

Raffles draw prizes **without replacement** (a drawn ticket is set aside).
That is a **hypergeometric** distribution:

```
P(win nothing)     = C(N-k, p) / C(N, p)
P(win ≥ 1 prize)   = 1 - P(win nothing)
P(win exactly j)   = C(k,j) × C(N-k, p-j) / C(N, p)
E[prizes won]      = p × k / N
```

`N` = tickets sold, `k` = your tickets, `p` = number of prizes.

Same scenario, correct answer: **92.86%**.

`odds.py` also supports `with_replacement=True` if your raffle returns the
drawn ticket to the drum (one ticket can win multiple prizes).

### Verified
`test_odds.py` runs the analytic formula against a 400,000-trial physical
simulation and confirms agreement to within 0.4%, plus edge cases
(zero tickets, owning the whole pool, more prizes than tickets) and proves the
distribution sums to exactly 1.0.

---

## What each buyer sees

| Metric | Meaning |
|---|---|
| **Chance to win** | P(at least one of the 4 prizes) |
| **Odds** | Expressed as "1 in N" |
| **Expected prizes** | Average prizes won over many repeats |
| **Exact breakdown** | P(win exactly 0/1/2/3/4) |
| **Marginal value** | % one more ticket would add right now |
| **Dilution forecast** | How odds fall as +50/+100/+250/+500/+1000 sell |

Buyers return anytime with an 8-character lookup code. Odds recompute live
against current sales.

---

## Pages

| Route | Purpose |
|---|---|
| `/` | Raffle list + create form |
| `/raffle/{id}` | Buy page with live odds preview |
| `/receipt/{code}` | Buyer's receipt, tickets, full analytics |
| `/lookup` | Find receipt by code |
| `/admin/{id}` | Sales dashboard, per-buyer odds |
| `/admin/{id}/drum` | **Printable drum list** |
| `/admin/{id}/drum.csv` | CSV export |
| `/admin/{id}/winners` | Results |

## API

```
GET /api/odds?raffle_id=1&tickets=5
GET /api/raffle/1/stats
```

---

## Drum list

`/admin/{id}/drum` renders every active ticket sorted by number with a
print-optimized stylesheet (dark UI drops away, nav hidden). Print → cut on the
row lines → drop in the machine. CSV export for mail-merge onto pre-perforated
ticket stock.

## Drawing

- `secrets.randbelow()` (CSPRNG), not `random`
- Without replacement — one ticket cannot win twice
- Refuses to draw twice on the same raffle
- Sets raffle to `drawn`, which blocks further sales
- Winners appear on each buyer's receipt with a "YOU WON!" marker

---

## Files

```
odds.py       hypergeometric engine
db.py         SQLite persistence, transactional purchase, CSPRNG draw
main.py       FastAPI routes
views.py      server-rendered HTML
test_odds.py  math validation vs Monte Carlo
e2e_test.sh   30 HTTP integration tests
```

---

## Before going live

Not built in — add these for production:

1. **Payments** — Stripe/Square. `orders.payment_ref` column is already there.
2. **Admin auth** — `/admin/*` is currently open. Put it behind login.
3. **Email receipts** — SMTP send on purchase.
4. **Legal** — raffle/lottery rules vary by state. Check yours before selling.
5. **Backups** — `raffle.db` is the whole system. Back it up before the draw.
