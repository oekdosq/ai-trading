"""Wrapper OANDA v20 (oandapyV20) untuk fetch candle harga XAU/USD.

Hanya membaca data (read-only). Tidak ada eksekusi order — bot ini
semi-otomatis, manusia yang mengeksekusi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from oandapyV20 import API
from oandapyV20.endpoints import instruments


@dataclass
class OandaError(Exception):
    message: str


@dataclass
class OandaClient:
    """Client yang sengaja tidak menyimpan token, hanya memakai API object."""

    token: str
    account_id: str
    env: str = "practice"

    def __post_init__(self) -> None:
        self._api = API(access_token=self.token, environment=self.env)

    def fetch_candles(
        self,
        instrument: str = "XAU_USD",
        granularity: str = "H1",
        count: int = 400,
    ) -> pd.DataFrame:
        """Ambil candle historis dan kembalikan DataFrame indexed by time.

        Kolom: time, open, high, low, close, volume, complete
        """
        params: dict[str, Any] = {
            "granularity": granularity,
            "count": min(count, 5000),
        }
        req = instruments.InstrumentsCandles(
            instrument=instrument, params=params
        )
        try:
            self._api.request(req)
        except Exception as e:  # noqa: BLE001
            raise OandaError(f"Gagal fetch candle: {e}") from e

        candles = req.response.get("candles", [])
        if not candles:
            raise OandaError("Tidak ada candle yang dikembalikan OANDA.")

        rows: list[dict[str, Any]] = []
        for c in candles:
            m = c["mid"]
            rows.append(
                {
                    "time": c["time"],
                    "open": float(m["o"]),
                    "high": float(m["h"]),
                    "low": float(m["l"]),
                    "close": float(m["c"]),
                    "volume": int(c.get("volume", 0)),
                    "complete": c.get("complete", False),
                }
            )
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time").sort_index()
        return df


def load_candles(
    client: OandaClient | None = None,
    instrument: str = "XAU_USD",
    granularity: str = "H1",
    count: int = 400,
) -> pd.DataFrame:
    """Helper: buat client default dari config kalau perlu."""
    if client is None:
        from config import config

        if not config.has_oanda:
            raise OandaError(
                "OANDA_TOKEN/OANDA_ACCOUNT_ID belum diisi di .env "
                "(pakai akun demo/practice)."
            )
        client = OandaClient(config.OANDA_TOKEN, config.OANDA_ACCOUNT_ID, config.OANDA_ENV)
    return client.fetch_candles(instrument=instrument, granularity=granularity, count=count)
