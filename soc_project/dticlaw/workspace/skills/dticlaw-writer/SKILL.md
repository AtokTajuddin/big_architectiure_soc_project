---
name: dticlaw-writer
description: "Generate dokumen profesional DOCX, PDF, Excel (XLSX), CSV. Technical writing, laporan, proposal, ekspor data — rapi, terstruktur, tanpa basa-basi."
metadata: { "openclaw": { "emoji": "📄" } }
allowed-tools: ["write", "read", "exec"]
user-invocable: true
---

# DTIClaw Technical Writer

Pembuatan dokumen bersih: **DOCX, PDF, XLSX, CSV**. Output ke `output/`.

## KAPAN memakai (jangan ngawur)

- ✅ Pengguna minta **file/dokumen** (laporan, proposal, ekspor tabel) dalam docx/pdf/xlsx/csv.
- ❌ Jawaban teks biasa di chat → tulis langsung, tanpa bikin file.

## Alur

1. Susun konten dulu sebagai **markdown** (untuk docx/pdf) atau **JSON/CSV** (untuk xlsx/csv) — pakai tool `write` ke file sementara di `/tmp`.
2. Jalankan script generator via `exec` dengan `$DTICLAW_PY`.
3. Beri tahu pengguna path hasil di `output/`.

## DOCX (markdown → docx)

```bash
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-writer/scripts/docx_writer.py" \
  --title "Judul" --author "Atok Tajuddin" \
  --input /tmp/konten.md --output "$DTICLAW_DIR/output/laporan.docx"
```

## PDF (markdown → pdf)

```bash
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-writer/scripts/pdf_writer.py" \
  --title "Judul" --author "Atok Tajuddin" \
  --input /tmp/konten.md --output "$DTICLAW_DIR/output/laporan.pdf"
```

## Excel / CSV (JSON atau CSV → xlsx/csv)

Input JSON: `{"sheets":[{"name":"Data","rows":[["Kolom1","Kolom2"],["a","b"]]}]}` atau list baris.

```bash
$DTICLAW_PY "$DTICLAW_DIR/workspace/skills/dticlaw-writer/scripts/xlsx_writer.py" \
  --input /tmp/data.json --output "$DTICLAW_DIR/output/data.xlsx" --title "Data"
# .csv otomatis bila output berakhiran .csv
```

## Aturan tulisan (tanpa slop)

- ❌ Hindari: "Di era digital ini...", "Perlu dicatat bahwa...", rantai "Selain itu, lebih lanjut...".
- ✅ Mulai dari temuan terpenting; poin > paragraf; angka spesifik + sitasi; kalimat aktif; EYD untuk dokumen formal.
- ❌ Jangan mengarang data/statistik.
