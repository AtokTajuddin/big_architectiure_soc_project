# Nexus Sentinel — ML Engine + Agent Gateway

Dashboard all-in-one sekaligus **gateway integrasi** SOC: semua sensor dan agent AI
bicara lewat satu pintu ini, bukan langsung ke Wazuh/Suricata/Shuffle satu-satu.

```
Wazuh / Suricata / Tetragon ──(tail)──> Benthos ──POST /ingest──┐
                                          │                     ▼
                                          └──> VictoriaLogs   NEXUS SENTINEL (FastAPI)
                                                              ├─ klasifikasi ML (OWASP Top-10)
Savior (savior_v2 @ Ollama GPU) <──── penjelasan awam ─────── ├─ SQLite (alerts, keys)
Shuffle SOAR       <──── webhook per kategori ─────────────── ├─ WebSocket /ws/alerts → UI
Agent eksternal    ──── request bertanda tangan Ed25519 ────> └─ REST API
```

## Komponen

| File | Peran |
|------|-------|
| `src/main.py` | FastAPI app: ingest, klasifikasi, endpoint API, WebSocket |
| `src/db.py` | Persistensi SQLite (alert + kredensial), retensi otomatis |
| `src/auth.py` | Kredensial 2 tingkat: bearer key + keypair Ed25519 per-agent |
| `src/savior.py` | Jembatan ke savior_v2 (Ollama): verdict triase + penjelasan awam |
| `examples/agent_client.py` | Contoh agent menandatangani request dengan file kredensial |

## Kredensial (ala provider AI)

1. **Bearer key** (`nx_live_...`) — untuk pipeline sederhana (Benthos, curl, script).
   Header: `Authorization: Bearer <key>`.
2. **Agent keypair** (`nxa_...`, Ed25519) — identitas kriptografis per-agent.
   Private key **diunduh sekali** dari UI (API Key Access Manager → Agent Identity
   Keypairs) sebagai file kredensial JSON, lalu dipasang ke agent mana pun.
   Server hanya menyimpan public key. Tiap request ditandatangani:

   ```
   message   = METHOD \n PATH \n UNIX_TS \n SHA256_HEX(BODY)
   signature = base64( Ed25519_sign(private_key, message) )
   header    = X-Agent-Key-Id / X-Agent-Timestamp / X-Agent-Signature
   ```

   Uji: `python3 examples/agent_client.py <credential.json> whoami`

## Endpoint utama

| Endpoint | Fungsi |
|----------|--------|
| `POST /ingest` | Terima log mentah (auth wajib) → klasifikasi → enrich → SOAR/Loki/Savior |
| `GET /api/alerts?limit=N` | Alert terbaru dari SQLite |
| `POST /api/alerts/feedback` | Tandai false positive (404 jika alert tak ada) |
| `WS /ws/alerts` | Feed real-time: `alert_new` / `alert_update` |
| `GET /api/whoami` | Uji kredensial |
| `POST /api/agent-keys/generate\|list\|revoke` | Kelola keypair agent |
| `POST /api/keys/generate\|list\|revoke` | Kelola bearer key |
| `GET /api/savior/health` | Status koneksi Ollama/savior_v2 |
| `GET /metrics` | Prometheus (presisi dihitung dari feedback nyata, bukan statis) |

## Environment

| Var | Default | Keterangan |
|-----|---------|------------|
| `DEMO_MODE` | `false` | `true` = simulator alert dummy (demo UI tanpa sensor) |
| `ML_INGEST_KEY` | `nx_live_default_key_12345` | Bearer key bootstrap untuk Benthos |
| `DB_PATH` | `../data/nexus.db` | Lokasi SQLite |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama; via compose diarahkan ke jembatan socat `:11435` |
| `SAVIOR_MODEL` | `savior_v2:latest` | Model triase |
| `SAVIOR_MIN_SEVERITY` | `high` | Ambang severity yang dijelaskan Savior |
| `SAVIOR_MAX_PENDING` | `3` | Batas antrean GPU; lebih dari ini → SKIPPED |
| `SAVIOR_DEDUP_TTL` | `600` | Detik; signature+src sama tidak dijelaskan ulang |
| `MAX_ALERT_ROWS` | `5000` | Retensi tabel alert (riwayat penuh tetap di VictoriaLogs) |

## Catatan integrasi host

- Ollama di host hanya listen `127.0.0.1`. Container mengaksesnya lewat service
  systemd user **`ollama-docker-bridge`** (socat, bind `172.17.0.1:11435` — tidak
  terekspos LAN). Cek: `systemctl --user status ollama-docker-bridge`.
- Volume log Wazuh (`single-node_wazuh_logs`) di-mount eksternal ke Benthos;
  kalau stack Wazuh belum pernah dibuat, jalankan dulu
  `cd wazuh-local/single-node && docker compose up -d`.
