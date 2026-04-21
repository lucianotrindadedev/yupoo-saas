from fastapi import APIRouter, Request, HTTPException, Header
from database import get_conn
from routers.auth import get_current_user
import stripe, uuid, os, json

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

PACKAGES = {
    "starter":  {"credits": 200,   "price_id": os.getenv("STRIPE_PRICE_STARTER",  "")},
    "pro":      {"credits": 1000,  "price_id": os.getenv("STRIPE_PRICE_PRO",      "")},
    "business": {"credits": 5000,  "price_id": os.getenv("STRIPE_PRICE_BUSINESS", "")},
    "unlimited":{"credits": 999999,"price_id": os.getenv("STRIPE_PRICE_UNLIMITED","")},
}

@router.get("/packages")
def list_packages():
    return [
        {"id": k, "credits": v["credits"], "price_id": v["price_id"]}
        for k, v in PACKAGES.items()
    ]

@router.post("/checkout/{package_id}")
async def create_checkout(package_id: str, request: Request):
    user = get_current_user(request)
    pkg = PACKAGES.get(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Pacote não encontrado")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": pkg["price_id"], "quantity": 1}],
        mode="payment",
        success_url=f"{os.getenv('FRONTEND_URL')}/dashboard?payment=success",
        cancel_url=f"{os.getenv('FRONTEND_URL')}/pricing",
        metadata={"user_id": user["id"], "package_id": package_id, "credits": pkg["credits"]},
    )
    return {"checkout_url": session.url}

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO stripe_webhooks (id, event_type, payload) VALUES (?, ?, ?)",
        (event["id"], event["type"], json.dumps(event))
    )
    conn.commit()

    if event["type"] == "checkout.session.completed":
        meta     = event["data"]["object"]["metadata"]
        user_id  = meta["user_id"]
        credits  = int(meta["credits"])
        pkg_id   = meta["package_id"]
        stripe_id = event["data"]["object"]["id"]

        conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (credits, user_id))
        conn.execute(
            "INSERT INTO transactions (id, user_id, type, amount, description, stripe_id) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, "purchase", credits, f"Compra pacote {pkg_id}", stripe_id)
        )
        conn.commit()

    conn.close()
    return {"received": True}

@router.get("/history")
def credit_history(request: Request):
    user = get_current_user(request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT type, amount, description, created_at FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
        (user["id"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
