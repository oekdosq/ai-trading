"""Web app FastAPI — AI Trading XAUUSD (Smart Money Concept).

Fitur:
  - Register / Login (JWT cookie)
  - Dashboard: tombol "Analisis" (demo/live) + riwayat sinyal pribadi
  - Semua halaman via Jinja2 template.

Menjalankan:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from pathlib import Path

import jwt
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth, db
from app.analysis import analyze

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="AI Trading XAUUSD", version="0.1.0")
app.mount(
    "/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static"
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _user_from_request(request: Request) -> str | None:
    token = request.cookies.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def _require_user(request: Request):
    user = _user_from_request(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return user


# ---------- auth pages ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = _user_from_request(request)
    return templates.TemplateResponse(request, "index.html", {"user": user})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    try:
        auth.register_user(username, password)
    except Exception as e:  # noqa: BLE001
        detail = getattr(e, "detail", str(e))
        return templates.TemplateResponse(
            request, "register.html", {"error": detail}, status_code=400
        )
    resp = RedirectResponse("/login", status_code=303)
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not auth.authenticate(username, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Username/password salah."},
            status_code=401,
        )
    resp = RedirectResponse("/dashboard", status_code=303)
    auth.set_auth_cookie(resp, username)
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    auth.clear_auth_cookie(resp)
    return resp


# ---------- dashboard ----------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, info: str = "", error: str = ""):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user
    signals = db.list_signals(user, limit=30)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "signals": signals, "info": info, "error": error},
    )


@app.post("/analyze", response_class=HTMLResponse)
def do_analyze(request: Request, mode: str = Form("demo")):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user
    result = analyze(mode=mode, instrument="XAU_USD")
    if result.get("ok"):
        db.save_signal(user, {**result, "mode": result.get("mode", mode)})
        return RedirectResponse(
            f"/dashboard?info=Analisis berhasil ({result.get('mode')})", status_code=303
        )
    err = (result.get("errors") or ["Analisis gagal."])[0]
    return RedirectResponse(f"/dashboard?error={err}", status_code=303)


# ---------- API (opsional, JSON) ----------
@app.get("/api/signal")
def api_signal():
    return analyze(mode="demo")
