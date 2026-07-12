#!/usr/bin/env bash
# ============================================================
# DTIClaw Sandbox Launcher — bubblewrap
# Gateway (API) di 18889, Dashboard (UI) di 3737
# FS dikurung ke folder dticlaw, network loopback-only
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DTICLAW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_PORT="${DTICLAW_GATEWAY_PORT:-18889}"
UI_PORT="${DTICLAW_UI_PORT:-3737}"

echo -e "${GREEN}🦞 DTIClaw Sandbox v0.1.0-alpha${NC}"
echo -e "  Root       : $DTICLAW_DIR"
echo -e "  Gateway    : http://127.0.0.1:${GATEWAY_PORT} (API)"
echo -e "  Dashboard  : http://127.0.0.1:${UI_PORT} (UI)"

export OPENCLAW_HOME="$DTICLAW_DIR/.dticlaw-home"
export OPENCLAW_STATE_DIR="$DTICLAW_DIR/.dticlaw-state"
export OPENCLAW_CONFIG_PATH="$DTICLAW_DIR/.dticlaw-state/openclaw.json"
export OLLAMA_HOST="127.0.0.1:11434"
# Local Ollama still needs a non-empty key to register as a provider.
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-local}"

mkdir -p "$OPENCLAW_STATE_DIR"/{logs,data}
mkdir -p "$DTICLAW_DIR/workspace"

cleanup() {
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $GATEWAY_PID 2>/dev/null || true
    kill $DASHBOARD_PID 2>/dev/null || true
    wait $GATEWAY_PID 2>/dev/null || true
    wait $DASHBOARD_PID 2>/dev/null || true
    echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT INT TERM

# Start OpenClaw Gateway
bwrap \
    --new-session \
    --die-with-parent \
    --unshare-user \
    --unshare-ipc \
    --unshare-pid \
    --unshare-uts \
    --unshare-cgroup \
    --hostname dticlaw-gw \
    --ro-bind /usr /usr \
    --ro-bind /lib /lib \
    --ro-bind /lib64 /lib64 \
    --ro-bind /etc /etc \
    --ro-bind "$OPENCLAW_STATE_DIR/hosts-block" /etc/hosts \
    --ro-bind /sys /sys \
    --proc /proc \
    --dev /dev \
    --tmpfs /run \
    --bind "$DTICLAW_DIR" "$DTICLAW_DIR" \
    --bind /tmp /tmp \
    --bind "$HOME/.ollama" "$HOME/.ollama" \
    --setenv HOME "$HOME" \
    --setenv USER "$USER" \
    --setenv OPENCLAW_HOME "$OPENCLAW_HOME" \
    --setenv OPENCLAW_STATE_DIR "$OPENCLAW_STATE_DIR" \
    --setenv OPENCLAW_CONFIG_PATH "$OPENCLAW_CONFIG_PATH" \
    --setenv OLLAMA_HOST "$OLLAMA_HOST" \
    --setenv OLLAMA_API_KEY "$OLLAMA_API_KEY" \
    --setenv OPENCLAW_TELEMETRY off \
    --setenv NODE_ENV production \
    node "$DTICLAW_DIR/openclaw.mjs" gateway run \
        --port "$GATEWAY_PORT" \
        --bind loopback \
        --auth none \
        --allow-unconfigured \
    &
GATEWAY_PID=$!

# Wait for gateway ready
echo -n "Waiting for gateway..."
for i in $(seq 1 30); do
    if curl -s --max-time 1 "http://127.0.0.1:${GATEWAY_PORT}/healthz" >/dev/null 2>&1; then
        echo " READY"
        break
    fi
    sleep 1
    echo -n "."
done

# Start Dashboard Server
bwrap \
    --new-session \
    --die-with-parent \
    --unshare-user \
    --unshare-ipc \
    --unshare-pid \
    --unshare-uts \
    --unshare-cgroup \
    --hostname dticlaw-ui \
    --ro-bind /usr /usr \
    --ro-bind /lib /lib \
    --ro-bind /lib64 /lib64 \
    --ro-bind /etc /etc \
    --ro-bind "$OPENCLAW_STATE_DIR/hosts-block" /etc/hosts \
    --ro-bind /sys /sys \
    --proc /proc \
    --dev /dev \
    --tmpfs /run \
    --bind "$DTICLAW_DIR" "$DTICLAW_DIR" \
    --bind /tmp /tmp \
    --setenv HOME "$HOME" \
    --setenv DTICLAW_UI_PORT "$UI_PORT" \
    --setenv DTICLAW_GATEWAY_PORT "$GATEWAY_PORT" \
    node "$DTICLAW_DIR/scripts/dashboard-server.mjs" \
    &
DASHBOARD_PID=$!

echo -e "${GREEN}Dashboard: http://127.0.0.1:${UI_PORT}${NC}"
echo "Press Ctrl+C to stop."

wait
