# Deploy ke Oracle Cloud (Always Free) — AI Trading XAUUSD

Panduan menaikkan web app AI Trading XAUUSD ke **Oracle Cloud Always Free**
(satu VM Ampere ARM A1: hingga **4 OCPU / 24 GB RAM**, aktif 24/7, **gratis seumur hidup**).

> ⚠️ Kantong-kantong biaya:
> - Oracle selalu menyediakan kuota **Always Free** yang dipakai resource di bawah ini.
> - Kalau kamu memilih **Pay-As-You-Go** saat daftar, pasang **budget alert ($1)** &
>   **reclaim idle free-tier instance** END session. Kalau murni **Always Free (bukan PAYG)**,
>   Oracle bisa mereclaim instance yang **idle** — jangan biarkan terlalu lama menganggur.

---

## 1. Buat akun Oracle Cloud

1. Buka https://www.oracle.com/cloud/free/
2. **Isi data asli & benar** — info palsu = akun langsung diblokir.
3. Butuh **kartu kredit/debit** utk verifikasi (tidak ditagih kecuali pakai PAYG)
   — kalau di currency/masih kesulitan, bisa pakai Virtual Card.
4. Setelah aktif, pilih **Home Region** (tidak bisa diubah nanti!) — pilih region terdekat.

---

## 2. Buat VCN (Virtual Cloud Network)

Menu ☰ → **Networking** → **Virtual Cloud Networks** → **Start VCN Wizard** →
**Create VCN with Internet Connectivity** → ikuti default (CIDR `10.0.0.0/16`) → **Create**.
Wizard otomatis bikin public/private subnet + Internet Gateway.

---

## 3. Buat Instance VM (Ampere A1 / ARM)

Menu ☰ → **Compute** → **Instances** → **Create Instance**:

| Setelan | Nilai |
|---|---|
| Name | `ai-trading` |
| Image / Shape | **Change Shape** → `VM.Standard.A1.Flex` (Ampere ARM) |
| OCPU / RAM | 1 OCPU / 6 GB (aman dalam batas 4 OCPU / 24 GB) |
| OS Image | **Ubuntu 22.04 atau 24.04** (default user `ubuntu`) |
| Networking | Existing VCN → public subnet → **Atur public IPv4 ✅** |
| SSH keys | **Paste/muat public key kamu** (lihat langkah bawah) |

> Kalau A1 "out of capacity" terus, fallback: `VM.Standard.E2.1.Micro` (AMD, 1/8 OCPU, 1 GB RAM)
> — selalu tersedia, cukup untuk web app ringan ini.

### Buat SSH key (di mesin lokal kamu)
```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_key
cat ~/.ssh/oracle_key.pub     # salin isinya → tempel di form "SSH keys" Oracle
```
Kalau Oracle yang generate, **unduh private key-nya saat itu juga** (tidak bisa diambil lagi).

---

## 4. Buka port di Security List — INI BAGIAN YANG PENTING

Default Oracle blokir SEMUA port masuk kecuali SSH. Web kamu tidak akan kebuka
sampai ini di-set. Menu ☰ → **Networking** → **Virtual Cloud Networks** → klik VCN kamu →
**Public Subnet** → **Security Lists** → **Default Security List** → **Add Ingress Rules**:

| Source CIDR | IP Protocol | Destination Port | Description |
|---|---|---|---|
| `0.0.0.0/0` | TCP | `22` | SSH (umumnya sudah ada) |
| `0.0.0.0/0` | TCP | `8000` | AI Trading XAUUSD (web) |

(setelah pakai nginx di langkah 8, boleh buka `80`/`443` dan tutup `8000` utk publik)

---

## 5. SSH ke server

```bash
chmod 600 ~/.ssh/oracle_key
ssh -i ~/.ssh/oracle_key ubuntu@PUBLIC_IP
```
(Cek PUBLIC_IP di halaman detail instance.)

---

## 6. Install Python & tool

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git nginx
```

---

## 7. Salin project & jalankan

```bash
# (opsional) clone repo — atau scp folder ai-trading ke server
cd ~
git clone <url-repo-ai-trading>   # mis. atau: scp -r ai-trading ubuntu@IP:~/
cd ai-trading

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# bikin env produksi — WAJIB set WEB_SECRET (string acak panjang)
cp .env.example .env
#   lalu isi:  WEB_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
#   dan isi OANDA_TOKEN / OANDA_ACCOUNT_ID kalau mau mode live.

# coba jalan manual dulu
WEB_SECRET=<secret> uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Tes dari browser: `http://PUBLIC_IP:8000` → harus jalan (login/register/dashboard).

---

## 8. Jalankan sebagai service otomatis (systemd) + nginx

Agar tetap hidup walau SSH ditutup & auto-restart saat server reboot:

1. Salin service unit (lihat `deploy/ai-trading.service`):
   ```bash
   sudo cp deploy/ai-trading.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now ai-trading
   sudo systemctl status ai-trading
   ```
2. (Opsional, biar pake port 80 + domain) salin `deploy/nginx-ai-trading.conf`:
   ```bash
   sudo cp deploy/nginx-ai-trading.conf /etc/nginx/sites-available/ai-trading
   sudo ln -s /etc/nginx/sites-available/ai-trading /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
   Lalu di Oracle Security List buka port `80`/`443`.

---

## 9. Periksa

```bash
ss -tlnp | grep -E ':8000|:80'        # port harus LISTEN
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000   # → 200
journalctl -u ai-trading -f            # log live
```

---

## Gotcha & catatan jujur

- **Port gold-plating:** default Oracle blokir port → kalau web "timeout" padahal service jalan,
  hampir pasti **Security List** atau **iptables/ufw** belum dibuka. Cek keduanya.
- Oracle Linux pakai user `opc`; Ubuntu pakai `ubuntu`.
- **Reclaim idle free-tier:** kalau akun bukan PAYG dan VM menganggur lama, Oracle bisa
  mematikannya. Jangan biarkan idle terlalu lama, atau upgrade ke PAYG + budget $1 alert.
- Web app **hanya rekomendasi** — tidak eksekusi order. Login utk pelacakan per-user.
- **HTTPS:** utk produksi publik tambahkan TLS (Caddy/Traefik/Let's Encrypt + domain).
