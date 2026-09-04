#!/usr/bin/env bash
# Jalankan web app AI Trading XAUUSD di localhost:8000
# Mode dev: pakai --reload. Untuk produksi set WEB_SECRET di .env.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Membuat virtual env..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

# Baca WEB_SECRET dari .env kalau ada (jangan wajib untuk dev)
if [ -f .env ]; then
  set -a; source .env; set +a
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "Menjalankan AI Trading XAUUSD → http://localhost:${PORT}"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
