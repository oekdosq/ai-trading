"""Generator data XAUUSD SINTETIS untuk mode demo offline.

Menghasilkan harga emas buatan yang menyerupai pergerakan nyata: ada noise
per-bar (sehingga fractal swing bisa terbentuk seperti data sungguhan),
plus pola Smart Money yang disisipkan (impulse, pullback ke level/support,
liquidity) supaya user melihat cara kerja bot TANPA akun OANDA maupun LLM.

INSTRUMENT hanya SIMULASI — bukan data pasar nyata.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_candles(
    instrument: str = "XAU_USD",
    granularity: str = "H1",
    count: int = 200,
    seed: int = 42,
) -> pd.DataFrame:
    """Bangun DataFrame OHLC sintetis menyerupai XAU/USD dengan pola SMC.

    Skema: bangun "drive" harga ber-trend lalu pullback, dengan noise
    per-bar agar fractal swing terbentuk. Ending dibuat smooth supaya
    parser struktur melihat setup yang dapat dinilai.
    """
    rng = np.random.default_rng(seed)
    use_up = seed % 2 == 0
    base = 2300.0 if use_up else 2450.0

    n = count
    # drive: impulse -> pullback -> impulse -> minor fade (seperti SMR)
    seg = [
        ([+6] * int(n * 0.30)),   # impulse naik 30%
        ([-4] * int(n * 0.25)),   # pullback/retest 25%
        ([+5] * int(n * 0.30)),   # lanjut naik 30%
        ([-2] * int(n * 0.15)),   # minor fade / pembentukan 15%
    ]
    steps: list[float] = []
    for s in seg:
        steps.extend(s)
    while len(steps) < n:
        steps.append(steps[-1])
    steps = steps[:n]

    if not use_up:
        steps = [-x for x in steps]

    # log-return style noise per bar (supaya fractal terbentuk)
    per_bar_vol = 12.0
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = noise[i - 1] * 0.15 + rng.normal(0, per_bar_vol * 0.5)
    # scale noise agar tidak mendominasi drive
    noise = noise / 1.5

    drive = np.cumsum(steps)
    close = base + drive + noise
    close = np.maximum(close, 50)  # harga selalu positif

    open_ = np.zeros(n)
    open_[0] = base
    open_[1:] = close[:-1]
    open_ += rng.normal(0, 0.8, n)

    spread = np.abs(rng.normal(2.5, 1.0, n)) + 0.5
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread

    idx = pd.date_range("2026-09-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": rng.integers(100, 5000, n).astype(int),
            "complete": True,
        },
        index=idx,
    ).sort_index()
    return df


def synthetic_client_fetch(
    instrument: str, granularity: str, count: int, seed: int = 42
) -> pd.DataFrame:
    """Padanan `OandaClient.fetch_candles` tapi sepenuhnya sintetis."""
    return synthetic_candles(
        instrument=instrument, granularity=granularity, count=count, seed=seed
    )
