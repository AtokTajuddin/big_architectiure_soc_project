---
name: dticlaw-rag
description: "Document ingestion, indexing, and retrieval via TurboVec (primary) or ChromaDB (fallback). Supports PDF, DOCX, MD, TXT, CSV, HTML. Use for knowledge base queries."
metadata: { "openclaw": { "emoji": "🧠" } }
allowed-tools: ["write", "read", "exec", "web_fetch"]
user-invocable: true
---

# DTIClaw RAG Engine

Retrieval-Augmented Generation untuk knowledge base pribadi. Primary: TurboVec (Rust quantized index). Fallback: ChromaDB.

## Architecture

```
Documents → Ingestion Pipeline → Chunk + Embed → Vector Index
                                                    ↓
User Query → Embed Query → Vector Search → Retrieve Top-K → LLM Synthesis
```

## Quick Start

```bash
# Index a file
bash scripts/turbovec.sh add ~/dticlaw/knowledge/mydoc.pdf

# Index a URL
bash scripts/turbovec.sh url https://example.com/article

# Search
bash scripts/turbovec.sh search "apa itu FHIR" --k 5

# Status
bash scripts/turbovec.sh status
```

## Supported Formats

| Format | Extensions | Parser |
|--------|-----------|--------|
| PDF | .pdf | pypdf / pdfplumber |
| Word | .docx | python-docx |
| Markdown | .md | raw text |
| Plain Text | .txt | raw text |
| HTML | .html | BeautifulSoup |
| CSV | .csv | csv module |
| JSON | .json | json module |

## TurboVec (Primary)

- Engine: `~/dticlaw/engines/turbovec/` (Python + Rust)
- Embedding: Ollama `nomic-embed-text` (768 dim, 4-bit quantized)
- Speed: ~0.6ms search (80x faster than ChromaDB)
- RAM: 8x lebih hemat dari FAISS

## ChromaDB (Fallback)

```bash
# Start ChromaDB
chroma run --path ~/dticlaw/data/chromadb --port 8001 &

# Ingest
python3 skills/dticlaw-rag/scripts/rag_ingest.py \
  --input ~/dticlaw/knowledge/ \
  --collection dticlaw_docs

# Search
python3 skills/dticlaw-rag/scripts/rag_search.py \
  --query "query text" \
  --collection dticlaw_docs \
  --k 5
```

## Citation Format

Always cite retrieved documents:
```
[Source: filename.pdf, chunk 3]
[Source: https://example.com/article, §2]
```

## Dependencies

- Python: `chromadb`, `pypdf`, `python-docx`, `beautifulsoup4`
- Ollama: `nomic-embed-text` (auto-pull if missing)
