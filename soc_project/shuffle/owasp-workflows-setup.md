# Shuffle SOAR — OWASP Top 10 Workflow Setup (Manual)

Shuffle tidak mendukung create workflow via REST API secara otomatis dari luar.
Workflow harus dibuat/import manual via UI.

## Quick Setup (3 Langkah)

### Langkah 1: Buka Shuffle UI
- URL: `http://localhost:3001`
- Login: `admin` / `Admin1234!`

### Langkah 2: Create 10 OWASP Workflows

Di menu **Workflows → New Workflow** (tombol orange `+ Create Workflow`), buat satu per satu:

| # | Workflow Name | Trigger | Action Utama | Deskripsi |
|---|--------------|---------|-------------|-----------|
| 1 | `SOC-A01-Broken-Access-Control` | **Webhook** | Log Data → HTTP POST | Privilege escalation / unauthorized access |
| 2 | `SOC-A02-Crypto-Failures` | **Webhook** | Log Data | Data exposure / weak crypto |
| 3 | `SOC-A03-Injection` | **Webhook** | HTTP POST (block src_ip) | SQL/XSS/Command injection dari Suricata |
| 4 | `SOC-A04-Insecure-Design` | **Webhook** | Log Data → Email alert | Malware / trojan detection |
| 5 | `SOC-A05-Security-Misconfig` | **Webhook** | Log Data → HTTP (rate limit) | DoS / misconfiguration |
| 6 | `SOC-A06-Vulnerable-Components` | **Webhook** | HTTP POST (MISP IOC) | CVE match — notify SOC L1 |
| 7 | `SOC-A07-Auth-Failures` | **Webhook** | HTTP POST (block IP) | SSH brute force |
| 8 | `SOC-A08-Integrity-Failures` | **Webhook** | Log Data | Software integrity / supply chain |
| 9 | `SOC-A09-Logging-Failures` | **Webhook** | Email alert | Pipeline gap / log tampering |
| 10 | `SOC-A10-SSRF` | **Webhook** | HTTP POST (block + quarantine) | SSRF / R2L network anomaly |

### Langkah 3: Tambahkan Webhook Trigger

Setiap workflow **WAJIB** punya node trigger **Webhook**:

1. Drag **Webhook** app ke canvas (dari panel kiri)
2. Klik node → **Edit**
3. Metode: `POST`
4. Klik **Save** → Shuffle akan generate URL unik, contoh:
   ```
   http://localhost:3001/api/v1/hooks/webhook_abc123def456
   ```
5. **Copy URL ini** → simpan

---

## Konfigurasi ML Engine → Shuffle

Edit `docker-compose.yml` service `ml-engine`:

```yaml
environment:
  SHUFFLE_WEBHOOK_URL: "http://localhost:3001/api/v1/hooks/webhook_abc123def456"
  SHUFFLE_API_KEY: shufflesocapikey2026abc
```

Jika Anda punya **banyak workflow** (recommended untuk OWASP terpisah), pilihan:

**Opsi A — Single generic webhook** (simplest):
- Semua alert masuk ke 1 workflow `SOC-ML-Alerts-Hub`
- Di dalam workflow, pakai **Branch** node untuk split berdasarkan field `owasp_id`

**Opsi B — Multiple webhooks** (most granular):
- Copy semua 10 webhook URLs
- ML Engine perlu logic dispatch — modify `main.py` `notify_shuffle()` untuk pilih URL berdasarkan `owasp_id`

---

## Struktur Payload yang Dikirim ML Engine

ML Engine mengirim JSON ini ke webhook Shuffle:

```json
{
  "source": "suricata",
  "status": "ATTACK DETECTED",
  "owasp_id": "A03:2021",
  "owasp_name": "Injection",
  "cwe": ["CWE-89", "CWE-79", "CWE-94"],
  "cve": "CVE-2023-40044",
  "nist": "SI-10, SI-16",
  "mitre": "Input Validation",
  "src_ip": "192.168.1.100",
  "dest_ip": "10.0.0.1",
  "severity": "high",
  "patch_steps": "Apply input sanitization..."
}
```

---

## Panduan Membuat Workflow di Shuffle UI

### Contoh: SOC-A03-Injection (Block src_ip)

1. **New Workflow** → Name: `SOC-A03-Injection`
2. Tambah node:
   - **Webhook** (trigger)
   - **Shuffle Tools** → `repeat_back_to_me` (log ke stdout)
   - **HTTP Request** → `POST` ke firewall API (opsional)
3. Sambungkan: `Webhook` → `repeat_back_to_me` → `HTTP Request`
4. Save

### Parameter Node Shuffle Tools (Log)

- **App**: Shuffle Tools
- **Action**: `repeat_back_to_me`
- **call**: `{{#webhook}}` (auto-filled dari trigger)

### Parameter Node HTTP Request (Block IP)

- **App**: HTTP Request
- **Action**: `POST`
- **URL**: `http://your-firewall/api/block`
- **Body**: `{"ip": "{{webhook.src_ip}}", "reason": "{{webhook.owasp_name}} - {{webhook.cve}}"}`

---

## Setelah Webhook URL Didapat

```bash
# 1. Edit docker-compose.yml, set SHUFFLE_WEBHOOK_URL
# 2. Restart ML engine
sudo docker compose -f /home/atokdins/soc_project/docker-compose.yml up -d --force-recreate ml-engine

# 3. Test dengan curl
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"raw": "{\"event_type\":\"alert\",\"src_ip\":\"192.168.1.100\",\"alert\":{\"signature\":\"ET DOS Potential SSH Scan\",\"category\":\"Attempted Denial of Service\",\"severity\":2}}", "source_hint": "suricata"}'

# 4. Cek Shuffle workflow execution history
```

---

## Alternatif: Import JSON Template

Jika Shuffle UI mendukung import JSON (menu **Admin → Workflows → Import**), gunakan file:

- `shuffle/templates/soc-a01-broken-access-control.json`
- `shuffle/templates/soc-a03-injection.json`
- ...dst

(File template akan dibuatkan terpisah.)

---

## Troubleshooting Shuffle

| Problem | Solusi |
|---------|--------|
| `Missing authentication` di log | Normal first-boot, tunggu 2-3 menit |
| Workflow tidak muncul di My Workflows | Refresh halaman (F5) atau re-login |
| Webhook URL tidak jalan | Pastikan port 3001 open, cek `sudo docker ps` |
| ML engine tidak kirim ke Shuffle | Cek `SHUFFLE_WEBHOOK_URL` di docker-compose, restart ml-engine |

---

*Setup guide ini menggantikan otomasi via API karena keterbatasan Shuffle REST endpoint.*
