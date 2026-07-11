# Savior agent — SOC Companion (savior_v2)

Agent framework pendamping model **savior_v2** (Llama-Primus 8B, fine-tune SOC) oleh **Atok Tajuddin & tim researcher**.
Fokus: baca log **Wazuh**, triase alert **TP / FP / FN**, beri rekomendasi. Jalan **lokal + GPU**.

---

## Arsitektur

```
savior_v2 (LoRA→GGUF Q4, Ollama via systemd, GPU RTX 3070)
   ├──► Savior Monitor :8899  (Docker) — triase Wazuh + metrics Grafana tiap 5 menit  ★
   ├──► Open WebUI  :3030  (chat persistent + Web Search + Wazuh Grounding anti-halusinasi)
   ├──► Savior agent (dticlaw) :3737  (agentic + savior-bridge)
   └──► savior-triage / savior-bridge  (baca Wazuh deterministik)

Grafana :3000 — dashboard "08 – Savior AI Companion" (embed Monitor + Chat)
   sumber data AI = VictoriaMetrics :8428 + VictoriaLogs :9428 (datasource Grafana)
Wazuh single-node (docker)  :9200 indexer · :55000 API · :443 dashboard
Shuffle SOAR (webhook, cloud)  — trigger via savior-bridge (human-in-the-loop)
```

## ★ Savior Monitor — pendamping SOC otomatis (tiap 5 menit)

Container Docker (`savior-monitor/`, `network_mode: host`) yang tiap 5 menit: tarik alert **NYATA** dari
Wazuh Indexer **+ metrics pipeline dari VictoriaMetrics/VictoriaLogs (data yang sama dengan Grafana:
MISP IOC, Shuffle SOAR, ML engine, volume log)** → triase savior_v2 (GPU) → sajikan ringkasan ke
**dashboard** dan log persistent. Deterministik (model hanya menilai data asli, **anti-halusinasi**).

- **Dashboard:** http://localhost:8899 (auto-refresh 30s, badge TENANG/PERHATIAN/KRITIS)
- **API:** `curl http://localhost:8899/api/latest`
- **Log persistent:** `savior-monitor/data/summaries.jsonl`
- **Start/stop:** `cd savior-monitor && docker compose up -d` / `down`
- **Konfigurasi** (`savior-monitor/docker-compose.yml`): `INTERVAL_SECONDS` (default 300),
  `KNOWN_ASSETS` (whitelist aset sah agar FP akurat, mis. `192.168.56.10=admin bastion`).

**Contoh ringkasan nyata** (7 alert asli, triase 12.5s):
```
STATUS: PERLU PERHATIAN
Probabilistik: 80% FALSE POSITIVE, 20% TRUE POSITIVE (rule.id=5710).
FALSE POSITIVE: brute-force ke user non-exist dari host dikenal (192.168.56.10, admin bastion).
TRUE POSITIVE: menunggu konfirmasi log detail; bila sahih → containment + hunt.
```

## Akses cepat

| Layanan | URL / perintah | Kredensial |
|---|---|---|
| **Savior Monitor** (ringkasan 5 menit) | http://localhost:8899 | — |
| **Grafana — dashboard "08 – Savior AI Companion"** | http://localhost:3000/d/mini-soc-savior-v1 | `admin` / `minisoc2026` |
| **Chat (Open WebUI)** | http://localhost:3030 | akun yang dibuat saat pertama |
| Wazuh dashboard | https://localhost | `admin` / `SecretPassword` |
| Wazuh indexer | https://127.0.0.1:9200 | `admin` / `SecretPassword` |
| Wazuh API | https://127.0.0.1:55000 | `wazuh-wui` / `MyS3cr37P450r.*-` |
| Triase CLI | `python3 dticlaw/scripts/savior-triage.py --limit 5` | — |
| Start Wazuh | `cd wazuh-local/single-node && docker compose up -d` | — |

> **Anti-halusinasi:** di Open WebUI, pertanyaan soal alert otomatis di-*ground* dengan data Wazuh asli
> (Filter "Wazuh Grounding", global+aktif). Untuk lookup CVE/eksternal nyalakan toggle 🌐 Web Search.

---

## Contoh response AI (hasil nyata)

### 1) Triase False-Positive (alert asli rule.id 5710)
**Input:** alert Wazuh `rule.id 5710` level 5 "sshd: non-existent user" dari `192.168.56.10`
(admin jump host sah, maintenance window).

**savior_v2 →**
```
VERDICT: FALSE POSITIVE
Alasan: aktivitas admin sah (jump host/bastion); rule ini sensitif, butuh tuning untuk internal.
Rekomendasi: tambahkan exception/tuning rule untuk srcip ini/kategori aset yang dikenal.
```
*58 token / 0.8s (72 tok/s, GPU) · wall 1.3s*

### 2) `savior-triage` — tarik alert ASLI dari Wazuh + triase
```
=== Wazuh: 3 alert (dari 194 match) ===
1. [3] rule 502  Wazuh server started.                              | 2026-06-25T02:09:05Z
2. [5] rule 5710 sshd: Attempt to login using a non-existent user   | srcip=192.168.56.10
3. [5] rule 5710 sshd: Attempt to login using a non-existent user   | srcip=192.168.56.10

=== Triase savior_v2 ===
VERDICT: TP — login gagal user tak dikenal; amankan sesi + buru aktivitas serupa.
VERDICT: FP — aktivitas admin sah (user baru belum di inventory).
--- 3 alert ditriase dalam 7.5s (GPU) ---
```

### 3) Open WebUI grounded (anti-halusinasi)
**User:** "Cek alert terbaru di Wazuh, ada brute force dari 192.168.56.10? Verdict?"
Filter menyuntik data ASLI (`rule.id=5710, srcip=192.168.56.10, full_log=...`, total match=6) →

**savior_v2 →**
```
Membaca log:
- rule.id=5710 level=5 "sshd: Attempt to login using a non-existent user"
  srcip=192.168.56.10 full_log="Failed password for invalid user backupadmin ... ssh2"
Verdict: TP (True Positive) — aktivitas nyata, bukan false positive.
Aksi: amankan session dari sumber itu + monitor.
```
> Catatan: verdict ikut konteks aset. Jika diberi tahu "192.168.56.10 = bastion admin sah", verdict menjadi **FP**.

### 4) Halusinasi SEBELUM grounding (jangan dipakai)
Chat polos tanpa grounding mengarang data: *"rule.id 1018, host=hr-app-01, ts=2024-03-25…"* —
**data palsu**. Filter Wazuh Grounding menghilangkan ini.

---

## Human-in-the-loop
- **Baca log Wazuh** = bebas (read-only).
- **Tindakan** (trigger Shuffle, blokir IP, ubah rule) = **wajib persetujuan**:
  `savior-bridge.py shuffle-trigger '<json>' --approved`

## File penting
- Model: `savior_v2/serve/` (Modelfile, merge.py, GGUF)
- Bridge/akses: `dticlaw/scripts/savior-bridge.py`, `dticlaw/scripts/savior-triage.py`
- Grounding Open WebUI: `wazuh-local/openwebui-wazuh-function.py`
- Demo FP: `wazuh-local/fp-demo.sh`
- Wazuh stack: `wazuh-local/single-node/`
- Kredensial: root `.env` (gitignored)
