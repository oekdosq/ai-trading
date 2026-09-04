"""Indikator pendukung berbasis pandas.

CATATAN: indikator ini BUKAN sinyal utama. Sinyal berasal dari analisis
struktur Smart Money Concepts + konfirmasi LLM. Indikator di sini hanya
pendukung (ATR untuk jarak SL/TP, EMA untuk konteks tren, fractal untuk
menemukan swing points yang dipakai parser struktur).
"""
from __future__ import annotations

import pandas as pd


def add_ema(df: pd.DataFrame, span: int = 50) -> pd.DataFrame:
    """Tambahkan kolom ema_{span}."""
    df = df.copy()
    df[f"ema_{span}"] = df["close"].ewm(span=span, adjust=False).mean()
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average True Range (Wilder)."""
    df = df.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing (alpha = 1/period)
    df[f"atr_{period}"] = tr.ewm(alpha=1 / period, adjust=False).mean()
    return df


def fractal_swings(
    df: pd.DataFrame, left: int = 2, right: int = 2
) -> pd.DataFrame:
    """Deteksi swing high/low (fractal) dengan kiri/kanan `left`/`right` bar.

    Mengembalikan kolom boolean: is_swing_high, is_swing_low.
    """
    df = df.copy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    n = len(df)

    sh = [False] * n
    sl = [False] * n
    for i in range(left, n - right):
        window_h = high[i - left : i + right + 1]
        window_l = low[i - left : i + right + 1]
        if high[i] == window_h.max() and (window_h == window_h.max()).sum() == 1:
            sh[i] = True
        if low[i] == window_l.min() and (window_l == window_l.min()).sum() == 1:
            sl[i] = True

    df["is_swing_high"] = sh
    df["is_swing_low"] = sl
    return df
