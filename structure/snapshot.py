"""Membangun packet terstruktur yang dikirim ke LLM.

Menggabungkan snapshot struktur dari timeframe bias (HTF) + timeframe entry
(LTF) + metadata penting (jam UTC, konteks waktu untuk CRT/TS) agar model
mendapatkan konteks multi-timeframe & time yang KB tekankan.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from structure.market import MarketSnapshot


def _ser(snap: MarketSnapshot) -> dict:
    d = asdict(snap)
    # bersihkan nilai None supaya rapi di JSON
    out = {k: v for k, v in d.items() if v is not None}
    return out


def build_llm_packet(
    bias_snap: MarketSnapshot,
    entry_snap: MarketSnapshot | None,
    *,
    instrument: str = "XAU_USD",
    now: datetime | None = None,
) -> str:
    """Bangun teks JSON utuh yang akan jadi input/user context untuk LLM."""
    now = now or datetime.now(timezone.utc)
    packet = {
        "metadata": {
            "instrument": instrument,
            "generated_utc": now.isoformat(),
            "utc_hour": now.hour,
            "utc_weekday": now.strftime("%A"),
            "bias_timeframe": bias_snap.timeframe,
            "entry_timeframe": entry_snap.timeframe if entry_snap else None,
            "note": (
                "Waktu & hari UTC disertakan untuk penilaian CRT/Turtle Soup "
                "dan Daily Bias (jam-jam spesifik yang disebutkan knowledge base)."
            ),
        },
        "bias_structure": _ser(bias_snap),
    }
    if entry_snap is not None:
        packet["entry_structure"] = _ser(entry_snap)
    return json.dumps(packet, ensure_ascii=False, indent=2)
