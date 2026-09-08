# Deployment Guide — Mother's Day Sweepstakes Drawing

## Recommendation

Use **GitHub for source control** and deploy the FastAPI app to **Render**,
Railway, Fly.io, or a VPS. Use GoDaddy only as a domain/DNS registrar if you
already own the domain there.

Do **not** use GitHub Pages. This app is not static; it needs Python, SQLite,
admin sessions, payment webhooks, email, and persistent storage.

## Files added for deployment

| File | Purpose |
|---|---|
| `.env.example` | Required env vars and secrets template |
| `requirements.txt` | Python dependencies |
| `Procfile` | Heroku/Railway-style process declaration |
| `start.sh` | Production start command |
| `render.yaml` | Render blueprint with persistent disk |
| `.gitignore` | Prevents committing DBs, logs, env files, venv |
| `prepare_production_db.py` | Creates clean production DB copy |

## Start command

```bash
./start.sh
```

Equivalent:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Required production environment variables

```bash
ADMIN_PASSWORD=<strong password>
ADMIN_SESSION_SECRET=<32+ random bytes>
RAFFLE_DB_PATH=/data/raffle.db
RAFFLE_SEED_ON_INIT=1
RAFFLE_BASE_URL=https://your-domain.example
SWEEPS_IP_SALT=<stable random secret>
```

If `ADMIN_PASSWORD` or `ADMIN_SESSION_SECRET` is missing, `/admin/*` fails
closed with HTTP 503. Public pages still work.

## Admin authentication

Protected paths:

```text
/admin/*
```

Allowed without a session:

```text
/admin/login
/admin/logout
```

Unauthenticated behavior:

| Request | Response |
|---|---|
| `GET /admin/6` | 303 redirect to `/admin/login?next=/admin/6` |
| `POST /admin/...` | 401 JSON `Admin login required` |
| Missing admin secrets | 503 closed |

Session cookie:

- Name: `sweeps_admin`
- Signed HMAC-SHA256
- HTTP-only
- SameSite=Lax
- Default lifetime: 8 hours

## Clean production DB

The current `raffle.db` contains demo/test entrants. Do not delete it until you
confirm.

To create a clean DB preserving only the Mother's Day Sweepstakes configuration:

```bash
python3 prepare_production_db.py
```

Output:

```text
raffle_prod_clean.db
```

It keeps sweepstakes id `6`, prizes, links/images, rules, dates, mail-in AMOE
address, and settings. It removes:

- buyers
- orders
- tickets
- draws
- payment events
- AMOE request log

For Render with the blueprint in `render.yaml`, copy this file to the mounted
persistent disk as `/data/raffle.db`.

## Render setup

1. Push repo to GitHub.
2. In Render: New → Blueprint or Web Service.
3. Build command:
   ```bash
   pip install -r requirements.txt
   ```
4. Start command:
   ```bash
   ./start.sh
   ```
5. Add persistent disk:
   ```text
   mountPath: /data
   size: 1 GB
   ```
6. Set `RAFFLE_DB_PATH=/data/raffle.db`.
7. Upload/copy `raffle_prod_clean.db` to `/data/raffle.db`, or run a one-time
   migration/seed step before launch.

## Payment go-live blockers

Before real donations:

1. Attorney review of Official Rules / AMOE.
2. Stable domain.
3. Stripe account + live key + webhook secret.
4. Webhook endpoint:
   ```text
   https://your-domain.example/webhook/stripe
   ```
5. Email backend switched from `preview` to SMTP/transactional provider.

## Local production-like test

```bash
export ADMIN_PASSWORD='test-password'
export ADMIN_SESSION_SECRET='dev-only-secret-change-me-32-bytes'
export RAFFLE_DB_PATH="$PWD/raffle.db"
./start.sh
```

Then visit `/admin/login`.
