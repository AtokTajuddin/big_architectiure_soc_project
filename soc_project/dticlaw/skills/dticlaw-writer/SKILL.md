---
name: dticlaw-writer
description: "Generate professional DOCX, PDF, Excel, CSV documents. Technical writing, reports, proposals, data exports — clean, structured, zero AI slop."
metadata: { "openclaw": { "emoji": "📄" } }
allowed-tools: ["write", "read", "exec", "web_fetch"]
user-invocable: true
---

# DTIClaw Technical Writer

Clean document generation tanpa filler paragraphs. Support: DOCX, XLSX, CSV, Markdown → PDF.

## Document Types

| Type | Format | Use Case |
|------|--------|----------|
| Research Report | DOCX | Deep research output, academic |
| Technical Proposal | DOCX | Project proposals, architecture docs |
| Data Export | XLSX/CSV | Structured data, tables, analysis |
| Meeting Notes | DOCX/MD | Rapat, interview, diskusi |
| Presentation Outline | MD | Slide decks, pitch decks |
| Quick Summary | MD/PDF | Ringkasan cepat |

## DOCX Generation (via Python)

Gunakan script `scripts/docx_writer.py`:

```bash
python3 skills/dticlaw-writer/scripts/docx_writer.py \
  --title "Judul Dokumen" \
  --author "Atok Tajuddin" \
  --input research.md \
  --output ~/dticlaw/output/report.docx
```

## Excel/CSV Export

```bash
python3 skills/dticlaw-writer/scripts/table_writer.py \
  --input data.json \
  --format xlsx \
  --output ~/dticlaw/output/data.xlsx
```

## Writing Rules (Zero Slop)

### NEVER DO:
- ❌ "In conclusion..." / "Kesimpulannya..."
- ❌ "In today's fast-paced world..." / "Di era digital ini..."
- ❌ "It is important to note that..." / "Perlu dicatat bahwa..."
- ❌ "Furthermore, additionally, moreover" chains
- ❌ Fake statistics, fabricated data
- ❌ Vague claims tanpa sumber

### ALWAYS DO:
- ✅ Lead with the most important finding
- ✅ Bullet points > paragraphs (kecuali narasi)
- ✅ Data-driven: angka spesifik, kutip sumber
- ✅ Active voice: "Tim menemukan" bukan "Ditemukan oleh tim"
- ✅ Bahasa Indonesia EYD untuk dokumen formal
- ✅ Page numbers, headers, proper formatting

## Document Structure

```
1. Cover Page (title, author, date, institution)
2. Executive Summary (1 page max)
3. Table of Contents
4. Main Content (numbered sections)
5. References / Sources
6. Appendices (optional)
```

## Dependencies

- Python: `python-docx`, `openpyxl`, `weasyprint` (optional PDF)
- Install: `pip install python-docx openpyxl`
