"""Autentikasi: register, login, verifikasi JWT (cookie).

Password di-hash (PBKDF2-HMAC-SHA256, stdlib). Token JWT disimpan sebagai
cookie HTTP-only (HttpOnly) sehingga tidak bisa dibaca JavaScript.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app import db

# Secret: ambil dari env; fallback untuk dev lokal (jangan untuk produksi).
SECRET_KEY = os.environ.get("WEB_SECRET", "dev-insecure-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.environ.get("WEB_TOKEN_MINUTES", "1440"))  # 24 jam

bearer = HTTPBearer(auto_error=False)

# Password hashing: PBKDF2-HMAC-SHA256 (stdlib, tanpa dependensi eksternal).
_PBKDF2_ITERATIONS = 260_000


def hash_password(plain: str) -> str:
    """Format: pbkdf2$<iterations>$<salt_b64>$<hash_b64>"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return "pbkdf2${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def verify_password(plain: str, stored: str) -> bool:
    try:
        scheme, iters_s, salt_b64, hash_b64 = stored.split("$")
        if scheme != "pbkdf2":
            return False
        iterations = int(iters_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:  # noqa: BLE001
        return False


def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def set_auth_cookie(response: Response, username: str) -> None:
    token = _create_token(username)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie("token")


def register_user(username: str, password: str) -> None:
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username & password wajib diisi.")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password minimal 4 karakter.")
    if db.user_exists(username):
        raise HTTPException(status_code=409, detail="Username sudah dipakai.")
    db.create_user(username, hash_password(password))


def authenticate(username: str, password: str) -> bool:
    user = db.get_user(username)
    if not user:
        return False
    return verify_password(password, user["password_hash"])


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.") from e


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Ambil username dari header Authorization Bearer (untuk API & dari cookie dipindai di route)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Belum login.")
    return _decode_token(credentials.credentials)
