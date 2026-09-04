"""CLI semi-otomatis untuk AI Trading XAUUSD (Smart Money Concept).

Bot CUKUP memberi sinyal/rekomendasi — MANUSIA yang mengeksekusi order.
Tidak ada eksekusi order otomatis di aplikasi ini.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from config import config

app = typer.Typer(add_completion=False, no_args_is_help=True)

OUT_DIR = Path(__file__).resolve().parent / "out"
SIGNAL_DIR = Path(__file__).resolve().parent / "signals"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.command()
def fetch(
    instrument: str = "auto",
    timeframe: str = "auto",
    count: int = 0,
    save: bool = True,
) -> None:
    """Tarik candle XAU/USD dari OANDA practice dan simpan ke out/."""
    from data.oanda import OandaClient, OandaError, load_candles

    instrument = instrument if instrument != "auto" else config.INSTRUMENT
    timeframe = timeframe if timeframe != "auto" else config.TIMEFRAME_BIAS
    count = count if count > 0 else config.CANDLE_COUNT

    if not config.has_oanda:
        typer.echo(
            "ERROR: OANDA_TOKEN/OANDA_ACCOUNT_ID belum diisi di .env "
            "(pakai akun demo/practice).", err=True
        )
        raise typer.Exit(code=1)

    try:
        client = OandaClient(
            config.OANDA_TOKEN, config.OANDA_ACCOUNT_ID, config.OANDA_ENV
        )
        df = load_candles(client, instrument=instrument, granularity=timeframe, count=count)
    except OandaError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(code=1) from e

    typer.echo(
        f"Fetched {len(df)} candle {instrument} {timeframe} "
        f"({df.index[0]:%Y-%m-%d %H:%M} → {df.index[-1]:%Y-%m-%d %H:%M})"
    )

    if save:
        OUT_DIR.mkdir(exist_ok=True)
        path = OUT_DIR / f"{instrument}_{timeframe}.csv"
        df.round(5).to_csv(path)
        typer.echo(f"Disimpan → {path}")


def _load_snapshot(
    instrument: str, tf: str, count: int, client
) -> tuple:
    from data.oanda import load_candles
    from structure.market import parse_structure

    df = load_candles(client, instrument=instrument, granularity=tf, count=count)
    return parse_structure(df, tf)


@app.command()
def analyze(
    instrument: str = "auto",
    bias_tf: str = "auto",
    entry_tf: str = "auto",
    count: int = 0,
    save: bool = True,
    demo: bool = False,
) -> None:
    """Analisis struktur + LLM → sinyal (semi-otomatis, tidak eksekusi).

    --demo: pakai data sintetis + sinyal rule-based (tanpa OANDA & Ollama).
    """
    from ai.analyzer import build_signal, fallback_signal, signal_to_dict
    from ai.llm import LlmUnavailable
    from data.oanda import OandaClient, OandaError

    instrument = instrument if instrument != "auto" else config.INSTRUMENT
    bias_tf = bias_tf if bias_tf != "auto" else config.TIMEFRAME_BIAS
    entry_tf = entry_tf if entry_tf != "auto" else config.TIMEFRAME_ENTRY
    count = count if count > 0 else config.CANDLE_COUNT

    if demo:
        _run_demo_analyze(instrument, bias_tf, entry_tf, count, save)
        return

    if not config.has_oanda:
        typer.echo(
            "ERROR: OANDA_TOKEN/OANDA_ACCOUNT_ID belum diisi di .env.\n"
            "       (Atau pakai `--demo` untuk mode offline sintetis.)", err=True
        )
        raise typer.Exit(code=1)

    try:
        client = OandaClient(
            config.OANDA_TOKEN, config.OANDA_ACCOUNT_ID, config.OANDA_ENV
        )
        bias = _load_snapshot(instrument, bias_tf, count, client)
        typer.echo(f"Struktur bias ({bias_tf}) ok — {len(bias.last_candles)} candle.")
        entry = None
        if entry_tf and entry_tf != bias_tf:
            entry = _load_snapshot(instrument, entry_tf, int(count / 2) or 120, client)
            typer.echo(f"Struktur entry ({entry_tf}) ok.")
    except OandaError as e:
        typer.echo(f"ERROR data: {e}", err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"Memanggil LLM lokal ({config.OLLAMA_MODEL})…")
    llm = LlmClient()
    try:
        sig = build_signal(bias, entry, instrument=instrument, llm=llm)
    except LlmUnavailable as e:
        typer.echo(f"⚠ {e}\n→ Fallback: pakai sinyal rule-based (coba `--demo`).", err=True)
        sig = fallback_signal(bias, entry, instrument=instrument)
    _print_signal(sig)

    if sig.ok and save:
        SIGNAL_DIR.mkdir(exist_ok=True)
        name = f"{instrument}_{bias_tf}_{_now()[:16].replace(':','')}.json"
        (SIGNAL_DIR / name).write_text(
            json.dumps(signal_to_dict(sig), ensure_ascii=False, indent=2)
        )
        typer.echo(f"\nSinyal tersimpan → signals/{name}")


def _run_demo_analyze(
    instrument: str, bias_tf: str, entry_tf: str, count: int, save: bool
) -> None:
    """Mode offline: data sintetis + fallback rule-based."""
    from data.synthetic import synthetic_client_fetch
    from structure.market import parse_structure
    from ai.analyzer import fallback_signal, signal_to_dict

    typer.echo("[DEMO OFFLINE] Memakai data SINTETIS — bukan data pasar nyata.\n")
    df = synthetic_client_fetch(instrument, bias_tf.lower(), count)
    bias = parse_structure(df, bias_tf)
    entry = None
    if entry_tf and entry_tf != bias_tf:
        df2 = synthetic_client_fetch(instrument, entry_tf.lower(), max(120, count // 2))
        entry = parse_structure(df2, entry_tf)

    sig = fallback_signal(bias, entry, instrument=instrument)
    _print_signal(sig)

    if sig.ok and save:
        SIGNAL_DIR.mkdir(exist_ok=True)
        name = f"{instrument}_{bias_tf}_demo_{_now()[:16].replace(':','')}.json"
        (SIGNAL_DIR / name).write_text(
            json.dumps(signal_to_dict(sig), ensure_ascii=False, indent=2)
        )
        typer.echo(f"\nSinyal demo tersimpan → signals/{name}")


@app.command()
def watch(
    interval: int = 60,
    runs: int = 0,
    instrument: str = "auto",
    bias_tf: str = "auto",
    entry_tf: str = "auto",
    demo: bool = False,
) -> None:
    """Auto-refresh analisis tiap `interval` detik (tanpa eksekusi).

    Tekan Ctrl+C untuk berhenti. Bot hanya menampilkan rekomendasi.
    --demo: mode offline sintetis (tanpa OANDA & Ollama).
    """
    import time

    from data.oanda import OandaClient
    from ai.analyzer import build_signal, fallback_signal, signal_to_dict
    from ai.llm import LlmClient, LlmUnavailable
    from data.synthetic import synthetic_client_fetch
    from structure.market import parse_structure

    instrument = instrument if instrument != "auto" else config.INSTRUMENT
    bias_tf = bias_tf if bias_tf != "auto" else config.TIMEFRAME_BIAS
    entry_tf = entry_tf if entry_tf != "auto" else config.TIMEFRAME_ENTRY

    if not demo and not config.has_oanda:
        typer.echo(
            "ERROR: OANDA credentials belum diisi di .env. (Atau pakai `--demo`.)",
            err=True,
        )
        raise typer.Exit(code=1)

    client = OandaClient(config.OANDA_TOKEN, config.OANDA_ACCOUNT_ID, config.OANDA_ENV) if not demo and config.has_oanda else None
    llm = LlmClient()
    n = 0
    try:
        while runs == 0 or n < runs:
            n += 1
            tag = "[DEMO]" if demo else ""
            typer.echo(f"\n===== Analisis #{n} {tag} — {_now()} [{instrument} {bias_tf}] =====")
            if demo:
                df = synthetic_client_fetch(instrument, bias_tf.lower(), config.CANDLE_COUNT, seed=42 + n)
                bias = parse_structure(df, bias_tf)
                entry = None
                if entry_tf and entry_tf != bias_tf:
                    df2 = synthetic_client_fetch(instrument, entry_tf.lower(), 150, seed=42 + n)
                    entry = parse_structure(df2, entry_tf)
                sig = fallback_signal(bias, entry, instrument=instrument)
            else:
                bias = _load_snapshot(instrument, bias_tf, config.CANDLE_COUNT, client)
                entry = None
                if entry_tf and entry_tf != bias_tf:
                    entry = _load_snapshot(instrument, entry_tf, 150, client)
                try:
                    sig = build_signal(bias, entry, instrument=instrument, llm=llm)
                except LlmUnavailable as e:
                    typer.echo(f"⚠ {e}", err=True)
                    sig = fallback_signal(bias, entry, instrument=instrument)
            _print_signal(sig)
            SIGNAL_DIR.mkdir(exist_ok=True)
            name = f"{instrument}_{bias_tf}_watch_{_now()[:16].replace(':','')}.json"
            (SIGNAL_DIR / name).write_text(
                json.dumps(signal_to_dict(sig), ensure_ascii=False, indent=2)
            )
            if runs and n >= runs:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nDihentikan oleh user.")


def _print_signal(sig) -> None:
    """Cetak sinyal dalam format ringkas untuk manusia."""
    if not sig.ok:
        typer.echo("Tidak menghasilkan sinyal valid:")
        for e in sig.errors:
            typer.echo(f"  - {e}")
        return
    arrow = {"buy": "▲ BUY", "sell": "▼ SELL", "hold": "● HOLD"}.get(sig.action, "HOLD")
    typer.echo(f"\n  Aksi      : {arrow} | Bias: {sig.bias} | Confidence: {sig.confidence:.2f}")
    if sig.entry is not None:
        typer.echo(f"  Entry     : {sig.entry}")
    if sig.stop_loss is not None:
        typer.echo(f"  Stop Loss : {sig.stop_loss}")
    if sig.take_profit is not None:
        typer.echo(f"  Take Profit: {sig.take_profit}")
    if sig.risk_reward is not None:
        typer.echo(f"  Risk/Reward: {sig.risk_reward}")
    if sig.confluence_factors:
        typer.echo("  Konfluensi : " + ", ".join(sig.confluence_factors))
    if sig.rationale:
        typer.echo(f"  Alasan     : {sig.rationale}")
    if sig.warning:
        typer.echo(f"  ⚠ Peringatan: {sig.warning}")
    typer.echo(
        "\n  [DISCLAIMER] Ini REKOMENDASI analisis, bukan jaminan profit. "
        "Eksekusi order sepenuhnya keputusan & tanggung jawab Anda."
    )


@app.command()
def signal() -> None:
    """Tampilkan sinyal terakhir yang disimpan (atau kosong)."""
    files = sorted(SIGNAL_DIR.glob("*.json"))
    if not files:
        typer.echo("Belum ada sinyal tersimpan.")
        raise typer.Exit(code=0)
    last = files[-1]
    typer.echo(f"Sinyal terakhir: {last.name}\n")
    typer.echo(Path(last).read_text())


if __name__ == "__main__":
    app()
