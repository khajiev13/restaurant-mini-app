# OLOT SOMSA — Telegram Mini App

A Telegram Mini App for ordering food from the OLOT SOMSA restaurant, built with:

- **Frontend**: React 18 + Vite + `@telegram-apps/telegram-ui`
- **Backend**: FastAPI + SQLAlchemy (async) + PostgreSQL 16
- **POS Integration**: AliPOS
- **Infrastructure**: Docker Compose + Caddy + Cloudflare Tunnel

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

# AliPOS API
ALIPOS_API_CLIENT_ID=your-client-id
ALIPOS_API_CLIENT_SECRET=your-client-secret
ALIPOS_API_BASE_URL=https://web.alipos.uz

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
| `POST` | `/api/webhooks/order-status` | — | Receive AliPOS status updates |
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
