# OLOT SOMSA — Telegram Mini App

A Telegram Mini App for ordering food from the OLOT SOMSA restaurant, built with:

- **Frontend**: React 18 + Vite + `@telegram-apps/telegram-ui`
- **Backend**: FastAPI + SQLAlchemy (async) + PostgreSQL 16
- **POS Integration**: AliPOS
- **Infrastructure**: Docker Compose + Cloudflare Tunnels

---

## Prerequisites

| Tool | Install |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Required |
| [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) | `brew install cloudflared` |
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
1. Start all Docker containers (PostgreSQL, backend, frontend)
2. Kill any stale Cloudflare tunnels
3. Create a new public HTTPS tunnel for the backend
4. Create a new public HTTPS tunnel for the frontend
5. Update `VITE_API_BASE_URL` in `.env` with the new backend URL
6. Rebuild the frontend container with the new URL
7. Print all URLs and BotFather instructions

Output looks like:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  All services running!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🖥  Frontend  →  https://xxxx-xxxx.trycloudflare.com
  🔧  Backend   →  https://yyyy-yyyy.trycloudflare.com

  📱  Set this URL in BotFather:
      https://xxxx-xxxx.trycloudflare.com
```

To force a full image rebuild (e.g. after pulling new code):

```bash
./start.sh --rebuild
```

---

## After Starting — Update BotFather

> **Cloudflare quick tunnels get a new URL every restart.** You must update your bot in BotFather after each `./start.sh`.

In Telegram, message [@BotFather](https://t.me/BotFather):

```
/setmenubutton
```
→ Select your bot → Enter the **Frontend URL** printed by `start.sh`.

Or to set a Web App:
```
/newapp  (if first time)
/editapp (to update URL)
```

---

## Stopping the App

```bash
cd restaurant-mini-app
docker compose down
pkill -f "cloudflared tunnel"
```

---

## Port Reference

| Service | Host Port | Container Port |
|---|---|---|
| PostgreSQL | `5432` | `5432` |
| Backend (FastAPI) | `8001` | `8000` |
| Frontend (Vite) | `3001` | `5173` |

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
| `POST` | `/auth/telegram` | — | Validate Telegram initData, return JWT |
| `GET` | `/menu` | — | Fetch full menu from AliPOS |
| `GET` | `/users/me` | JWT | Get current user profile |
| `PUT` | `/users/me` | JWT | Update phone number |
| `POST` | `/orders` | JWT | Place an order via AliPOS |
| `GET` | `/orders` | JWT | List user's orders |
| `GET` | `/orders/{id}` | JWT | Get order details |
| `GET` | `/orders/{id}/status` | JWT | Get live order status |
| `POST` | `/webhooks/alipos` | — | Receive AliPOS status updates |

---

## How Authentication Works

1. Telegram injects `window.Telegram.WebApp.initData` into the Mini App
2. Frontend POSTs it to `POST /auth/telegram`
3. Backend validates the HMAC-SHA256 signature using the bot token
4. Backend creates/updates the user in PostgreSQL and returns a JWT
5. All subsequent requests use `Authorization: Bearer <token>`

---

## Troubleshooting

**"530 The origin has been unregistered"**
→ Tunnel died. Run `./start.sh` again and update BotFather URL.

**"422 Unprocessable Entity" on /users/me or /orders**
→ Auth hasn't completed yet (race condition on first load). Reload the Mini App.

**Frontend shows blank / won't load**
→ Check `VITE_API_BASE_URL` in `.env` — must be the current backend tunnel URL. Run `./start.sh` to auto-fix.

**Docker port already in use**
→ Check what's using a port: `lsof -i :3001` then kill it or change ports in `docker-compose.yml`.

**Backend crash on first user login**
→ Was a datetime timezone bug — fixed in `models.py` (all timestamps use naive UTC).
