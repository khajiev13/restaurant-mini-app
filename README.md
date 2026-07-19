# OLOT SOMSA — Telegram Mini App

A production Telegram Mini App for restaurant ordering, built around a real food-ordering workflow: menu sync, cart checkout, AliPOS order creation, hosted payment callbacks, and live order status.

**Highlights**

- Telegram Mini App frontend with React 19, Vite, and `@telegram-apps/telegram-ui`
- FastAPI backend with async SQLAlchemy, PostgreSQL 16, JWT auth, and Telegram `initData` validation
- AliPOS menu/order integration plus Multicard/Rahmat hosted checkout callbacks
- Docker Compose deployment with Caddy and Cloudflare Tunnel
- Signed callback handling, webhook endpoints, and automated checks for payment/order flows

**Links**

- Telegram bot: [@olotsomsa_zakaz_bot](https://t.me/olotsomsa_zakaz_bot)
- Repository: [github.com/khajiev13/restaurant-mini-app](https://github.com/khajiev13/restaurant-mini-app)

---

## Prerequisites

| Tool | Install |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Required |
| A Telegram Bot | Create with [@BotFather](https://t.me/BotFather) |

---

## First-Time Setup

### 1. Clone the repo

```bash
git clone https://github.com/khajiev13/restaurant-mini-app.git
cd restaurant-mini-app
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Then fill in the values:

```env
# Telegram
TELEGRAM_BOT_TOKEN=8695209419:your-bot-token
TELEGRAM_BOT_USERNAME=olotsomsa_zakaz_bot
TABLE_ACCESS_SECRET=generate-a-separate-64-char-hex-secret

# AliPOS API
ALIPOS_API_CLIENT_ID=your-client-id
ALIPOS_API_CLIENT_SECRET=your-client-secret
ALIPOS_API_BASE_URL=https://web.alipos.uz
ALIPOS_RESTAURANT_ID=your-restaurant-id

# PostgreSQL
POSTGRES_USER=restaurant_user
POSTGRES_PASSWORD=your-strong-password
POSTGRES_DB=restaurant_db

# JWT (generate with: openssl rand -hex 32)
JWT_SECRET=your-64-char-hex-string

# Set automatically by start.sh — leave blank initially
VITE_API_BASE_URL=

# Set automatically by start.sh — leave blank initially
PUBLIC_APP_URL=

# Used when registering the Telegram webhook
TELEGRAM_WEBHOOK_SECRET=your-webhook-secret

# Optional hardening overrides (comma-separated)
CORS_ALLOWED_ORIGINS=
TRUSTED_HOSTS=
```

Generate a JWT secret:
```bash
openssl rand -hex 32
```

### 3. Make the start script executable

```bash
chmod +x start.sh
```

---

## Starting the App

Run this every time you want to start the app:

```bash
./start.sh
```

This will:
1. Start all Docker containers
2. Keep the origin private behind `127.0.0.1:8080` locally via Caddy
3. Connect the app to your configured Cloudflare Tunnel hostname
4. Verify `/healthz` and `/api/health` locally and publicly
5. Update `PUBLIC_APP_URL` in `.env`
6. Set the Telegram webhook automatically
7. Set the Telegram menu button automatically

Output looks like:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  App exposed through Cloudflare named tunnel
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🌍  Public app     →  https://restaurant.labtutor.app/
  🔗  Webhook        →  https://restaurant.labtutor.app/api/webhooks/bot
```

To force a full image rebuild (e.g. after pulling new code):

```bash
./start.sh --rebuild
```

---

## Cloudflare Tunnel

For local Telegram Mini App testing and production, use a named Cloudflare Tunnel with a stable hostname like `https://restaurant.labtutor.app` and set:

```env
PUBLIC_APP_URL=https://restaurant.labtutor.app
CLOUDFLARE_TUNNEL_TOKEN=your-cloudflare-tunnel-token
```

`start.sh` uses a single named Cloudflare Tunnel container and verifies that the stable hostname is reachable before updating Telegram.

Important:
- Never run the production `CLOUDFLARE_TUNNEL_TOKEN` on a developer laptop.
- The production tunnel must only be attached to the production server connector.
- If you need local Cloudflare testing, use a separate tunnel or a temporary Quick Tunnel.

## After Starting

`start.sh` updates the webhook and the bot menu button automatically.

Useful local checks:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/api/health
```

The only manual Telegram step left is BotFather's main Mini App URL if you use the profile launch button:

```
/editapp (to update URL)
```
→ Set it to the **Public app URL** printed by `start.sh`.

---

## Stopping the App

```bash
cd restaurant-mini-app
docker compose down
docker rm -f restaurant_cloudflared >/dev/null 2>&1 || true
```

---

## Port Reference

| Service | Host Port | Container Port |
|---|---|---|
| Local Caddy origin | `127.0.0.1:8080` | `80` |
| Public app (via tunnel) | configured `PUBLIC_APP_URL` | `caddy:80` |

---

## Project Structure

```
restaurant-mini-app/
├── start.sh                  # One-command startup script
├── docker-compose.yml
├── .env                      # Your secrets (gitignored)
├── .env.example              # Template
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── middleware/
│       │   └── telegram_auth.py    # JWT auth + initData validation
│       ├── models/
│       │   └── models.py           # SQLAlchemy ORM models
│       ├── routers/
│       │   ├── auth.py             # POST /auth/telegram
│       │   ├── users.py            # GET/PUT /users/me
│       │   ├── menu.py             # GET /menu (proxies AliPOS)
│       │   ├── orders.py           # POST /orders, GET /orders
│       │   └── webhooks.py         # POST /webhooks/alipos
│       └── schemas/
│
├── frontend/
│   ├── Dockerfile
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx                 # Telegram SDK init, routing
│       ├── pages/
│       │   ├── MenuPage.jsx        # Product catalog + cart button
│       │   ├── CartPage.jsx        # Order placement
│       │   ├── OrderStatusPage.jsx # Live order tracking
│       │   └── ProfilePage.jsx     # User info + order history
│       ├── stores/
│       │   ├── cartStore.js        # Zustand cart state
│       │   └── authStore.js        # JWT auth state
│       └── services/
│           └── api.js              # Axios client
│
└── database/
    └── init.sql                    # Initial schema
```

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/health` | — | Health check for the API |
| `POST` | `/api/auth/telegram` | — | Validate Telegram initData, return JWT |
| `GET` | `/api/menu` | — | Fetch full menu from AliPOS |
| `GET` | `/api/users/me` | JWT | Get current user profile |
| `PUT` | `/api/users/me` | JWT | Update phone number |
| `POST` | `/api/orders` | JWT | Place an order via AliPOS |
| `GET` | `/api/orders` | JWT | List user's orders |
| `GET` | `/api/orders/{id}` | JWT | Get order details |
| `GET` | `/api/orders/{id}/status` | JWT | Get live order status |
| `DELETE` | `/api/orders/{id}` | JWT | Cancel the customer's new table order |
| `POST` | `/api/orders/{id}/switch-to-cash` | JWT | Cancel an unpaid invoice, then submit the table order as cash |
| `POST` | `/api/orders/{id}/retry-payment` | JWT | Create a new checkout after a definite payment failure or confirmed expiry |
| `POST` | `/api/tables/resolve` | — | Resolve a signed QR entry or numeric manual table code |
| `POST` | `/api/tables/restore/{order_id}` | JWT | Restore safe table context before its original QR session expires |
| `GET` | `/api/tables/manifest` | Admin JWT | Generate current table deep links and manual codes |
| `POST` | `/api/webhooks/order-status` | — | Receive AliPOS status updates |
| `POST` | `/api/webhooks/stoplist/{product_id}` | — | Receive AliPOS menu availability updates |
| `POST` | `/api/webhooks/bot` | — | Receive Telegram bot updates |
| `POST` | `/api/webhooks/multicard/callback` | — | Receive Multicard payment callbacks |

---

## How Authentication Works

1. Telegram injects `window.Telegram.WebApp.initData` into the Mini App
2. Frontend POSTs it to `POST /api/auth/telegram`
3. Backend validates the HMAC-SHA256 signature using the bot token
4. Backend creates/updates the user in PostgreSQL and returns a JWT
5. All subsequent requests use `Authorization: Bearer <token>`

---

## QR Table Ordering

Each physical table uses its number as the manual code: for example, `Stoll 12` uses manual code `12`. New manifest links use signed `t2_` start parameters; existing signed `t_` links remain compatible. Table-number gaps are valid, including the intentionally absent table `9`.

Install the development dependencies, keep the admin JWT in the environment, and download the current manifest without writing the JWT into a command-line argument or file:

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt

test -n "$ADMIN_JWT"
backend/.venv/bin/python scripts/download_table_manifest.py \
  --output /private/tmp/olot-table-manifest.json

backend/.venv/bin/python scripts/generate_table_qr_pngs.py \
  --manifest /private/tmp/olot-table-manifest.json \
  --public-base https://restaurant.labtutor.app \
  --bot-username olotsomsa_zakaz_bot \
  --output /private/tmp/olot-table-qr-pngs
```

Both output paths must be new. The downloader reads `ADMIN_JWT` only from the environment, accepts only a direct HTTP `200`, rejects redirects, never logs the token or response body, and refuses to overwrite an existing manifest file. The generator checks both public health endpoints, requires every deep link to target the explicitly trusted `olotsomsa_zakaz_bot`, and resolves every signed manifest entry against the deployed API before rendering. It then decodes every generated symbol and publishes the folder with an atomic no-replace operation only when every decoded destination exactly matches its manifest deep link. It refuses to overwrite an existing output directory.

The output directory contains only raw, opaque, black-on-white PNG QR symbols named for the manifest's table numbers. It contains no manifest, text in any language, numbers, labels, logo, frame, PDF, ZIP, JSON, CSV, README, design elements, or nested directory. The JWT remains environment-held and is used only by the separate manifest-download command; the generator itself uses no application credential.

A scan opens the existing menu with a session-scoped table context. Customers at the same table keep separate carts and orders; they never see a shared table bill.

Payment behavior:

- Cash is the default and the order is submitted to the selected AliPOS table immediately.
- Online payment opens Multicard first. AliPOS receives the order only after the signed callback confirms the exact amount.
- A still-unpaid online order can switch to cash only after Multicard confirms invoice cancellation.
- Definite payment-link failures and confirmed expiries can retry online or switch to cash. Network-ambiguous invoice creation is held for verification and is never retried automatically.
- A table order can be cancelled only while AliPOS still reports `NEW`; a paid cancellation requests a full refund.
- Client request IDs prevent duplicate checkout retries. Queued cash/paid orders and queued refunds resume safely after a restart; ambiguous provider outcomes are reconciled instead of blindly repeated.
- Customer menu reads and checkout repricing merge stop-list webhooks with AliPOS's live item/modifier availability feed.
- Payment-return restoration is capped to the original QR/manual-code expiry and never extends table access. After expiry, ordering more requires a fresh scan or code.

Before deploying this feature to an existing database, apply the idempotent migration:

```bash
set -a; source .env; set +a
docker compose exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < database/migrations/2026-07-13-qr-table-ordering.sql
```

Use a separate production `TABLE_ACCESS_SECRET` generated with `openssl rand -hex 32`. Rotating it invalidates printed QR signatures and active table sessions, so regenerate and reprint the manifest after rotation.

---

## Troubleshooting

**Cloudflare public URL is not reachable**
→ Check that `PUBLIC_APP_URL` and `CLOUDFLARE_TUNNEL_TOKEN` are correct in `.env`, then run `./start.sh` again.

**"422 Unprocessable Entity" on /users/me or /orders**
→ Auth hasn't completed yet (race condition on first load). Reload the Mini App.

**Frontend shows blank / won't load**
→ Run `./start.sh` again and verify that the configured `PUBLIC_APP_URL` opens correctly.

**Docker port already in use**
→ Check what's using the local Caddy port: `lsof -i :8080` then kill it or change the Caddy port in `docker-compose.yml`.

**Backend crash on first user login**
→ Was a datetime timezone bug — fixed in `models.py` (all timestamps use naive UTC).
