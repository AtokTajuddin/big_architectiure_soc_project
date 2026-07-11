---
name: dticlaw-rag
description: "Retrieval basis pengetahuan akademik lokal (jadwal kuliah, data dosen, kurikulum, kalender akademik, peraturan). Embedding bge-m3 via Ollama. Untuk pertanyaan tentang data internal kampus/DTI."
metadata: { "openclaw": { "emoji": "🧠" } }
allowed-tools: ["exec", "read"]
user-invocable: true
---

# DTIClaw RAG — Retrieval Basis Pengetahuan Lokal

Retrieval lokal. Embedding **bge-m3** (Ollama) + cosine (numpy). Store: `workspace/rag_store`.

## KAPAN memakai (penting — jangan ngawur)

- ✅ Pertanyaan tentang **data akademik internal**: jadwal kuliah/kelas/ruang, dosen, kurikulum, kalender akademik, peraturan akademik DTI/ITS.
- ❌ Obrolan umum / opini / pengetahuan umum → jawab langsung tanpa tool.
- ❌ Info terkini/eksternal dari internet → pakai skill **dticlaw-research**.

## Cara pakai (WAJIB via venv `$DTICLAW_PY`, jalankan dengan `exec`)

```bash
# Cari (knowledge base sudah ter-index)
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-rag/scripts/rag.py" \
  --store "$DTICLAW_DIR/workspace/rag_store" search "<pertanyaan>" --k 5

# Lihat dokumen ter-index
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-rag/scripts/rag.py" \
  --store "$DTICLAW_DIR/workspace/rag_store" status

# Tambah dokumen (.md .txt .pdf .docx .csv .html .json)
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-rag/scripts/rag.py" \
  --store "$DTICLAW_DIR/workspace/rag_store" ingest "<path-file>"
```

## Alur menjawab

1. `search` dengan query pengguna.
2. Baca `hits` (JSON: score, source, chunk, text).
3. Jawab **hanya dari isi hits** — jangan mengarang.
4. Sitasi: `[Sumber: <source>, chunk <n>]`.
5. Jika hits tidak relevan/kosong: katakan data tidak ditemukan di basis pengetahuan.

## Basis pengetahuan saat ini

Jadwal Perkuliahan DTI, Data Dosen, Kalender Akademik ITS 2025-2026, Peraturan Akademik. Cek terbaru via `status`.
