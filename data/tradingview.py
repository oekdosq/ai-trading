"""Provider candle XAU/USD via TradingView (tanpa akun).

Menggunakan websocket data internal TradingView (protocol socket.io chart).
  wss://data.tradingview.com/socket.io/websocket?from=chart&type=chart

Alur (pola komunitas, banyak dipakai):
  chart_create_session -> resolve_symbol (symbol=OANDA:XAUUSD dsb)
    -> create_series (resolution map) -> load_studies
  Data historis tiba sebagai pesan `du`; bar OHLC dikumpulkan & digabung.

Catatan: TradingView kadang membatasi IP datacenter. Provider ini best-effort:
gagal -> dengan cepat naikkan FreeDataError sehingga rantai lanjut ke provider
berikutnya (Dukascopy) atau fallback spot + error jujur.
"""
from __future__ import annotations

import asyncio
import json
import random
import time

import pandas as pd

try:  # websockets adalah dep kecil untuk provider opsional
    import websockets
except ImportError:  # pragma: no cover
    websockets = None

from data.free import FreeDataError  # noqa: E402

_SYMBOLS = ("OANDA:XAUUSD", "TVC:GOLD", "COMEX:GC1!")

_RES = {"M5": "5", "M15": "15", "H1": "60", "H4": "240", "D": "1D", "W": "1W"}

_PERIOD_SEC = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D": 86400, "W": 604800}

_URI = "wss://data.tradingview.com/socket.io/websocket?from=chart&type=chart"
_HEADERS = {
    "Origin": "https://www.tradingview.com",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
}


def _wrap(obj: dict) -> str:
    body = json.dumps(obj, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _few(prefix: str) -> str:
    return prefix + format(random.randrange(16**8), "08x")


def _parse_du(payload: dict) -> pd.DataFrame | None:
    """Ekstrak bar OHLC dari pesan `du` TradingView."""
    v = payload.get("v") or []
    for item in v:
        if not isinstance(item, dict):
            continue
        for key, s in item.items():
            if isinstance(s, dict) and "s" in s and "t" in s:
                t = s.get("t") or []
                o = s.get("o") or []
                h = s.get("h") or []
                l = s.get("l") or []
                c = s.get("c") or []
                if not (t and o and h and l and c and len(t) == len(c)):
                    continue
                n = len(t)
                idx = pd.to_datetime(t, unit="s", utc=True)

                def _clean(arr):
                    return [None if (isinstance(x, str) and x in ("bi", "blocked")) else x for x in arr]

                df = pd.DataFrame(
                    {
                        "open": _clean(o)[:n],
                        "high": _clean(h)[:n],
                        "low": _clean(l)[:n],
                        "close": _clean(c)[:n],
                    },
                    index=idx,
                )
                df = df.dropna(subset=["open", "high", "low", "close"])
                if df.empty:
                    continue
                df["volume"] = 0
                df["complete"] = True
                return df
    return None


async def _fetch_symbol(symbol: str, resolution: str, period_sec: int, count: int, timeout: float) -> pd.DataFrame:
    if websockets is None:
        raise FreeDataError("websockets belum terpasang")

    sid = _few("cs_")
    sub_id = _few("sds_sym_")
    plan = [
        {"m": "chart_create_session", "p": [sid, ""]},
        {"m": "resolve_symbol", "p": [sid, sub_id, f'={{"symbol":"{symbol}","adjustment":"splits"}}']},
        {"m": "create_series", "p": [sid, "sds_1", "s1", sub_id, resolution, ""]},
        {"m": "load_studies", "p": [sid, "", 1, ""]},
    ]

    frames: list[pd.DataFrame] = []
    deadline = time.time() + timeout
    async with websockets.connect(
        _URI, additional_headers=_HEADERS, open_timeout=10, max_size=2**24
    ) as ws:
        for msg in plan:
            await ws.send(json.dumps(msg, separators=(",", ":")))
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.5, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            except websockets.ConnectionClosed as e:
                raise FreeDataError(f"TradingView tutup socket: [{e.code}] {e.reason}")
            if not raw.startswith("~m~"):
                continue
            body = raw.split("~m~", 2)[2]
            try:
                m = json.loads(body)
            except json.JSONDecodeError:
                continue
            if m.get("m") == "du" and len(m.get("p", [])) > 2:
                dfs = _parse_du(m["p"][2])
                if dfs is not None and not dfs.empty:
                    frames.append(dfs)
    if not frames:
        raise FreeDataError(f"{symbol}: tanpa data bar dari socket")

    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.tail(count)
    now_epoch = time.time()
    boundary = now_epoch - (now_epoch % period_sec)
    df["complete"] = (df.index.view("int64") / 1_000_000_000) < boundary
    return df


def tradingview_client_fetch(
    instrument: str = "XAU_USD",
    granularity: str = "H1",
    count: int = 150,
    timeout: float = 9.0,
) -> pd.DataFrame:
    """Padanan fetch_candles — data TradingView, best-effort."""
    tf = granularity.upper()
    resolution = _RES.get(tf)
    if resolution is None:
        raise FreeDataError(f"Timeframe tidak didukung: {tf}")
    if tf == "H4":
        df = asyncio.run(_fetch_symbol(_SYMBOLS[0], "60", _PERIOD_SEC["H1"], count * 4 + 4, timeout))
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "complete": "last"}
        df = df.resample("4h").agg(agg).dropna(subset=["open"]).tail(count)
        return df
    last_err: Exception | None = None
    for symbol in _SYMBOLS:
        try:
            return asyncio.run(_fetch_symbol(symbol, resolution, _PERIOD_SEC[tf], count, timeout))
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise FreeDataError(f"Semua simbol TradingView gagal ({', '.join(_SYMBOLS)}): {last_err}")