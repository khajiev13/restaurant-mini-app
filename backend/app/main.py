from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import addresses, auth, menu, orders, users, webhooks

app = FastAPI(title="Mr.Pub Restaurant API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Will be restricted to Telegram Mini App origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(menu.router)
app.include_router(users.router)
app.include_router(addresses.router)
app.include_router(orders.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
