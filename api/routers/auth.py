from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import httpx, jwt, uuid, time, os
from database import get_conn

router = APIRouter()

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:3000")
JWT_SECRET           = os.getenv("JWT_SECRET", "change-this-secret")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

GOOGLE_SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
])

def create_jwt(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60 * 60 * 24 * 30,  # 30 dias
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = auth_header[7:]
    payload = decode_jwt(token)
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return dict(user)

@router.get("/google")
def google_login():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/auth?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)

@router.get("/callback")
async def google_callback(code: str):
    async with httpx.AsyncClient() as client:
        # Troca code por tokens
        token_res = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        tokens = token_res.json()
        if "error" in tokens:
            raise HTTPException(status_code=400, detail=tokens["error"])

        # Busca info do usuário
        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        guser = user_res.json()

    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (guser["email"],)).fetchone()

    if not user:
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, name, avatar, credits) VALUES (?, ?, ?, ?, ?)",
            (user_id, guser["email"], guser.get("name"), guser.get("picture"), 10)  # 10 créditos grátis
        )
        conn.execute(
            "INSERT INTO transactions (id, user_id, type, amount, description) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, "bonus", 10, "Créditos de boas-vindas")
        )
        conn.commit()
        user_id_final = user_id
    else:
        user_id_final = user["id"]

    conn.close()

    # Salva o drive_token na sessão (simplificado — em prod usar refresh token criptografado)
    jwt_token = create_jwt(user_id_final, guser["email"])
    drive_token = tokens.get("access_token", "")

    return RedirectResponse(
        f"{FRONTEND_URL}/dashboard?token={jwt_token}&drive_token={drive_token}"
    )

@router.get("/me")
def me(request: Request):
    user = get_current_user(request)
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "avatar": user["avatar"],
        "credits": user["credits"],
    }
