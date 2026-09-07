"""Dukascopy XAU/USD candle NYATA gratis (tanpa akun/API key).

Sumber data biner `.bi5` history feed publik Dukascopy:
  https://datafeed.dukascopy.com/datafeed/XAUUSD/YYYY/<bulan-0>/<hari>/BID_candles_*.bi5

Baris tiap bar: int big-endian:
  4 byte waktu (unix detik) + O / H / L / C (masing2 4 byte, harga * 10^-5)
  + opsional 4 byte volume (total 20 atau 24 byte/bar).

Sama seperti provider lain: DataFrame index datetime, kolom
open/high/low/close/volume/complete.
"""
from __future__ import annotations

import datetime as dt
import json
import socket
import struct
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

BASE = "https://datafeed.dukascopy.com/datafeed/XAUUSD"

_FILE = {
    "M5": "BID_candles_min_5.bi5",
    "M15": "BID_candles_min_15.bi5",
    "H1": "BID_candles_hour_1.bi5",
    "H4": "BID_candles_hour_1.bi5",  # digabung dari 1h
    "D": "BID_candles_day_1.bi5",
    "W": "BID_candles_week_n.bi5",
}

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

_PRICE_SCALE = 1e-5



def _preflight(host: str = "datafeed.dukascopy.com", timeout: float = 2.0) -> None:
    """Cek cepat apakah TCP ke host Dukascopy menjangkau; kalau tidak -> abort cepat."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, 443))
    except OSError as e:
        raise FreeDataError(f"Dukascopy tak terjangkau dari IP ini ({e.strerror or e})") from e
    finally:
        sock.close()

_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_HOLD = {"M5": 60, "M15": 120, "H1": 300, "H4": 600, "D": 1800, "W": 3600}

_PERIOD_SEC = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D": 86400, "W": 604800}


class FreeDataError(Exception):
    pass


class UnsupportedTimeframeError(FreeDataError):
    pass


_SPOT_SOURCES = [
    "https://api.gold-api.com/price/XAU",
    "https://data-asg.goldprice.org/dbXRates/USD",
]


def free_spot() -> dict:
    """Harga spot XAU/USD NYATA tanpa akun — sumber paling andal dari bebas.

    Sumber: gold-api.com (primer) -> goldprice.org (fallback). Kena blokir
    tak masalah, cukup pakai sumber yang lain.
    """
    for url in _SPOT_SOURCES:
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if "gold-api" in url:
                price = float(payload["price"])
                ts = payload.get("updatedAt", "")
                src = "gold-api.com"
            else:
                price = float(payload["items"][0]["xauPrice"])
                ts = payload.get("ts", "")
                src = "goldprice.org"
            return {
                "price": round(price, 2),
                "updated_at": ts,
                "source": src,
            }
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            continue
    raise FreeDataError("Semua sumber spot gagal")


def _tf(s: str) -> str:
    return s.upper()


def _bi5_url(y: int, m0: int, d: int, frame: str) -> str:
    # m0 = bulan 0-indexed (Jan=0), tidak ada padding
    return f"{BASE}/{y}/{m0}/{d}/{_FILE[frame]}"


def _fetch_day(y: int, m0: int, d: int, frame: str) -> pd.DataFrame:
    req = urllib.request.Request(_bi5_url(y, m0, d, frame), headers=_UA)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read()

    if len(raw) < 20:
        raise FreeDataError(f"{y}-{m0+1}-{d}: file terlalu kecil ({len(raw)}B)")

    row = 24 if len(raw) % 24 == 0 else 20
    n = len(raw) // row
    out: list[tuple] = []
    for i in range(n):
        chunk = raw[i * row : (i + 1) * row]
        ts, o, h, l, c = struct.unpack(">IIIII", chunk[:20])
        # Abaikan bar "kosong" Dukascopy (timestamp 0 atau harga 0)
        if ts == 0 or o == 0 or h == 0 or l == 0 or c == 0:
            continue
        # Dukascopy timestamp = unix epoch detik (UTC)
        out.append((ts, o * _PRICE_SCALE, h * _PRICE_SCALE, l * _PRICE_SCALE, c * _PRICE_SCALE))

    if not out:
        raise FreeDataError(f"{y}-{m0+1}-{d}: tanpa bar valid")

    df = pd.DataFrame(out, columns=["ts", "open", "high", "low", "close"]).drop_duplicates("ts")
    df.index = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.drop(columns=["ts"]).sort_index()
    df["volume"] = 0
    df["complete"] = True
    return df


def _dates_needed(tf: str, count: int) -> list[tuple[int, int, int]]:
    """Daftar hari kalender (UTC) yang meliputi `count` bar timeframe."""
    period = _PERIOD_SEC[tf]
    total_needed = count * period
    days: list[tuple[int, int, int]] = []
    day = dt.datetime.now(dt.timezone.utc).date()
    gathered = 0
    guard = 0
    while gathered < total_needed and guard < 120:
        if tf == "W":
            # ambil per minggu: cukup ambil hari Senin
            if day.weekday() == 0:
                days.append((day.year, day.month - 1, day.day))
        elif tf == "D":
            days.append((day.year, day.month - 1, day.day))
        else:
            days.append((day.year, day.month - 1, day.day))
            # intraday: 8 jam sauang padat per hari => anggap ~6 bar/jam aktual
            gathered += period * 6
        if tf in ("D", "W"):
            gathered += period
        day -= dt.timedelta(days=1)
        guard += 1
    return days


def _combine(tf: str, count: int) -> pd.DataFrame:
    days = _dates_needed(tf, count)[::-1]  # naik (dulu -> kini)
    frames: list[pd.DataFrame] = []
    consecutive_fail = 0
    tried = 0
    for y, m0, d in days:
        tried += 1
        try:
            frames.append(_fetch_day(y, m0, d, tf))
            consecutive_fail = 0
        except (FreeDataError, OSError) as e:
            consecutive_fail += 1
            print(f"  [free] lewati {y}-{m0+1}-{d}: {e}")
            # Fail-fast: IP kemungkinan diblokir sumber data.
            if consecutive_fail >= 6 or tried >= 24:
                break
            continue
        if tried >= 24:
            break
    if not frames:
        raise FreeDataError("Tidak ada satu hari pun berhasil diunduh")
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]

    if tf == "H4":
        df = df.resample("4h").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "complete": "last"}
        ).dropna(subset=["open"])
    if tf == "W":
        df = df.resample("W").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "complete": "last"}
        ).dropna(subset=["open"])

    return df.tail(count)


def free_client_fetch(
    instrument: str = "XAU_USD",
    granularity: str = "H1",
    count: int = 200,
) -> pd.DataFrame:
    """Padanan `OandaClient.fetch_candles` — data NYATA gratis.

    Urutan coba: TradingView (best-effort) -> Dukascopy. Semua gagal ->
    FreeDataError (real mode menampilkan error jujur + harga spot).
    """
    tf = _tf(granularity)
    if tf not in _FILE:
        raise UnsupportedTimeframeError(f"Timeframe tidak didukung: {tf}")

    key = f"{instrument}:{tf}:{count}"
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < _HOLD.get(tf, 120):
        return cached[1].copy()

    # 1) TradingView (preferensi user)
    try:
        from data.tradingview import tradingview_client_fetch

        df = tradingview_client_fetch(instrument, tf, count)
        _cache[key] = (time.time(), df)
        return df
    except (FreeDataError, OSError, ValueError) as e:
        print(f"  [free] TradingView gagal: {e}")

    # 2) Dukascopy (fallback biner publik)
    _preflight()
    df = _combine(tf, count)
    _cache[key] = (time.time(), df)
    return df