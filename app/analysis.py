"""Menjalankan pipeline trading dari web app.

mode='demo'  -> data sintetis + fallback rule-based (gratis, tanpa OANDA/Ollama)
mode='real'  -> candle XAU/USD NYATA sumber gratis: TradingView -> Dukascopy
                (primary; bila IP diblokir, error jujur + harga spot asli).
mode='live'  -> OANDA (praktik)+Ollama bila .env terisi; tanpa itu otomatis
                memakai rantai TradingView gratis (pengganti OANDA).
"""
from __future__ import annotations

from typing import Any

from config import config
from structure.market import parse_structure
from data.synthetic import synthetic_client_fetch


def _rule_signal(
    df_bias: Any,
    bias_tf: str,
    instrument: str,
    entry_df: Any = None,
    entry_tf: str | None = None,
) -> dict[str, Any]:
    from ai.analyzer import fallback_signal, signal_to_dict

    bias = parse_structure(df_bias, bias_tf)
    entry = None
    if entry_tf and entry_tf != bias_tf and entry_df is not None:
        entry = parse_structure(entry_df, entry_tf)
    sig = fallback_signal(bias, entry, instrument=instrument)
    return signal_to_dict(sig)


def analyze(mode: str = "demo", instrument: str = "XAU_USD") -> dict[str, Any]:
    mode = mode if mode in ("demo", "real", "live") else "demo"
    instrument = instrument or config.INSTRUMENT
    bias_tf = config.TIMEFRAME_BIAS
    entry_tf = config.TIMEFRAME_ENTRY

    oanda_failed_reason: str | None = None
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
            result["source"] = "OANDA (akun nyata, premium)"
            return result
        except OandaError as e:
            oanda_failed_reason = str(e)
            print(f"  [live] OANDA gagal → lanjut rantai TradingView: {e}")
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "errors": [f"Live gagal: {e}"], "mode": "live"}
            return result

    if mode in ("real", "live"):
        try:
            from data.free import free_client_fetch, free_spot, FreeDataError

            result = _rule_signal(
                free_client_fetch(instrument, bias_tf, config.CANDLE_COUNT),
                bias_tf,
                instrument,
            )
            if entry_tf and entry_tf != bias_tf:
                entry_df = free_client_fetch(instrument, entry_tf, 150)
                bias_df = free_client_fetch(instrument, bias_tf, config.CANDLE_COUNT)
                result = _rule_signal(
                    bias_df,
                    bias_tf,
                    instrument,
                    entry_df=entry_df,
                    entry_tf=entry_tf,
                )
            result["mode"] = mode
            result["source"] = (
                "TradingView/Dukascopy (chart asli, gratis)"
                if mode == "real"
                else "TradingView (gratis, tanpa OANDA — mode live premium nonaktif)"
            )
            if mode == "live":
                if not config.has_oanda:
                    result["warning"] = (
                        "OANDA tidak dikonfigurasi (.env) — mode live memakai rantai "
                        "TradingView gratis sebagai gantinya."
                    )
                elif oanda_failed_reason:
                    result["warning"] = (
                        f"OANDA gagal ({oanda_failed_reason}) — diganti TradingView gratis."
                    )
            return result
        except FreeDataError as e:
            try:
                spot = free_spot()
            except FreeDataError:
                spot = None
            return {
                "ok": False,
                "mode": mode,
                "errors": [
                    f"Riwayat candle intraday tidak tersedia dari IP ini: {e}",
                    "Jalankan di Oracle VM (IP tidak diblokir) agar chart asli tersedia.",
                ],
                "spot_price": spot["price"] if spot else None,
                "spot_updated_at": spot["updated_at"] if spot else None,
                "spot_source": spot["source"] if spot else None,
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "mode": mode,
                "errors": [f"{mode.capitalize()} gagal: {e}"],
            }

    # ---- demo (default) ----
    df = synthetic_client_fetch(instrument, bias_tf.lower(), config.CANDLE_COUNT)
    result = _rule_signal(
        df,
        bias_tf,
        instrument,
        entry_df=synthetic_client_fetch(instrument, entry_tf.lower(), 150)
        if (entry_tf and entry_tf != bias_tf)
        else None,
        entry_tf=entry_tf,
    )
    result["mode"] = "demo"
    if mode == "live":
        result["warning"] = (
            (result.get("warning") or "")
            + " Live tidak tersedia (cek .env OANDA/Ollama) — memakai data demo sintetis."
        ).strip()
    return result
