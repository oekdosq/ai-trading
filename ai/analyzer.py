"""Penggabung: struktur parser → LLM → sinyal tervalidasi.

LLM boleh menghasilkan apa saja; kita VALIDASI dan NORMALISASI sebelum
dipakai. Cacat/format salah → tolak, jangan asal lewat. Ini melindungi
dari output model yang ngawur.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ai.llm import LlmClient, LlmResult, LlmUnavailable, _extract_json
from ai.prompt import SYSTEM_PROMPT
from structure.market import MarketSnapshot
from structure.snapshot import build_llm_packet

VALID_ACTIONS = {"buy", "sell", "hold"}
VALID_BIAS = {"bullish", "bearish", "netral"}


@dataclass
class Signal:
    ok: bool = False
    instruments: str = "XAU_USD"
    generated_utc: str = ""
    model: str = ""
    bias: str = "netral"
    action: str = "hold"
    confidence: float = 0.0
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    confluence_factors: list[str] = field(default_factory=list)
    rationale: str = ""
    warning: str = ""
    errors: list[str] = field(default_factory=list)


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _validate(data: dict[str, Any], errors: list[str]) -> None:
    act = str(data.get("action", "hold")).lower().strip()
    if act not in VALID_ACTIONS:
        errors.append(f"action tidak valid: {act!r}")
    bias = str(data.get("bias", "netral")).lower().strip()
    if bias not in VALID_BIAS:
        errors.append(f"bias tidak valid: {bias!r}")
    try:
        conf = float(data.get("confidence", 0))
        if not (0 <= conf <= 1):
            errors.append("confidence harus 0..1")
    except (TypeError, ValueError):
        errors.append("confidence bukan angka")
    if act in ("buy", "sell"):
        if _to_float(data.get("stop_loss")) is None:
            errors.append("action buy/sell wajib punya stop_loss")
        if _to_float(data.get("take_profit")) is None:
            errors.append("action buy/sell wajib punya take_profit")
        rr = _to_float(data.get("risk_reward"))
        if rr is not None and rr <= 0:
            errors.append("risk_reward harus positif")


def build_signal(
    bias_snap: MarketSnapshot,
    entry_snap: MarketSnapshot | None,
    *,
    instrument: str = "XAU_USD",
    llm: LlmClient | None = None,
) -> Signal:
    """Lakukan analisis penuh dan kembalikan Signal (validasi ketat)."""
    llm = llm or LlmClient()
    now = datetime.now(timezone.utc)
    packet = build_llm_packet(bias_snap, entry_snap, instrument=instrument, now=now)
    user_prompt = (
        "Berikut adalah snapshot struktur pasar terkini (JSON). "
        "Analisis dan berikan rekomendasi sesuai aturan:\n\n" + packet
    )

    try:
        result: LlmResult = llm.complete(SYSTEM_PROMPT, user_prompt)
    except LlmUnavailable as e:
        return Signal(ok=False, errors=[str(e)], generated_utc=now.isoformat())

    signal = Signal(ok=False, generated_utc=now.isoformat(), model=result.model)
    if not result.ok:
        signal.errors = [result.error or "LLM gagal"]
        return signal

    try:
        data = _extract_json(result.text)
    except json.JSONDecodeError as e:
        signal.errors = [f"Output bukan JSON valid: {e}"]
        return signal
    if not isinstance(data, dict):
        signal.errors = ["Output bukan object JSON"]
        return signal

    errors: list[str] = []
    _validate(data, errors)
    if errors:
        signal.errors = errors
        signal.rationale = str(data.get("rationale", ""))[:300]
        return signal

    signal.ok = True
    signal.action = str(data.get("action", "hold")).lower()
    signal.bias = str(data.get("bias", "netral")).lower()
    signal.confidence = round(float(data.get("confidence", 0)), 2)
    signal.entry = _to_float(data.get("entry"))
    signal.stop_loss = _to_float(data.get("stop_loss"))
    signal.take_profit = _to_float(data.get("take_profit"))
    signal.risk_reward = _to_float(data.get("risk_reward"))
    signal.confluence_factors = [
        str(x) for x in (data.get("confluence_factors") or []) if isinstance(x, str)
    ]
    signal.rationale = str(data.get("rationale", "")).strip()
    signal.warning = str(data.get("warning", "")).strip()
    signal.errors = []
    return signal


def fallback_signal(
    bias_snap: MarketSnapshot,
    entry_snap: MarketSnapshot | None = None,
    *,
    instrument: str = "XAU_USD",
) -> Signal:
    """Sinyal rule-based DARI STRUKTUR PARSER SAJA (tanpa LLM).

    Dipakai untuk mode demo offline / fallback saat Ollama tidak tersedia.
    Heuristik SMC sederhana:
      - arah dari event BOS/CHoCH/HH-HL/LH-LL terakhir.
      - confluence = jumlah sinyal searah yang mendukung.
      - SL/TP dibangun dari swing terdekat & jarak ATR-ish.
    Ini BUKAN pengganti penuh analisis LLM — hanya untuk demo & pengujian.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    sig = Signal(instruments=instrument, generated_utc=now.isoformat())

    dir_score = 0.0  # positif = bull, negatif = bear
    confluence: list[str] = []

    for e in bias_snap.events:
        if e.side == "bull":
            dir_score += 1.0
        elif e.side == "bear":
            dir_score -= 1.0
        if e.kind in ("BOS", "CHoCH/QM") and e.side != "neutral":
            confluence.append(f"{e.kind} {e.side}")

    # turtle soup searah menambah confluence
    ts = bias_snap.turtle_soup
    if ts and ts.detected and ts.side == "bull":
        dir_score += 0.5
        confluence.append("Turtle soup bull")
    elif ts and ts.detected and ts.side == "bear":
        dir_score -= 0.5
        confluence.append("Turtle soup bear")

    # liquidity terdekat: harga dekat BSL (target atas) / SSL (target bawah)
    for z in bias_snap.bisl_tsl:
        if z.side == "BSL" and 0 <= z.distance_points <= 60:
            confluence.append("dekat BSL (target atas)")
        if z.side == "SSL" and 0 <= z.distance_points <= 60:
            confluence.append("dekat SSL (target bawah)")

    price = bias_snap.price
    if dir_score > 0.8 and len(confluence) >= 2:
        sig.action = "buy"
        sig.bias = "bullish"
        sig.entry = round(price, 2)
        sig.stop_loss = round(price - 8, 2)
        sig.take_profit = round(price + 16, 2)
        sig.rationale = (
            "Demo/rule-based: struktur menunjukkan momentum naik dengan "
            "konfluensi beberapa faktor SMC. Ini contoh dari parser struktur, "
            "bukan LLM."
        )
    elif dir_score < -0.8 and len(confluence) >= 2:
        sig.action = "sell"
        sig.bias = "bearish"
        sig.entry = round(price, 2)
        sig.stop_loss = round(price + 8, 2)
        sig.take_profit = round(price - 16, 2)
        sig.rationale = (
            "Demo/rule-based: struktur menunjukkan momentum turun dengan "
            "konfluensi beberapa faktor SMC. Contoh dari parser struktur, bukan LLM."
        )
    else:
        sig.action = "hold"
        sig.bias = "netral"
        sig.confidence = 0.3
        sig.rationale = (
            "Demo/rule-based: struktur tidak cukup konfluen untuk sinyal kuat. "
            "('hold') — kondisi ini normal kalau setup tidak terpenuhi."
        )

    if sig.action != "hold":
        sl = sig.stop_loss
        tp = sig.take_profit
        rr = None
        if sl is not None and tp is not None:
            risk = abs(price - sl)
            reward = abs(tp - price)
            if risk > 0:
                rr = round(reward / risk, 2)
        sig.risk_reward = rr
        sig.confidence = 0.6 if len(confluence) >= 2 else 0.4
        sig.confluence_factors = confluence
        sig.warning = (
            "MODE DEMO — sinyal dari rule-based, BUKAN analisis LLM. "
            "Jangan dipakai untuk trading nyata."
        )
        sig.ok = True

    sig.errors = []
    return sig


def signal_to_dict(sig: Signal) -> dict[str, Any]:
    return {
        "ok": sig.ok,
        "instruments": sig.instruments,
        "generated_utc": sig.generated_utc,
        "model": sig.model,
        "bias": sig.bias,
        "action": sig.action,
        "confidence": sig.confidence,
        "entry": sig.entry,
        "stop_loss": sig.stop_loss,
        "take_profit": sig.take_profit,
        "risk_reward": sig.risk_reward,
        "confluence_factors": sig.confluence_factors,
        "rationale": sig.rationale,
        "warning": sig.warning,
        "errors": sig.errors,
    }
