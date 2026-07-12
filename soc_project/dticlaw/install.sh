#!/usr/bin/env bash
# ============================================================
# DTIClaw Installer v0.1.0-alpha
# One-command setup: clone → install → ready
# ============================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DTICLAW_HOME="${DTICLAW_HOME:-$HOME/dticlaw}"
DTICLAW_WORKSPACE="$DTICLAW_HOME/workspace"

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════╗"
echo "║   🦞 DTIClaw Installer v0.1.0-alpha      ║"
echo "║   Digital Twin Intelligence Claw         ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Pre-flight Checks ───
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

command -v node >/dev/null 2>&1 || { echo -e "${RED}Node.js 22+ required${NC}"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo -e "${RED}npm required${NC}"; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo -e "${YELLOW}⚠️  Ollama not found (optional for local LLM)${NC}"; }
command -v python3 >/dev/null 2>&1 || { echo -e "${YELLOW}⚠️  Python 3 not found (optional for DOCX/PDF/RAG)${NC}"; }

NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VER" -lt 22 ]; then
    echo -e "${RED}Node.js 22+ required, found: $(node -v)${NC}"
    exit 1
fi
echo -e "${GREEN}  ✅ Node $(node -v)${NC}"

# ─── Install Dependencies ───
echo -e "${YELLOW}[2/6] Installing npm dependencies...${NC}"
npm install --legacy-peer-deps 2>&1 | tail -1
echo -e "${GREEN}  ✅ npm packages installed${NC}"

# ─── Setup Workspace ───
echo -e "${YELLOW}[3/6] Setting up DTIClaw workspace...${NC}"
mkdir -p "$DTICLAW_HOME"/{workspace,memory,logs,data/{turbovec,chromadb},output,knowledge}

# Symlink skills ke workspace
mkdir -p "$DTICLAW_WORKSPACE/skills"
for skill in dticlaw-research dticlaw-writer dticlaw-rag dticlaw-guardian; do
    if [ -d "skills/$skill" ]; then
        cp -r "skills/$skill" "$DTICLAW_WORKSPACE/skills/"
    fi
done
echo -e "${GREEN}  ✅ Workspace ready: $DTICLAW_HOME${NC}"

# ─── Setup Config ───
echo -e "${YELLOW}[4/6] Setting up configuration...${NC}"
if [ ! -f "$DTICLAW_HOME/config.json" ]; then
    cat > "$DTICLAW_HOME/config.json" << 'CONFEOF'
{
  "gateway": { "port": 18889, "bind": "loopback", "auth": "none" },
  "agents": {
    "defaults": {
      "model": "ollama/gemma2:9b",
      "workspace": "REPLACE_DTICLAW_HOME/workspace"
    }
  },
  "skills": {
    "entries": {
      "dticlaw-research": { "enabled": true },
      "dticlaw-writer": { "enabled": true },
      "dticlaw-rag": { "enabled": true },
      "dticlaw-guardian": { "enabled": true }
    },
    "config": {
      "searchPaths": ["REPLACE_DTICLAW_HOME/workspace/skills"]
    }
  }
}
CONFEOF
    # Replace placeholder
    sed -i "s|REPLACE_DTICLAW_HOME|$DTICLAW_HOME|g" "$DTICLAW_HOME/config.json"
fi
echo -e "${GREEN}  ✅ Config: $DTICLAW_HOME/config.json${NC}"

# ─── Pull Models ───
echo -e "${YELLOW}[5/6] Checking Ollama models...${NC}"
if command -v ollama >/dev/null 2>&1; then
    for model in nomic-embed-text gemma2:9b llama3.1:8b gemma3:1b; do
        if ! ollama list 2>/dev/null | grep -q "$model"; then
            echo "  Pulling $model..."
            ollama pull "$model" 2>&1 | tail -1 || echo "  ⚠️  Could not pull $model"
        else
            echo "  ✅ $model"
        fi
    done
fi

# ─── Finalize ───
echo -e "${YELLOW}[6/6] Finalizing...${NC}"

# Copy .env
if [ ! -f "$DTICLAW_HOME/.env" ]; then
    cp .env.example "$DTICLAW_HOME/.env" 2>/dev/null || true
fi

# Create initial memory
DATE_TAG=$(date +%Y-%m-%d)
mkdir -p "$DTICLAW_HOME/memory"
cat > "$DTICLAW_HOME/memory/$DATE_TAG.md" << MEMEOF
# $DATE_TAG — DTIClaw First Run

## System Initialized
- **Date:** $(date)
- **Version:** v0.1.0-alpha
- **Host:** $(hostname)

## Active Skills
- dticlaw-research (deep multi-hop web research)
- dticlaw-writer (DOCX, PDF, Excel, CSV generator)
- dticlaw-rag (TurboVec + ChromaDB RAG)
- dticlaw-guardian (permission gate + anti-hallucination)

## Security
- Permission gate: strict (P0-P3)
- Prompt injection guard: active
- Workspace isolated
MEMEOF

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ DTIClaw v0.1.0-alpha Ready! 🦞      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Home:${NC}     $DTICLAW_HOME"
echo -e "  ${BLUE}Workspace:${NC} $DTICLAW_WORKSPACE"
echo -e "  ${BLUE}Config:${NC}   $DTICLAW_HOME/config.json"
echo ""
echo -e "  ${YELLOW}Quick Start:${NC}"
echo "    1. cd $DTICLAW_HOME"
echo "    2. node openclaw.mjs gateway --config $DTICLAW_HOME/config.json"
echo "    3. Open http://127.0.0.1:18889 (dashboard)"
echo ""
echo -e "  ${YELLOW}Or use npm:${NC}"
echo "    npm run dticlaw:gateway"
echo ""
