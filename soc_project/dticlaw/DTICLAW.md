# 🛡️ Savior agent — SOC Companion for savior_v2

**Version:** v0.2.0-alpha
**Owner:** Atok Tajuddin & tim researcher
**Base:** OpenClaw (hardened fork)
**Model:** savior_v2 (Llama-Primus, fine-tune SOC, Ollama/GPU)

## What is Savior agent?

Savior agent is a hardened, skill-enhanced fork of OpenClaw, repurposed as a SOC companion for the
**savior_v2** model. It analyzes Wazuh alerts, labels TRUE POSITIVE vs FALSE POSITIVE vs FALSE
NEGATIVE, and — with controlled access — can call the Wazuh API and Shuffle webhook (via
`scripts/savior-bridge.py`) to inspect logs and take action.

## Skills

| Skill | Trigger | Capability |
|-------|---------|------------|
| 🔬 **dticlaw-research** | Research, analisis, cari tahu | Multi-hop web search → fetch → synthesize with citations |
| 📄 **dticlaw-writer** | Bikin dokumen, report, export | DOCX, XLSX, CSV generation — clean, zero slop |
| 🧠 **dticlaw-rag** | Dari dokumen, knowledge base | TurboVec + ChromaDB document ingestion & retrieval |
| 🛡️ **dticlaw-guardian** | (auto-active) | P0-P3 permission gate, injection detection, audit trail |

## Quick Install

```bash
# 1. Extract
tar -xzf dticlaw.tar.gz
cd dticlaw

# 2. Install
bash install.sh

# 3. Run
node openclaw.mjs gateway --config $HOME/dticlaw/config.json
```

## Architecture

```
OpenClaw Runtime (fork)
├── Skills System
│   ├── dticlaw-research    ← web_search + web_fetch + synthesis
│   ├── dticlaw-writer      ← python-docx + openpyxl
│   ├── dticlaw-rag         ← TurboVec (Rust) + ChromaDB
│   └── dticlaw-guardian    ← permission gate + hallucination guard
├── Memory (SQLite FTS5)    ← conversation memory
├── TurboVec                ← vector search engine
└── Ollama                  ← local models
```

## Security

- P0-P3 permission classification
- Prompt injection detection (18 patterns)
- External content wrapping (random boundary markers)
- LLM special token sanitization
- Unicode homoglyph detection
- Config mutation lock + hash protection
- Filesystem policy enforcement
- Tool policy profiles

## Requirements

- Node.js 22+
- Ollama (optional, for local LLM)
- Python 3 (optional, for DOCX/RAG)

## License

MIT (inherited from OpenClaw)
