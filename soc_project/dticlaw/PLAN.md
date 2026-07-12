# DTIClaw — Arsitektur, Status, & Rencana (Handoff)

> Pasangan [HISTORY.md](HISTORY.md). Ini peta arsitektur, status fitur, dan TODO.

## Arsitektur (alur 1 pesan)
```
Browser (dashboard/public/index.html, minimalis, localStorage)
   │  POST /api/chat/stream  (SSE, token streaming)
   ▼
dashboard/server.js  (127.0.0.1:3737, loopback+Host guard, rate-limit)
   │   ├─ URL di pesan? → UrlFetcher.fetchUrl(allowAny) + ingest  (all-in-one)
   │   └─ else → gateway.streamReply(msg, onToken)
   ▼
core/gateway.js
   planAction(msg)  →  tool: chat | rag | research | gendoc        [AGENTIC]
   ├─ chat    → handleChat   (identitas/persona + memori mem0, stream)
   ├─ rag     → handleRag     (hybrid retrieval → JADWAL deterministik /
   │                           sintesis grounded LLM, stream + sumber)
   ├─ research→ handleResearch (engines/deep-research, web DDGS)
   └─ gendoc  → handleGenerateDoc (jadwal deterministik / skill writer → PDF/DOCX)
        ↕ engines: turbovec(bridge.js→index.py), memory(bridge.js→memory_engine.py)
        ↕ Ollama (gemma2:9b, bge-m3, qwen2.5vl)
```

## Peta file inti
| File | Peran |
|---|---|
| `core/gateway.js` | Orkestrator: planAction, handleChat/Rag/Research/GenerateDoc, streamReply, processMessage |
| `core/sandbox.js` | `confinePath` (FS), `assertPublicUrl` (anti-SSRF) |
| `core/ollama.js` | klien Ollama: `chat`, `chatStream`, `embed` |
| `core/{security,risk,audit,tools,logger}.js` | guard input/output, risk matrix, audit, tool registry (exec OFF), logging |
| `core/telegram.js` | bot (OFF default; BELUM ada owner-allowlist) |
| `engines/turbovec/{index.py,bridge.js}` | vector index hybrid (dense+BM25), IPC |
| `engines/memory/{memory_engine.py,bridge.js}` | mem0 long-term memory, IPC |
| `engines/docx-writer/{index.js,pdf.js}` | generator DOCX & PDF |
| `engines/{deep-research,reasoning,vision,guardian,rag}/` | engine lain (rag=Chroma fallback OFF) |
| `dashboard/server.js` + `public/index.html` | web server + UI minimalis |
| `skills/technical_writer.md` | skill penulis dokumen (editable) |
| `scripts/run-sandboxed.sh` | launcher bubblewrap (CARA JALAN RESMI) |
| `scripts/ingest_knowledge.py` | (re)build index turbovec dari `knowledge/` |
| `config/agent.yaml`, `config/.env.example` | konfigurasi |

## Cara menjalankan
```bash
cd Agentic/dticlaw
# sekali: venv berbasis SYSTEM python (penting utk sandbox)
uv venv --python /usr/bin/python3.11 .venv
uv pip install --python .venv/bin/python -r engines/requirements.txt rank-bm25 pymupdf mem0ai ollama
npm install
# Ollama: pull gemma2:9b, bge-m3 (dan qwen2.5vl:7b utk vision)
# ingest dokumen (knowledge/ berisi PDF + Jadwal_Perkuliahan.md):
.venv/bin/python scripts/ingest_knowledge.py
# jalankan (sandboxed, web-only):
bash scripts/run-sandboxed.sh   # → http://127.0.0.1:3737
```

## Status fitur
| Fitur | Status |
|---|---|
| Sandbox FS (bwrap) | ✅ terbukti konfinemen |
| Web UI minimalis + persisten (localStorage) | ✅ |
| Streaming SSE (TTFT) | ✅ token mengalir |
| Agentic router (LLM pilih tool) | ✅ |
| RAG hybrid (dense+BM25) | ✅ |
| Jadwal deterministik (akurat, A=Selasa, dst, multi-sesi) | ✅ |
| Identitas/sapaan → chat (tanpa sumber palsu) | ✅ |
| gendoc PDF/DOCX (markdown ter-render, jadwal terfilter) | ✅ |
| mem0 memori jangka panjang | ✅ store+recall |
| ChromaDB fallback | ⚠️ OFF (perlu chroma server) |
| Telegram | ⚠️ OFF (perlu owner-allowlist) |

## KNOWN ISSUES / sedang dikerjakan
1. **Data Dosen.pdf retrieval lemah**: PDF roster dosen padat → sebagian chunk
   sebelumnya gagal embed (Ollama 500). Sudah: sanitasi + chunk 512→300 + resilient.
   Saat handoff ini index sedang **di-rebuild ulang** (chunk 300). Verifikasi:
   `siapa Ridho Rahman Hariadi?` harus mengembalikan entri dosen (RR = Ridho Rahman
   Hariadi, pengampu Integrasi Sistem). Jika skor masih rendah, pertimbangkan
   ekstraksi tabel per-baris utk Data Dosen (mirip jadwal).
2. **gemma2:9b copy verbatim English** dari Kurikulum.pdf (mis. definisi blockchain)
   walau prompt minta Bahasa Indonesia → model 9B lemah translate-saat-grounding.
   Opsi: model lebih besar utk sintesis, atau langkah terjemahan terpisah.
3. **Routing pertanyaan ENTITAS/orang** ("siapa itu X") → default chat, gate 330;
   bila data ada tapi skor < gate, tak ter-ground. Pertimbangkan turunkan gate
   atau planAction lebih pintar (sudah LLM, tapi quick='chat' bypass LLM).

## RENCANA BERIKUTNYA (prioritas)
1. **[Arahan owner] Samakan arsitektur ke OpenClaw**: owner ingin pola tool-use
   OpenClaw (retrieval sebagai tool yang dipanggil agent), bukan routing+deterministik
   hardcode. **BUTUH source OpenClaw** (repo/path distill) — minta ke owner dulu.
   Setelah ada: refactor planAction/handle* → loop tool-calling ala OpenClaw,
   pertahankan jadwal-deterministik sebagai *tool* (bukan special-case di router).
2. Tuntaskan retrieval Data Dosen (verifikasi Ridho) → roster dosen bisa ditanya.
3. (Opsional) Aktifkan ChromaDB fallback: `chroma run` + `chromadb.enabled:true`.
4. (Opsional) Telegram owner-allowlist sebelum mengaktifkan bot.
5. Polish UI (owner akan kerjakan sebagian): render markdown lebih kaya (tabel),
   tombol download untuk PDF/DOCX hasil, wiring vision (kirim gambar) ke UI.
6. 3 temuan audit minor tersisa: prompt-guard tipis, alur konfirmasi tool
   (fail-closed), label risk `reversible`.

## Hal yang TIDAK boleh diubah tanpa alasan kuat
- Sandbox launcher & web-only (keamanan).
- bge-m3 1024-d sebagai embedding tunggal.
- Guard `persist()` anti-index-kosong + gateway read-only (cegah korupsi).
- Identitas DTIClaw / Atok / 5 Juni 2026 (di `engines/reasoning/index.js`
  `_systemPrompt()` + `config/agent.yaml`).
