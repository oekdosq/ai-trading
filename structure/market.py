"""Rekonstruksi struktur market dari urutan swing points.

Menerjemahkan konsep Smart Money dari knowledge base menjadi deteksi
berbasis-urutan (sequence), bukan snapshot tunggal. Karena banyak aturan
ditentukan oleh URUTAN kejadian (mis. BOS sebelum vs sesudah take IDM),
logika di sini mementingkan urutan supaya perbedaan SMR 1 vs SMR 2 bisa
dibedakan.

MODEL-DRIVEN: deteksi ini berbasis aturan (rule-based) dari swing points
yang sudah diekstrak. Hasil akhir (apakah level valid / trap / POI yang mana)
tetap diserahterimakan ke LLM sebagai konfirmasi akhir, karena sebagian
konsep membutuhkan penilaian kontekstual/visual.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from structure.swings import Swing, SwingSeries, extract_swings, swing_levels


@dataclass
class StructEvent:
    """Satu peristiwa struktur terdeteksi. kind adalah label SMC."""

    kind: str                       # e.g. 'BOS', 'CHoCH', 'IDM', 'protected_low', ...
    side: str                       # 'bull' | 'bear' | 'neutral'
    at_index: int
    price: float
    detail: str = ""


@dataclass
class LiquidityZone:
    """Level likuiditas (BSL/SSL) terdekat beserta jarak."""

    side: str            # 'BSL' (buy-side) | 'SSL' (sell-side)
    price: float
    distance_points: float
    note: str = ""


@dataclass
class TurtleSoup:
    detected: bool
    side: str = "neutral"        # 'bull' | 'bear'
    from_index: int = -1
    detail: str = ""


@dataclass
class MarketSnapshot:
    """Hasil parse struktur untuk satu frame, siap dikirim ke LLM."""

    timeframe: str
    price: float
    last_candles: list[dict]
    recent_high: Optional[float]
    recent_low: Optional[float]
    events: list[StructEvent] = field(default_factory=list)
    bisl_tsl: list[LiquidityZone] = field(default_factory=list)
    turtle_soup: Optional[TurtleSoup] = None
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    failure_to_displace: Optional[str] = None    # 'bull'|'bear'|None
    levels_resistance: list[float] = field(default_factory=list)
    levels_support: list[float] = field(default_factory=list)


def _close(series: pd.Series) -> list[float]:
    return [float(x) for x in series]


def parse_structure(
    df: pd.DataFrame,
    timeframe: str = "H1",
    left: int = 2,
    right: int = 2,
) -> MarketSnapshot:
    """Bangun MarketSnapshot dari dataframe OHLC untuk satu timeframe."""
    series: SwingSeries = extract_swings(df, left=left, right=right)
    levels = swing_levels(series, lookback=20)
    price = float(df["close"].iloc[-1])

    snap = MarketSnapshot(
        timeframe=timeframe,
        price=price,
        last_candles=[_candle_row(df, i) for i in range(max(0, len(df) - 6), len(df))],
        recent_high=levels["recent_high"],
        recent_low=levels["recent_low"],
        levels_resistance=levels["resistance"],
        levels_support=levels["support"],
    )

    _detect_structure(snap, series)
    _detect_liquidity(snap, series)
    _detect_turtle_soup(snap, df)
    _detect_daily_bias(snap, df)
    return snap


def _candle_row(df: pd.DataFrame, i: int) -> dict:
    r = df.iloc[i]
    return {
        "time": str(df.index[i]),
        "o": round(float(r["open"]), 2),
        "h": round(float(r["high"]), 2),
        "l": round(float(r["low"]), 2),
        "c": round(float(r["close"]), 2),
    }


def _detect_structure(snap: MarketSnapshot, series: SwingSeries) -> None:
    """Deteksi BOS/CHoCH/IDM/protected level dari urutan swing terakhir.

    Aturan kunci SMR (dari KB):
      - BOS setelah swing di-take + retest = level jadi protected (valid).
      - Swing minor (IDM) sebelum lanjut arah = jebakan retail.
      - Urutan BOS vs IDM menentukan valid/trap.
    Dibangun heuristik sederhana berbasis swing terakhir.
    """
    sw = series.swings
    if len(sw) < 4:
        return

    last5 = sw[-5:]
    # klasifikasi arah terakhir: rising jika swing low & high terakhir naik
    highs = series.highs()
    lows = series.lows()
    if len(highs) >= 2 and len(lows) >= 2:
        last_h1, last_h2 = highs[-2].price, highs[-1].price
        last_l1, last_l2 = lows[-2].price, lows[-1].price
        # BOS bullish: high tertembus (harga actual terbaru > high terakhir)
        if snap.price > last_h1:
            snap.events.append(
                StructEvent("BOS", "bull", highs[-1].idx, last_h1,
                            f"harga ({snap.price:.2f}) menembus swing high {last_h1:.2f}")
            )
        if snap.price < last_l1:
            snap.events.append(
                StructEvent("BOS", "bear", lows[-1].idx, last_l1,
                            f"harga ({snap.price:.2f}) menembus swing low {last_l1:.2f}")
            )
        # Higher High / Higher Low progression → struktur bullish
        if last_h2 > last_h1 and last_l2 > last_l1:
            snap.events.append(StructEvent("HH/HL sequence", "bull", sw[-1].idx, snap.price,
                                           "struktur: higher high + higher low"))
        elif last_h2 < last_h1 and last_l2 < last_l1:
            snap.events.append(StructEvent("LH/LL sequence", "bear", sw[-1].idx, snap.price,
                                           "struktur: lower high + lower low"))

    # CHoCH / QM: perubahan karakter — swing terakhir melawan arah dominan
    if len(highs) >= 3 and len(lows) >= 3:
        h = snap.price
        hh = highs[-2].price < highs[-1].price and highs[-1].price < h  # masih uptrend
        ll = lows[-2].price > lows[-1].price and lows[-1].price > h     # downtrend
        # CHoCH bear: harga gagal buat HH baru (high terakhir < high sebelumnya)
        if highs[-1].price < highs[-2].price and h < highs[-2].price:
            snap.events.append(
                StructEvent("CHoCH/QM", "bear", highs[-1].idx, highs[-1].price,
                            "gagal membuat higher high baru")
            )
        if lows[-1].price > lows[-2].price and h > lows[-2].price:
            snap.events.append(
                StructEvent("CHoCH/QM", "bull", lows[-1].idx, lows[-1].price,
                            "gagal membuat lower low baru")
            )

    # IDM (inducement): swing minor berlawanan di dekat harga — kandidat jebakan.
    # Heuristik: swing low yang ditinggalkan dua swing terakhir pada sisi trending.
    if len(lows) >= 2:
        last_low = lows[-1]
        if snap.price > last_low.price:
            snap.events.append(
                StructEvent("IDM (jebakan)", "bull", last_low.idx, last_low.price,
                            f"swing low {last_low.price:.2f} kemungkinan inducement")
            )
    if len(highs) >= 2:
        last_high = highs[-1]
        if snap.price < last_high.price:
            snap.events.append(
                StructEvent("IDM (jebakan)", "bear", last_high.idx, last_high.price,
                            f"swing high {last_high.price:.2f} kemungkinan inducement")
            )


def _detect_liquidity(snap: MarketSnapshot, series: SwingSeries) -> None:
    """Level BSL/SSL terdekat berdasarkan recent swing high/low."""
    if snap.recent_high is not None:
        dist = round(snap.recent_high - snap.price, 2)
        snap.bisl_tsl.append(
            LiquidityZone("BSL", snap.recent_high, dist,
                          "buy-side liquidity pada swing high terakhir")
        )
    if snap.recent_low is not None:
        dist = round(snap.price - snap.recent_low, 2)
        snap.bisl_tsl.append(
            LiquidityZone("SSL", snap.recent_low, dist,
                          "sell-side liquidity pada swing low terakhir")
        )


def _detect_turtle_soup(snap: MarketSnapshot, df: pd.DataFrame) -> None:
    """CRT / Turtle Soup: wick menembus range tapi close kembali.

    Heuristik: candle terakhir punya wick signifikan > X% body menuju arah
    di luar range 3 candle sebelumnya. Ditandai, final diputuskan LLM.
    """
    if len(df) < 4:
        snap.turtle_soup = TurtleSoup(False)
        return
    last = df.iloc[-1]
    prev = df.iloc[-4:-1]
    rng_hi = float(prev["high"].max())
    rng_lo = float(prev["low"].min())
    body = abs(float(last["close"]) - float(last["open"]))
    if body <= 0:
        snap.turtle_soup = TurtleSoup(False)
        return
    up_wick = float(last["high"]) - max(float(last["close"]), float(last["open"]))
    dn_wick = min(float(last["close"]), float(last["open"])) - float(last["low"])
    # bearish turtle soup: wick atas besar, harga tembus rng_hi lalu close balik
    if up_wick > 0.6 * body and float(last["high"]) > rng_hi:
        snap.turtle_soup = TurtleSoup(True, "bear", idx_from(df, last),
                                      "wick menembus atas range tapi close balik (TS bear)")
    elif dn_wick > 0.6 * body and float(last["low"]) < rng_lo:
        snap.turtle_soup = TurtleSoup(True, "bull", idx_from(df, last),
                                      "wick menembus bawah range tapi close balik (TS bull)")
    else:
        snap.turtle_soup = TurtleSoup(False)


def idx_from(df: pd.DataFrame, row: pd.Series) -> int:
    try:
        return int(df.index.get_loc(row.name))
    except Exception:  # noqa: BLE001
        return len(df) - 1


def _detect_daily_bias(snap: MarketSnapshot, df: pd.DataFrame) -> None:
    """Daily Bias dasar: PDH/PDL dari hari sebelumnya + failure to displace."""
    if df.index.tz is None:
        daily = df.copy()
    else:
        daily = df.tz_convert("UTC")
    days = daily.groupby(daily.index.date)
    frames = list(days)
    if len(frames) < 2:
        return
    prev_day = frames[-2][1]
    snap.pdh = round(float(prev_day["high"].max()), 2)
    snap.pdl = round(float(prev_day["low"].min()), 2)
    if snap.pdh is None or snap.pdl is None:
        return
    # failure to displace: harga menyentuh PDH/PDL tapi close tidak jauh menembus
    last = df.iloc[-1]
    if snap.price > snap.pdh and float(last["close"]) <= snap.pdh * 1.0005:
        snap.failure_to_displace = "bull"
    elif snap.price < snap.pdl and float(last["close"]) >= snap.pdl * 0.9995:
        snap.failure_to_displace = "bear"
