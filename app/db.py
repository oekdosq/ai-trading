"""Database SQLite sederhana (stdlib sqlite3) untuk web app.

Tabel:
  users   -> id, username, password_hash, created_at
  signals -> id, username, action, bias, confidence, entry, stop_loss,
             take_profit, risk_reward, rationale, mode, created_at

Tidak butuh server DB eksternal — cukup file .db lokal.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT,
                bias TEXT,
                confidence REAL,
                entry REAL,
                stop_loss REAL,
                take_profit REAL,
                risk_reward REAL,
                rationale TEXT,
                mode TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


# ---- users ----
def create_user(username: str, password_hash: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
            (username, password_hash, _now()),
        )


def get_user(username: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def user_exists(username: str) -> bool:
    return get_user(username) is not None


# ---- signals ----
def save_signal(username: str, sig: dict) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO signals
              (username, action, bias, confidence, entry, stop_loss, take_profit,
               risk_reward, rationale, mode, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                username,
                sig.get("action"),
                sig.get("bias"),
                sig.get("confidence"),
                sig.get("entry"),
                sig.get("stop_loss"),
                sig.get("take_profit"),
                sig.get("risk_reward"),
                sig.get("rationale"),
                sig.get("mode", "demo"),
                _now(),
            ),
        )
        return int(cur.lastrowid)


def list_signals(username: str, limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM signals WHERE username = ? ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()
        return [dict(r) for r in rows]
