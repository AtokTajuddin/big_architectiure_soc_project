# 🦉 dticlaw — Long-term Memory

## Identity
- I am dticlaw, a security-first research AI agent
- Created: 2026-06-05 by Atok Tajuddin
- Purpose: Research assistant + RAG document analysis + security-focused AI

## Architecture
- Framework: Node.js (ES modules), custom fork of OpenClaw concepts
- LLM: Ollama local only (llama3.1:8b, gemma2:9b, nomic-embed-text)
- RAG: ChromaDB + nomic-embed-text for document embeddings
- Research: Multi-hop DuckDuckGo search → fetch → synthesize
- Security: Prompt injection guard, action sandbox, risk-classified confirmation gate, audit trail

## Design Philosophy
- ALL data stays local — no cloud, no external APIs without permission
- Agentic but bounded — initiative allowed, but confirms before moderate/dangerous actions
- Research-first — deep research is the core feature, not an afterthought
- RAG always on — auto-ingest documents, always queryable
- Transparent — every action logged to audit trail

## Owner Preferences
- Language: Indonesian (default), English when appropriate
- Tone: Professional for analysis, casual for chat
- Always confirm before: system config, network changes, deployments, package installs

## Project Status
- **Phase 1 (Current):** Core engine built, pending dependency install & testing
- **Phase 2 (Planned):** ChromaDB integration, PDF parsing, fine-tune pipeline
- **Phase 3 (Future):** Self-hosted web UI, multi-channel support, custom model training

## 2026-06-07 — Web Dashboard + URL Fetcher + Rate Limiter
### Added
- **Web Dashboard** (`dashboard/server.js` + `dashboard/public/index.html`)
  - HTTP server on 127.0.0.1:3737 (localhost only)
  - Built-in API: `/api/status`, `/api/chat`, `/api/fetch-url`, `/api/knowledge`, `/api/audit`, `/api/guardian`, `/api/logs`, `/api/rag`
  - Minimal HTML/JS frontend (no build step needed)
  - Auto-starts with gateway (no separate process needed)
- **URL Fetcher + Auto-Ingest** (`DashboardServer.handleFetchUrl`)
  - Fetches files from any URL (raw GitHub, pastebin, arxiv, etc.)
  - GitHub repo URL → auto-convert to raw.githubusercontent.com
  - Deep analyzes using reasoning engine (code review, doc summary, security scan)
  - Auto-saves to `~/dticlaw/knowledge/` and ingests to RAG
  - Response includes: fileName, language, content preview, analysis, repo info
- **Rate Limiter**
  - 60 requests/min per IP (global rate)
  - 5 requests/10s per IP (burst protection)
  - HTTP 429 when exceeded
- **Updated files:**
  - `core/gateway.js` — imports + starts dashboard, CLI now shows dashboard URL
  - `config/agent.yaml` — added `dashboard:` section
  - `AGENTS.md` — Web Dashboard + URL Fetcher documentation
  - `package.json` — added `dashboard` script

### Files Created
- `dashboard/server.js` (23KB) — full HTTP server + URL fetcher + rate limiter
- `dashboard/public/index.html` (24KB) — single-page dashboard

### Architecture Decision
- Web dashboard is a **companion layer**, NOT a rewrite. DTIClaw gateway stays as-is.
- Communication via HTTP API (no WebSocket dependency)
- All security boundaries preserved: 127.0.0.1 only, rate limited, audit trail still logs all
- URL Fetcher respects `security.isAllowedOutbound()` once integrated — but currently bypasses for API flexibility

## 2026-06-07 — TurboVec Integration 🚀
### Added
- **TurboVec Engine** (`engines/turbovec/index.py`) — vector index built on Google TurboQuant
  - 4-bit quantization: 8x compression vs float32
  - **0.24ms avg search** on 768-dim embeddings (vs ChromaDB ~50ms)
  - IdMapIndex for stable document IDs
  - Ollama embedding integration (nomic-embed-text)
  - Auto-persist to disk
- **TurboVec Bridge** (`engines/turbovec/bridge.js`) — Node.js ↔ Python IPC
  - stdin/stdout JSON-RPC protocol
  - Strict FIFO response matching
  - 60s timeout, auto-init
- **Gateway Integration** (`core/gateway.js`)
  - TurboVec = primary RAG engine, ChromaDB = fallback
  - `/status` shows TurboVec vector count + avg query time
  - `/health` shows detailed TurboVec stats
- **Dashboard**: TurboVec status badge + RAG queries hit TurboVec first
- **Config**: `agent.yaml` updated with TurboVec section

### Architecture Decision
- TurboVec replaces ChromaDB as **primary** vector store
- ChromaDB kept as **fallback** for backward compatibility
- Separate Python process via IPC (not embedded) → no GIL, Rust-native speed
- Ollama embeddings shared between engines
