# AI Trading XAUUSD — Smart Money Concept (Semi-Otomatis)

Bot **semi-otomatis** khusus **XAU/USD** berbasis **Smart Money Concept (SMC)**.
Bot mengunduh data harga dari **OANDA practice (demo)**, mengekstrak struktur
market (swing, BOS/CHoCH, IDM, BSL/SSL, POI), lalu menganalisis dengan
**LLM lokal (Ollama)** untuk menghasilkan sinyal rekomendasi.

> ⚠️ **DISCLAIMER PENTING**
> Bot ini **HANYA memberikan rekomendasi/analisis**. Ia **TIDAK pernah
> mengeksekusi order** — baik otomatis maupun atas nama Anda. Semua keputusan
> dan eksekusi trading sepenuhnya di tangan Anda dan menjadi tanggung jawab
> Anda sendiri. Trading berisiko tinggi; bisa menyebabkan kehilangan modal.
> Ini bukan jaminan profit. Gunakan akun **demo/practice** terlebih dahulu.
> DYOR (Do Your Own Research).

---

## Cara kerja (pipeline)

```
OANDA practice (XAU_USD)
        │  fetch candle (HTF bias H1 + LTF entry M15)
        ▼
structure/  — ekstraksi struktur SMC
   swings.py     → swing high/low (fractal)
   market.py     → BOS/CHoCH/IDM/protected level/BSL-SSL/Turtle Soup/Daily Bias
   snapshot.py   → gabung snapshot HTF+LTF jadi packet JSON untuk LLM
        ▼
ai/  — analisis LLM lokal
   prompt.py     → system prompt SMC (dari knowledge base) + output JSON
   llm.py        → client Ollama (gratis, offline) + retry
   analyzer.py   → panggil LLM, VALIDASI & normalisasi output JSON
        ▼
sinyal   →  { action, confidence, entry, stop_loss, take_profit, rationale }
            (Bahasa Indonesia) — di-TAMPILKAN untuk Anda, TIDAK dieksekusi
```

## Knowledge Base
Konsep yang dipakai bersumber dari `knowledbase` Smart Money Concept:
SMR (Swing Market Reversal) Model 1&2, MSNR Trendlines, QMX/QM+TL, CRT
(Candle Range Theory) / PO3 / Turtle Soup, MSS vs CISD, Daily Bias (PDH/PDL),
dan Algorithm Ratio. Poin kunci: **urutan struktur** (BOS sebelum/sesudah
take IDM menentukan valid-protek vs trap) dan **confluence** (≥2-3 faktor).

---

## Mode Demo (tanpa OANDA & Ollama)

Bot punya **mode demo offline** — memakai data XAU/USD **sintetis** dan
sinyal **rule-based** dari parser struktur. Kamu bisa langsung melihat cara
kerja bot, bentuk output sinyal, dan struktur parser **tanpa** perlu akun
OANDA maupun menjalankan Ollama.

```bash
# langkah 1 & 2 di bawah masih perlu biar semua modul jalan
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# analisis demo sekali
python cli.py analyze --demo

# watch demo (auto-refresh, tanpa eksekusi)
python cli.py watch --demo --interval 60 --runs 5
```

Contoh keluaran `analyze --demo`:

```
[DEMO OFFLINE] Memakai data SINTETIS — bukan data pasar nyata.

  Aksi      : ▼ SELL | Bias: bearish | Confidence: 0.60
  Entry     : 3102.33
  Stop Loss : 3110.33
  Take Profit: 3086.33
  Risk/Reward: 2.0
  Konfluensi : BOS bear, CHoCH/QM bear, Turtle soup bull
  Alasan     : Demo/rule-based: struktur menunjukkan momentum turun dengan konfluensi beberapa faktor SMC...
  ⚠ Peringatan: MODE DEMO — sinyal dari rule-based, BUKAN analisis LLM. Jangan dipakai untuk trading nyata.

  [DISCLAIMER] Ini REKOMENDASI analisis, bukan jaminan profit. Eksekusi order sepenuhnya keputusan & tanggung jawab Anda.
```

> ⚠️ Mode demo memakai data **sintetis** dan logika **rule-based** sebagai
> pengganti sementara LLM. Ini untuk pengenalan/kasus uji — bukan untuk
> trading nyata. Untuk analisis sebenarnya, pakai mode default (OANDA + Ollama).

---

## Setup

1. **Python 3.10+** dan buat virtual env:
   ```bash
   cd ai-trading
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **OANDA practice (demo)** — gratis:
   - Daftar akun demo: https://www.oanda.com/demo-account/
   - Dapatkan `Access Token` & `Account ID` dari dashboard OANDA.
   - Salin `.env.example` → `.env` dan isi:
     ```bash
     cp .env.example .env
     # lalu edit .env
     ```
   > Token jangan pernah di-commit (`.gitignore` sudah memuat `.env`).

3. **Ollama (LLM lokal, gratis)**:
   ```bash
   # install Ollama: https://ollama.com
   ollama serve          # nyalakan server
   ollama pull qwen3:8b  # model default (bisa diganti di .env → OLLAMA_MODEL)
   ```

---

## Usage

```bash
# 1. Tarik & simpan data candle (tes koneksi OANDA)
python cli.py fetch

# 2. Analisis sekali → tampilkan sinyal (dan simpan ke signals/)
python cli.py analyze

# 3. Auto-refresh tiap interval (mis. tiap 2 menit), tanpa eksekusi
python cli.py watch --interval 120

# 4. Lihat sinyal terakhir yang tersimpan
python cli.py signal

# (opsional) Mode demo offline — tanpa OANDA & Ollama
python cli.py analyze --demo
```

Contoh keluaran `analyze`:
```
  Aksi      : ▲ BUY | Bias: bullish | Confidence: 0.65
  Entry     : 2015.4
  Stop Loss : 2008.2
  Take Profit: 2030.0
  Risk/Reward: 2.1
  Konfluensi : CHoCH bull, BSL tersentuh + retest POI
  Alasan     : BOS setelah take IDM membuat low jadi protected level, ...
  ⚠ Peringatan: volatilitas tinggi menjelang berita
  [DISCLAIMER] Ini REKOMENDASI, bukan jaminan profit. Eksekusi di tangan Anda.
```

---

## Web App (FastAPI + Login)

Selain CLI, bot punya **aplikasi web** (FastAPI) dengan halaman login/register
dan dashboard untuk menghasilkan & melihat sinyal dari browser.

```bash
# cara mudah (membuat venv, install deps, jalankan)
./run.sh

# atau manual
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
# buka http://localhost:8000
```

Alur:
1. `/register` — buat akun (password di-hash dengan PBKDF2, aman).
2. `/login` — masuk (sesi lewat cookie JWT).
3. `/dashboard` — klik **Analisis** untuk generate sinyal; riwayat tersimpan di `data.db` (SQLite).
4. `/api/signal` — endpoint JSON sinyal terakhir (dipakai integrasi eksternal).

Mode di web sama dengan CLI:
- **Demo (default)** — data sintetis + sinyal rule-based, langsung jalan tanpa OANDA/Ollama.
- **Live (otomatis saat `.env` terisi)** — pakai data OANDA practice + analisis LLM Ollama.

> ⚠️ Seperti CLI, web app ini **hanya memberikan rekomendasi** — ia tidak
> mengeksekusi order apa pun. Login dipakai untuk pelacakan per-user; bukan
> perlindungan trading otomatis.

### Publikasi (hosting gratis)
Untuk menjalankan web app agar **bisa diakses semua orang** tanpa biaya, lihat
**[`DEPLOY_ORACLE.md`](DEPLOY_ORACLE.md)** — panduan deploy ke **Oracle Cloud
Always Free** (VM ARM aktif 24/7 gratis). Termasuk: buat akun, VCN, instance,
buka port di Security List, install Python, service systemd, dan reverse-proxy nginx.
File dukungan ada di folder `deploy/` (`ai-trading.service`, `nginx-ai-trading.conf`).

---

## Konfigurasi (.env)

| Variabel | Default | Keterangan |
|---|---|---|
| `OANDA_TOKEN` | – | Access token akun practice OANDA |
| `OANDA_ACCOUNT_ID` | – | ID akun practice OANDA |
| `OANDA_ENV` | `practice` | environment OANDA (jangan ubah ke live!) |
| `OLLAMA_MODEL` | `qwen3:8b` | model Ollama untuk analisis |
| `OLLAMA_HOST` | `http://localhost:11434` | alamat server Ollama |
| `INSTRUMENT` | `XAU_USD` | instrumen (khusus XAU/USD per spesifikasi) |
| `TIMEFRAME_BIAS` | `H1` | timeframe untuk penentuan bias (HTF) |
| `TIMEFRAME_ENTRY` | `M15` | timeframe untuk entry presisi (LTF) |
| `CANDLE_COUNT` | `400` | jumlah candle saat fetch |

---

## Struktur folder

```
ai-trading/
├── config.py            # baca .env
├── cli.py               # CLI typer: fetch / analyze / watch / signal
├── requirements.txt
├── data/
│   ├── oanda.py         # fetch candle XAU_USD dari OANDA
│   └── indicators.py    # fractal swings, ATR, EMA (pendukung)
├── structure/
│   ├── swings.py        # ekstraksi swing high/low
│   ├── market.py        # deteksi struktur SMC + urutan
│   └── snapshot.py      # bungkus packet untuk LLM
├── ai/
│   ├── prompt.py        # system prompt SMC (Bahasa Indonesia)
│   ├── llm.py           # client Ollama
│   └── analyzer.py      # panggil LLM + validasi JSON
├── app/                 # web app (FastAPI)
│   ├── main.py          # routes: / /register /login /logout /dashboard /analyze /api/signal
│   ├── auth.py          # sesi cookie JWT + hash password (PBKDF2, stdlib)
│   ├── db.py            # database SQLite (users + signals) via stdlib
│   ├── analysis.py      # pipeline analisis untuk web (demo/live)
│   ├── templates/       # HTML (base, index, login, register, dashboard)
│   ├── static/style.css # styling
│   └── data.db          # file SQLite (dibuat otomatis saat start)
├── run.sh               # start web app di http://localhost:8000
├── signals/             # riwayat sinyal (JSON)
└── out/                 # data candle tersimpan (CSV)
```

---

## Batasan & Jujur tentang Deteksi
Deteksi struktur di `structure/` berbasis **aturan (rule-based)** dari data
OHLC — ia menangkap pola yang jelas (sequence HH/HL, BOS/CHoCH, IDM, BSL/SSL,
turtle soup, PDH/PDL). Beberapa konsep yang butuh penilaian visual/subjektif
(seperti posisi relatif trendline atau validasi akhir SMR 1 vs 2) diserahkan
sebagai *konfirmasi akhir* ke LLM, bukan klaim akurat mutlak dari parser.
Selalu verifikasi sinyal secara manual sebelum bertindak.
