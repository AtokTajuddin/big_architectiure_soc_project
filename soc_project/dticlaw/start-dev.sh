#!/bin/bash
# Start Savior agent (gateway + dashboard) locally

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export DTICLAW_GATEWAY_PORT=18889
export DTICLAW_UI_PORT=3737

# Savior agent: pakai config & persona dari repo + model savior_v2 (Ollama, GPU)
export OPENCLAW_STATE_DIR="$SCRIPT_DIR/.dticlaw-state"
export OPENCLAW_HOME="$SCRIPT_DIR/.dticlaw-home"
# Ollama perlu "auth" agar provider terdaftar di OpenClaw (nilai apa saja diterima)
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

# Create log dir
mkdir -p /tmp/dticlaw-logs

echo "📦 Starting Savior agent..."
echo ""

# Start gateway (--dev flag shifts port to 18789)
echo "🌐 Gateway (port 18789, dev mode)..."
node openclaw.mjs --dev gateway run --allow-unconfigured > /tmp/dticlaw-logs/gateway.log 2>&1 &
GATEWAY_PID=$!
echo "  PID: $GATEWAY_PID"

# Wait for gateway to start
sleep 4

# Start dashboard server (with dev gateway port)
echo "🎨 Dashboard (port 3737)..."
DTICLAW_GATEWAY_PORT=18789 node scripts/dashboard-server.mjs > /tmp/dticlaw-logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "  PID: $DASHBOARD_PID"

sleep 2

echo ""
echo "✅ Savior agent is running!"
echo ""
echo "📍 Web Interface: http://127.0.0.1:3737"
echo "🔌 Gateway API: http://127.0.0.1:18789 (dev mode)"
echo ""
echo "📋 Logs:"
echo "  Gateway:  /tmp/dticlaw-logs/gateway.log"
echo "  Dashboard: /tmp/dticlaw-logs/dashboard.log"
echo ""
echo "⏹️  To stop: kill $GATEWAY_PID $DASHBOARD_PID"
echo "   or: pkill -f 'node.*openclaw\|node.*dashboard'"
echo ""

# Keep script running
wait $GATEWAY_PID $DASHBOARD_PID 2>/dev/null || true
