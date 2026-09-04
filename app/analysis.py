"""Menjalankan pipeline trading dari web app.

mode='demo'  -> data sintetis + fallback rule-based (gratis, tanpa OANDA/Ollama)
mode='live'  -> OANDA (praktik) + Ollama; butuh .env terisi, jika tidak akan
                otomatis jatuh (fallback) ke rule-based dengan peringatan.
"""
from __future__ import annotations

from typing import Any

from config import config
from structure.market import parse_structure
from data.synthetic import synthetic_client_fetch


def analyze(mode: str = "demo", instrument: str = "XAU_USD") -> dict[str, Any]:
    mode = mode if mode in ("demo", "live") else "demo"
    instrument = instrument or config.INSTRUMENT
    bias_tf = config.TIMEFRAME_BIAS
    entry_tf = config.TIMEFRAME_ENTRY

    if mode == "live" and config.has_oanda:
        try:
            from data.oanda import OandaClient, OandaError
            from ai.analyzer import build_signal, signal_to_dict
            from ai.llm import LlmUnavailable

            client = OandaClient(
                config.OANDA_TOKEN, config.OANDA_ACCOUNT_ID, config.OANDA_ENV
            )
            bias = parse_structure(
                client.fetch_candles(instrument, bias_tf, config.CANDLE_COUNT), bias_tf
            )
            entry = None
            if entry_tf and entry_tf != bias_tf:
                entry = parse_structure(
                    client.fetch_candles(instrument, entry_tf, 150), entry_tf
                )
            try:
                sig = build_signal(bias, entry, instrument=instrument)
            except LlmUnavailable as e:
                from ai.analyzer import fallback_signal

                sig = fallback_signal(bias, entry, instrument=instrument)
                sig.errors = [f"LLM tidak tersedia: {e} → fallback rule-based."]
            result = signal_to_dict(sig)
            result["mode"] = "live"
            return result
        except OandaError as e:
            # fallback ke demo
            pass
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "errors": [f"Live gagal: {e}"], "mode": "live"}
            return result

    # ---- demo (default) ----
    df = synthetic_client_fetch(instrument, bias_tf.lower(), config.CANDLE_COUNT)
    bias = parse_structure(df, bias_tf)
    entry = None
    if entry_tf and entry_tf != bias_tf:
        df2 = synthetic_client_fetch(instrument, entry_tf.lower(), 150)
        entry = parse_structure(df2, entry_tf)

    from ai.analyzer import fallback_signal, signal_to_dict

    sig = fallback_signal(bias, entry, instrument=instrument)
    result = signal_to_dict(sig)
    result["mode"] = "demo"
    if mode == "live":
        result["warning"] = (
            (result.get("warning") or "")
            + " Live tidak tersedia (cek .env OANDA/Ollama) — memakai data demo sintetis."
        ).strip()
    return result
