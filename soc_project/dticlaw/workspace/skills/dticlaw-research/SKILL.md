---
name: dticlaw-research
description: "Riset web (DuckDuckGo/DDGS, tanpa API key) + analisis mendalam dengan sintesis & sitasi. Untuk info terkini/eksternal, studi literatur, market intel."
metadata: { "openclaw": { "emoji": "🔬" } }
allowed-tools: ["exec", "read", "write"]
user-invocable: true
---

# DTIClaw Deep Research

Riset web lokal via **DDGS** (DuckDuckGo, tanpa API key) + sintesis multi-sumber.

## KAPAN memakai (jangan ngawur)

- ✅ Info **terkini/eksternal** dari internet, studi literatur, tren, fakta yang tidak ada di basis pengetahuan lokal.
- ❌ Data akademik internal (jadwal/dosen/kurikulum) → pakai **dticlaw-rag**.
- ❌ Pertanyaan umum yang sudah kamu tahu → jawab langsung.

## Cara pakai (WAJIB via `$DTICLAW_PY`, jalankan dengan `exec`)

```bash
# Cari saja (judul + cuplikan + url)
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-research/scripts/web_search.py" \
  --query "<topik>" --max 6

# Cari + ambil & ekstrak isi N halaman teratas (untuk analisis mendalam)
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-research/scripts/web_search.py" \
  --query "<topik>" --max 6 --fetch 3 --chars 2000
```

Output JSON: `{query, count, results:[{title,url,snippet,page?}]}`.

## Alur (horizon looping)

1. **Rencana**: pecah pertanyaan kompleks → 2-4 sub-pertanyaan.
2. **Cari**: jalankan `web_search.py` per sub-pertanyaan; pakai `--fetch` bila perlu isi halaman.
3. **Validasi**: bandingkan antar sumber; tandai sepakat/kontradiksi/celah.
4. **Sintesis**: rangkum per sub-topik dengan sitasi `[Sumber: url]`.
5. **Tindak lanjut** (maks 2-3 putaran) bila ada celah.

## Keamanan

- Jangan mengarang sitasi — tandai "tidak ditemukan" bila nihil.
- Tandai tingkat keyakinan bila relevan (TINGGI/SEDANG/RENDAH).
- Bahasa Indonesia default.
