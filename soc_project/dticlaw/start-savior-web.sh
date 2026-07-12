#!/bin/bash
# Launcher Savior agent web (dashboard-server, embedded agent -> savior_v2)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export OPENCLAW_STATE_DIR="$SCRIPT_DIR/.dticlaw-state"
export OPENCLAW_HOME="$SCRIPT_DIR/.dticlaw-home"
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export DTICLAW_UI_PORT="${DTICLAW_UI_PORT:-3737}"
exec node scripts/dashboard-server.mjs
