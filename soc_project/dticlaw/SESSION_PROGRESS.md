# DTIClaw — Progres Sesi (2026-06-14)

Snapshot kerja sesi ini. Untuk penerus / lanjutan.

## TL;DR status

- DTIClaw jalan **sandboxed (bwrap)** & persisten: gateway `18789`, dashboard/UI `3737`.
- **Interface mandiri baru** di `http://127.0.0.1:3737` (bukan lagi control-ui bawaan OpenClaw) — chat ke agent, VERIFIED end-to-end.
- Skills **dipangkas** dari 76 → **4 aktif** (allowlist per-agent): dticlaw-research, dticlaw-writer, dticlaw-rag, dticlaw-guardian.
- Skill yang tadinya **hollow kini berimplementasi & teruji standalone**: writer (docx/xlsx/csv/pdf), research (DDGS), rag (bge-m3).
- ⚠️ Belum tuntas: SKILL.md belum diupdate untuk memanggil script via `$DTICLAW_PY`; gateway belum di-restart dgn env baru; identitas agent masih meleset (lihat Known Issues).

## Cara menjalankan

```bash
cd Agentic/dticlaw
bash scripts/dticlaw-service.sh start      # start sandboxed (bwrap)
bash scripts/dticlaw-service.sh status     # cek (port-based)
bash scripts/dticlaw-service.sh stop       # stop + reap by port
bash scripts/dticlaw-service.sh restart
# Buka: http://127.0.0.1:3737
```

Log: `.dticlaw-state/logs/{gateway,dashboard}.log`

## Arsitektur efektif

```
Browser → dashboard-server.mjs (3737, bwrap "dticlaw-dashboard")
            └─ POST /chat → spawn `node openclaw.mjs agent --json`
                              → Gateway (18789, bwrap "dticlaw-gateway", auth none)
                                  → ollama/gemma2:9b (generator) + bge-m3 (embed)
```

- Config DTIClaw: `.dticlaw-state/openclaw.json` (agent id `dticlaw`, model gemma2:9b, auth.mode none, allowlist skills).
- State dir: `.dticlaw-state/` (via `OPENCLAW_STATE_DIR`).
- Sandbox FS: hanya folder dticlaw + `/tmp` + `~/.ollama` (read-only `/usr /etc /lib`).

## Yang diperbaiki sesi ini

1. **Proses non-sandboxed dimatikan**; `start-dev.sh` (buatan awal, SALAH: `--dev` vanilla C3-PO, tanpa sandbox) tidak dipakai — pakai `dticlaw-service.sh`.
2. `dticlaw-service.sh` diperbaiki: `start` benar-benar detached (drop `--die-with-parent`, redirect log), `stop`/`status` **berbasis port (fuser/ss)** — fix orphan "jebakan pkill".
3. **Auth**: `gateway.auth.mode = none` di config + flag `--auth none` (loopback lokal, tak perlu token → UI bebas konek).
4. **Model fix**: set `OLLAMA_API_KEY` (nilai apa saja) → tanpa ini `ollama/gemma2:9b` = "Unknown model".
5. **Port**: samakan gateway ke **18789** (default yg dicari CLI) → `openclaw agent` pakai gateway running (model tetap warm), bukan fallback embedded.
6. **Skills trim**: `agents.list[].skills = [...]` (agent filter) → 4/76 aktif → fix **context overflow** (system prompt turun dari 7349 token).
7. **UI baru**: `web/index.html` + rewrite `scripts/dashboard-server.mjs` (serve UI + `/chat` + `/healthz`).
8. **venv** `.venv/` (python 3.14) + deps ringan: python-docx, openpyxl, pypdf, reportlab, ddgs, requests, beautifulsoup4, numpy. (Sengaja HINDARI chromadb/sentence-transformers/torch — RAM 8GB.)
9. **Implementasi skill** (di `workspace/skills/`):
   - writer: `xlsx_writer.py`, `pdf_writer.py` (+ docx_writer.py lama). docx/xlsx/csv/pdf TESTED ✓
   - research: `web_search.py` (DDGS). TESTED ✓ (hasil nyata)
   - rag: `rag.py` (ingest/search/status, embed bge-m3 via Ollama + numpy cosine, store npy+jsonl). TESTED ✓ (1024-dim)

## Temuan penting (jawaban verifikasi user)

- **TurboVec / mem0 / ChromaDB: TIDAK ADA / tidak jalan** di instalasi ini. SKILL.md dticlaw-rag lama hanya dokumentasi; engine TurboVec tak ada, mem0 tak terinstall, chroma tak running. → Diganti pendekatan ringan: **bge-m3 (Ollama) + numpy** (lihat `rag.py`). mem0 digantikan `memory-core` bawaan OpenClaw (SQLite).
- Ini **benar DTIClaw (OpenClaw modif)**: identity & agent `dticlaw` ada di config; tapi runtime tetap memuat 57 skill bundled OpenClaw (dibatasi via allowlist, bukan dihapus fisik).

## Known issues / TODO berikutnya

1. **Identitas meleset**: gemma2 jawab "large language model trained by OpenClaw" (Inggris). Perlu sistem prompt/identity diperkuat (Bahasa Indonesia, nama DTIClaw, pembuat Atok). Cek `identity` + system prompt OpenClaw; gemma2:9b cenderung copy verbatim.
2. **Wire skill ke agent**: update 3 SKILL.md agar agent menjalankan script via `$DTICLAW_PY` (env sudah diinject di `dticlaw-service.sh`, BELUM di `run-sandboxed.sh`). Lalu `restart`.
3. **Context overflow** pada sesi panjang (gemma2 budget ~4096). Opsi: naikkan `num_ctx` gemma2 (max 8192) atau andalkan auto-compaction / sesi baru.
4. amazon-bedrock plugin error load (missing @aws-sdk) — tak relevan, abaikan/disable.
5. Verifikasi end-to-end via UI: minta agent generate dokumen & retrieval (belum dilakukan dari UI).

## Update 2 (lanjutan sesi 2026-06-14)

- **SOUL/Persona** ✅: `workspace/SOUL.md` (ringkas) → identitas benar "Aku DTIClaw 🦞, buatan Atok Tajuddin (sejak 5 Juni 2026)", Bahasa Indonesia. SOUL.md = mekanisme persona OpenClaw (di workspace root agent).
- **Egress guard** ✅: `.dticlaw-state/hosts-block` (di-bind ke `/etc/hosts` sandbox, IPv4 `0.0.0.0` + IPv6 `::`) null-route openclaw.ai/docs/clawhub/telemetry/ios-push-relay. Lokal (Ollama) + vendor (anthropic dsb) + web TIDAK diblok. Telemetry off. Verified: tidak ada koneksi keluar non-loopback dari gateway.
- **Fix context overflow** ✅: gemma2:9b native ctx 8192 → OpenClaw split 4096/4096 → overflow multi-turn. Solusi: custom Ollama model `dticlaw-gemma` (Modelfile `num_ctx 12288`, `num_predict 2048`). Multi-turn VERIFIED. RAM mesin ternyata **30GB** (bukan 8GB) — aman.
- **Skills wired** ✅: 3 SKILL.md (rag/research/writer) ditulis ulang pakai `$DTICLAW_PY` + `$DTICLAW_DIR` (di-inject ke sandbox env) + panduan "kapan pakai" (agentic, tidak ngawur). Allowlist kini 3 skill (guardian di-drop, tak ada di kebutuhan).
- **RAG ke database nyata** ✅: ingest `knowledge/` (Jadwal_Perkuliahan.md, Data Dosen.pdf, Kalender Akademik, Peraturan Akademik) → **221 vektor** di `workspace/rag_store` (bge-m3, 1024-dim). Retrieval TESTED.
- **Agentic RAG** ⏳: gemma2:9b Capabilities = `completion` SAJA (tak bisa tool-calling) → agent tak pernah panggil rag.py. Keputusan owner: **pull qwen2.5:7b-instruct** (tool-calling, 32k ctx) sebagai otak agent. Modelfile siap: `.dticlaw-state/ollama/Modelfile.dticlaw-qwen` (num_ctx 16384, temp 0.4). Switch: `bash scripts/switch-model.sh qwen`. Download ~4.7GB sedang berjalan.

## Update 3 (2026-06-14 malam) — Agentic RAG TERBUKTI + lanjut besok

- **Agentic RAG BERFUNGSI** (bukti keras): dengan otak model tool-calling, agent otonom memanggil `rag.py`. Uji "jadwal keseluruhan Kelas A" → trajectory: **7 panggilan rag.py**, jawaban tabel jadwal dari data nyata. Bukan hardcode/halusinasi.
- **Akar masalah retrieval = kapabilitas model, BUKAN retrieval/pipeline** (yang selalu jalan). gemma2:9b `completion`-only → tak panggil tool. Model `tools`-capable → agentic jalan.
- **Otak agent saat ini = `ollama/deepseek-v4-pro:cloud`** (config `.dticlaw-state/openclaw.json` list[0].model.primary). Ini **CLOUD** (sementara, untuk bukti). Backup config lokal: `.dticlaw-state/openclaw.json.bak.*`.
- **DNS container ollama sudah di-fix** (`--dns 1.1.1.1 8.8.8.8`) → pull tak lagi `i/o timeout`. qwen2.5vl:7b (praktikum) **selesai**; qwen2.5:7b-instruct (DTIClaw agentic lokal) **masih unduh** — lambat karena ISP throttle; owner lanjut besok di internet cepat.
- **Praktikum SELESAI**: 3 notebook ber-output + `BANASPATI_Final.ipynb` (konsolidasi) + judge 10/10 via `gemini-3-flash-preview:cloud` ($0.032) + RAGAS + metrik inferensi.
- **Tuning item besok**: agent (deepseek) kadang **skip retrieval** untuk pertanyaan akademik (mis. "dosen Ridho" → minta klarifikasi, tak panggil rag.py). Perkuat instruksi "selalu retrieve untuk pertanyaan akademik" di SOUL.md/SKILL.md, atau qwen lokal mungkin lebih konsisten.

## Update 4 (2026-06-15) — Agentic RAG 100% LOKAL BERFUNGSI ✅

- Otak agent sekarang = **`ollama/dticlaw-qwen`** (FROM qwen2.5:7b-instruct, tools, num_ctx 16384, **temp 0.1**) — lokal penuh, no-leak.
- **Uji "siapa dosen Ridho"** → agent jalankan rag.py → jawab **"Dr. Ridho Rahman Hariadi, S.Kom., M.Sc."** + sitasi **Data Dosen.pdf**. Bukti retrieval nyata (data hanya ada di PDF itu).
- **3 fix kunci** agar qwen 7B andal agentic (model 7B lemah tool-use, ketiganya diperlukan):
  1. **Pangkas tool** ke `exec/read/write` (`agents.list[].tools.allow`) — default ~35 tool (terutama `memory_search`) bikin qwen nyasar ke memori kosong, bukan rag.py.
  2. **temperature 0.1** (dari 0.4) — emisi tool lebih deterministik.
  3. **SOUL.md**: "LANGSUNG panggil exec, jangan cuma bilang 'aku akan mencari' lalu berhenti".
- Kecepatan: qwen 7B lokal ~76s sederhana / ~3-4 mnt agentic. Timeout `/chat` dashboard 180s (`DTICLAW_AGENT_TIMEOUT_MS`) — naikkan kalau query agentic berat.
- deepseek-v4-pro:cloud juga jalan (lebih kuat/cepat) tapi cloud — fallback.

## LANJUT BESOK — langkah cepat

```bash
cd Agentic/dticlaw
# 1. Selesaikan unduh model agentic lokal (internet cepat):
docker exec banaspati-ollama ollama pull qwen2.5:7b-instruct
# 2. Pindahkan otak agent ke qwen lokal (privat, no-leak):
bash scripts/switch-model.sh qwen
# 3. Uji ulang agentic RAG (harus 100% lokal):
#    buka http://127.0.0.1:3737 → tanya "jadwal keseluruhan Kelas A"
#    cek trajectory ada panggilan rag.py:
#    grep -c rag.py .dticlaw-state/agents/dticlaw/sessions/*.trajectory.jsonl
```

Catatan: kalau mau kembali ke gemma2 lokal (non-agentic) sementara: `bash scripts/switch-model.sh gemma2`.

## Cara ganti otak agent

```bash
bash scripts/switch-model.sh qwen     # ke qwen2.5 (tool-calling, Agentic RAG)
bash scripts/switch-model.sh gemma2   # kembali ke gemma2 (completion saja)
```

## Peta file kunci (relatif ke Agentic/dticlaw)

- `scripts/dticlaw-service.sh` — launcher sandboxed utama (start/stop/status/restart)
- `scripts/run-sandboxed.sh` — varian foreground (perlu sinkron env DTICLAW_PY/auth)
- `scripts/dashboard-server.mjs` — server UI 3737 + endpoint /chat
- `web/index.html` — interface mandiri DTIClaw
- `.dticlaw-state/openclaw.json` — config DTIClaw (auth none, allowlist, model)
- `workspace/skills/dticlaw-{writer,research,rag,guardian}/` — skill aktif
- `.venv/` — python env untuk skill
