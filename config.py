"""Konfigurasi terpusat via env vars (python-dotenv).

Semua kredensial hanya dibaca dari .env dan TIDAK pernah di-commit.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    """Baca nilai config sekali, ekspos sebagai atribut."""

    # OANDA (practice/demo)
    OANDA_TOKEN: str = _get("OANDA_TOKEN")
    OANDA_ACCOUNT_ID: str = _get("OANDA_ACCOUNT_ID")
    OANDA_ENV: str = _get("OANDA_ENV", "practice")

    # LLM lokal (Ollama)
    OLLAMA_MODEL: str = _get("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_HOST: str = _get("OLLAMA_HOST", "http://localhost:11434")

    # Instrumen & timeframe default
    INSTRUMENT: str = _get("INSTRUMENT", "XAU_USD")
    # Bias pakai HTF, entry pakai LTF (multi-timeframe alignment)
    TIMEFRAME_BIAS: str = _get("TIMEFRAME_BIAS", "H1")
    TIMEFRAME_ENTRY: str = _get("TIMEFRAME_ENTRY", "M15")

    # Default candle count saat fetch
    CANDLE_COUNT: int = int(_get("CANDLE_COUNT", "400"))

    @property
    def has_oanda(self) -> bool:
        return bool(self.OANDA_TOKEN and self.OANDA_ACCOUNT_ID)


config = Config()
