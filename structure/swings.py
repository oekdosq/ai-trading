"""Ekstraksi swing points & level dari candle OHLC.

Ini lapisan paling dasar parser struktur. Semua konsep Smart Money
(swing, BOS, IDM, liquidity) dibangun di atas daftar swing yang
dihasilkan di sini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from data.indicators import fractal_swings


@dataclass
class Swing:
    """Satu swing point (fractal) pada frame tertentu."""

    idx: int                 # posisi di dataframe asli (berurutan)
    time: Optional[pd.Timestamp]
    price: float
    kind: str                # 'high' | 'low'
    strength: int = 1        # jumlah bar kiri/kanan (lebih besar = lebih kuat)


@dataclass
class SwingSeries:
    """Urutan swing points dari suatu timeframe."""

    swings: list[Swing] = field(default_factory=list)

    def highs(self) -> list[Swing]:
        return [s for s in self.swings if s.kind == "high"]

    def lows(self) -> list[Swing]:
        return [s for s in self.swings if s.kind == "low"]

    def last_n(self, n: int) -> list[Swing]:
        return self.swings[-n:]

    @property
    def last(self) -> Optional[Swing]:
        return self.swings[-1] if self.swings else None


def extract_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> SwingSeries:
    """Bangun SwingSeries dari dataframe OHLC.

    Pakai fractal detection dari data.indicators. Hanya bar 'complete'
    yang dipertimbangkan agar swing di ujung kanan tidak berubah-ubah.
    """
    df = fractal_swings(df, left=left, right=right)
    series = SwingSeries()
    for i in range(len(df)):
        row = df.iloc[i]
        if bool(row["is_swing_high"]):
            series.swings.append(
                Swing(idx=int(i), time=df.index[i], price=float(row["high"]), kind="high", strength=left)
            )
        if bool(row["is_swing_low"]):
            series.swings.append(
                Swing(idx=int(i), time=df.index[i], price=float(row["low"]), kind="low", strength=left)
            )
    return series


def swing_levels(series: SwingSeries, lookback: int = 20) -> dict[str, list[float]]:
    """Level support/resistance sederhana dari swing terbaru.

    Mengembalikan {'resistance': [...], 'support': [...], 'recent_high': float,
    'recent_low': float}. Bukan klaim SMC penuh — hanya konteks untuk LLM.
    """
    hs = series.highs()[-lookback:]
    ls = series.lows()[-lookback:]
    res = sorted({round(h.price, 2) for h in hs}, reverse=True)
    sup = sorted({round(l.price, 2) for l in ls})
    recent_high = max((h.price for h in hs), default=None)
    recent_low = min((l.price for l in ls), default=None)
    return {
        "resistance": res,
        "support": sup,
        "recent_high": recent_high,
        "recent_low": recent_low,
    }
