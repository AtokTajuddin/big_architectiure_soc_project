# DTIClaw — Riwayat Pengembangan & Keputusan (Handoff)

> Dibaca dulu oleh agent/dev berikutnya. Ini merangkum APA yang terjadi, KENAPA,
> dan kondisi terkini. Untuk arsitektur & to-do lihat [PLAN.md](PLAN.md).

## Konteks proyek
- **DTIClaw** = asisten riset agentic, **versi modifikasi/distill dari OpenClaw**
  (oleh Atok Tajuddin). Node.js (gateway/engines) + Python (turbovec, mem0) via IPC.
- Identitas resmi: *"DTIClaw, asisten AI yang dikembangkan oleh Atok Tajuddin
  sejak 5 Juni 2026"* (tanggal dari log/artefak awal `logs/2026-06-05.log`).
- Lokasi: `…/praktikum-modul-5/Prkatikum_github/praktikum-ai-modul5/Agentic/dticlaw/`
- Ada proyek SAUDARA di repo yang sama: **BANASPATI** (RAG multimodal praktikum
  Modul 5, folder `banaspati/` + 3 notebook Orang1/2/3) — terpisah dari DTIClaw.

## Prinsip operasi (WAJIB dipertahankan)
1. **Sandbox-only**: jalankan via `scripts/run-sandboxed.sh` (bubblewrap). FS
   terkurung ke folder dticlaw — `~/.ssh`, `.env` proyek lain TIDAK terlihat.
   Terbukti via uji konfinemen.
2. **Web-only**: Telegram dimatikan default (butuh `DTICLAW_ENABLE_TELEGRAM=1`
   + owner-allowlist yang BELUM dibuat). Interface = dashboard `127.0.0.1:3737`.
3. **Lokal-first**: Ollama (`gemma2:9b` generator/chat, `bge-m3` 1024-d embedding,
   `qwen2.5vl:7b` vision). Gemini API hanya bila diperlukan (judge BANASPATI).
4. **Embedding = bge-m3 (1024-d)** di SEMUA tempat. `nomic-embed-text` dibuang.

## Linimasa & keputusan kunci

### 1. Audit keamanan → [AUDIT.md](AUDIT.md)
12 temuan. Semua CRITICAL/HIGH ditambal:
- `exec_safe` (RCE shell `spawn(cmd,{shell:true})`) → **dinonaktifkan**.
- Path traversal read/write → `core/sandbox.js` `confinePath()` mengurung ke SANDBOX_ROOT.
- SSRF dashboard fetch-url & web_fetch → `assertPublicUrl()` blok IP privat/metadata.
- LFI `/api/logs` → konfinemen ke logDir + ekstensi.
- Dashboard tanpa auth/CORS `*` → loopback-only + Host guard (anti DNS-rebind) + CORS same-origin.
- Telegram tanpa owner-check → dimatikan default.

### 2. Vector stack
- **TurboVec** (`engines/turbovec/`, lib `turbovec` 0.8.0 PyPI) = PRIMER. Dense
  index 1024-d, IPC JSON ke Node via `bridge.js`. venv di `.venv` (BERBASIS
  SYSTEM python `/usr/bin/python3.11` agar jalan di sandbox — JANGAN pakai uv-managed
  python yang di luar folder).
- **Hybrid retrieval**: dense (turbovec) + **BM25** (`rank_bm25`) → RRF. BM25 lazy,
  rebuild saat korpus berubah. Field hasil `score` = skor DENSE (0 bila BM25-only)
  agar gate & sitasi konsisten.
- **ChromaDB** = FALLBACK, status **OFF** (`agent.yaml chromadb.enabled:false`).
  RagEngine (Node) konek ke Chroma server `localhost:8000` (HTTP) — TIDAK ada
  server jalan. Untuk mengaktifkan: jalankan `chroma run` + set enabled:true.

### 3. mem0 (memori jangka panjang) — `engines/memory/`
- `mem0ai` 2.0.5 + Ollama (gemma2:9b extraction, bge-m3 embed) + Chroma lokal
  (`data/mem0_chroma`). IPC `bridge.js`. Terbukti: store + recall ("Atok bikin dticlaw").
- API mem0 2.x: `search/get_all` pakai `filters={'user_id':...}` (BUKAN top-level).
- Butuh lib python `ollama` (sudah diinstall).

### 4. Agentic router (ala OpenClaw) — `core/gateway.js planAction()`
- LLM memilih tool: `chat | rag | research(web DDGS) | gendoc`. Fast-path aturan
  untuk identitas/sapaan/gendoc (murah), sisanya diputuskan LLM. Terbukti memilih
  tool dengan alasan (mis. "berita terbaru" → research).

### 5. Generasi dokumen — `handleGenerateDoc` + `engines/docx-writer/`
- **DOCX** (`index.js`, lib `docx`) + **PDF** (`pdf.js`, lib `pdfkit`).
- Markdown DIRENDER di PDF (`**bold**`, `##` → heading; tak ada `**`/`##` mentah).
- Skill penulis: `skills/technical_writer.md` (file, bisa diedit).
- **Jadwal** → dibangun DETERMINISTIK dari `knowledge/Jadwal_Perkuliahan.md`
  (filter kelas/semester/MK), BUKAN dump LLM.

### 6. Streaming (TTFT) — SSE
- `ollama.chatStream()` → `gateway.streamReply()` → dashboard `/api/chat/stream`
  (SSE) → frontend `EventSource`/reader. Token mengalir per-token (terbukti).
- Jawaban jadwal deterministik dikirim 1 blok (instan, nol halusinasi).

### 7. UI minimalis — `dashboard/public/index.html`
- Ditulis ulang gaya Claude/GPT: satu kolom, bubble, markdown-lite, streaming.
- **Persisten**: chat disimpan `localStorage` (`dticlaw_chat_v1`) → tak hilang saat refresh.
- Tombol "+ Chat baru". Tab lama (URL Fetcher/Knowledge/Logs) DILEBUR: tempel URL
  di chat → auto fetch+ingest (anti-SSRF private tetap aktif).

## BUG PENTING yang ditemukan & ditambal
1. **KORUPSI INDEX (root cause "halusinasi")**: gateway dulu `persist()` index
   KOSONG saat exit → menimpa index bagus (texts:0). Penyebab agent "mengarang"
   karena konteks benar-benar kosong. FIX: hapus auto-persist saat exit (gateway
   read-only) + guard `persist()` menolak menulis index kosong.
2. **gemma2:9b sering mengarang/abstain** pada lookup terstruktur meski jawaban
   ADA di konteks → untuk JADWAL dipakai **jawaban deterministik (bypass LLM)**.
3. **Huruf kelas (A/B/C)** 1-karakter ter-filter → A vs B tertukar. FIX: deteksi
   `kelas X` khusus + match `<Letter> (` di baris jadwal.
4. **Prompt sintesis terlalu ketat** (orientasi jadwal) → pertanyaan PROSA salah
   abstain. FIX: prompt grounded UMUM (jadwal sudah ditangani jalur deterministik).
5. **Guardian drift bocor** ke jawaban chat → dijadikan internal log/audit saja.
6. **Embed 500 (Ollama)** pada PDF padat (Data Dosen) → sanitasi karakter kontrol
   + cap 6000 char + ingest resilient (skip-chunk, tak jatuhkan dokumen) + chunk
   diperkecil 512→300 kata.
7. `index.remove()` turbovec API rewel (numpy array) — dihindari; pakai full rebuild.

## CATATAN PROSES (penting utk next agent)
- **JANGAN `pkill -f "..."` dengan pola yang ada di command sendiri** (mis.
  "ollama pull", "index.py --ipc", "gateway.js") — beberapa kali membunuh shell
  sendiri (exit 144). Kill via PID dari `ss -ltnp`/`pgrep` spesifik.
- **Jangan dua proses menulis index bersamaan**: STOP gateway sebelum ingest/rebuild
  (gateway memuat index in-memory; saat shutdown bisa menimpa).
- Restart web: `kill <pid :3737>` lalu `bash scripts/run-sandboxed.sh </dev/null &`.
- Jaringan workstation ~1 MB/s & flaky saat sesi ini (pull model lambat).
- gemma2:9b di RTX 3070: **~57 tok/s** warm dgn `num_ctx` kecil; lambat (~8 tok/s)
  kalau `num_ctx=8192`. Pakai num_ctx wajar.
