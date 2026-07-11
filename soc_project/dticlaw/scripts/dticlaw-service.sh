#!/usr/bin/env bash
# DTIClaw detached launcher
set -euo pipefail

DTICLAW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 18789 is the gateway port the CLI derives by default for a local-loopback
# config; matching it lets `openclaw agent/status` reach this running gateway
# instead of falling back to a fresh embedded runtime each call.
GATEWAY_PORT="${DTICLAW_GATEWAY_PORT:-18789}"
UI_PORT="${DTICLAW_UI_PORT:-3737}"
PID_DIR="$DTICLAW_DIR/.dticlaw-pids"

export OPENCLAW_HOME="$DTICLAW_DIR/.dticlaw-home"
export OPENCLAW_STATE_DIR="$DTICLAW_DIR/.dticlaw-state"
export OPENCLAW_CONFIG_PATH="$DTICLAW_DIR/.dticlaw-state/openclaw.json"
export OLLAMA_HOST="127.0.0.1:11434"
# Ollama is local; OpenClaw still requires a non-empty API key to register it
# as a provider, otherwise ollama/* models resolve as "Unknown model".
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-local}"

mkdir -p "$PID_DIR"
mkdir -p "$OPENCLAW_STATE_DIR"/{logs,data}
mkdir -p "$DTICLAW_DIR/workspace"

start_bwrap() {
    local name="$1"; shift
    local pidfile="$PID_DIR/$name.pid"
    local logfile="$OPENCLAW_STATE_DIR/logs/$name.log"
    # Detached daemon: setsid + redirect IO + pidfile lifecycle.
    # No --die-with-parent here (it would kill the sandbox the moment this
    # launcher shell exits); `stop` manages teardown via the pidfile instead.
    setsid bwrap \
        --new-session \
        --unshare-user \
        --unshare-ipc \
        --unshare-pid \
        --unshare-uts \
        --unshare-cgroup \
        --hostname "dticlaw-$name" \
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
        --setenv DTICLAW_GATEWAY_PORT "$GATEWAY_PORT" \
        --setenv DTICLAW_UI_PORT "$UI_PORT" \
        --setenv DTICLAW_DIR "$DTICLAW_DIR" \
        --setenv DTICLAW_PY "$DTICLAW_DIR/.venv/bin/python" \
        --setenv OPENCLAW_TELEMETRY off \
        --setenv NODE_ENV production \
        "$@" \
        </dev/null >"$logfile" 2>&1 &
    echo $! > "$pidfile"
}

case "${1:-run}" in
    start)
        if [ -f "$PID_DIR/gateway.pid" ] && kill -0 "$(cat "$PID_DIR/gateway.pid")" 2>/dev/null; then
            echo "DTIClaw already running"
            exit 0
        fi
        echo "Starting DTIClaw Gateway on port $GATEWAY_PORT..."
        start_bwrap gateway node "$DTICLAW_DIR/openclaw.mjs" gateway run --port "$GATEWAY_PORT" --bind loopback --auth none --allow-unconfigured
        echo "Starting DTIClaw Dashboard on port $UI_PORT..."
        start_bwrap dashboard node "$DTICLAW_DIR/scripts/dashboard-server.mjs"
        echo "Waiting for services..."
        for i in $(seq 1 30); do
            curl -s --max-time 1 "http://127.0.0.1:$GATEWAY_PORT/healthz" >/dev/null 2>&1 && curl -s --max-time 1 "http://127.0.0.1:$UI_PORT/" >/dev/null 2>&1 && break
            sleep 1
        done
        echo "✅ Dashboard: http://127.0.0.1:$UI_PORT"
        echo "✅ Gateway API: http://127.0.0.1:$GATEWAY_PORT"
        ;;
    stop)
        # pidfile stores the setsid PID, which exits right after forking bwrap,
        # so a pidfile-only stop leaves the sandboxed listener orphaned. Kill the
        # pidfile group first, then reap by port to guarantee teardown.
        for svc in gateway dashboard; do
            pidfile="$PID_DIR/$svc.pid"
            if [ -f "$pidfile" ]; then
                pid=$(cat "$pidfile" 2>/dev/null) || true
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
                fi
                rm -f "$pidfile"
            fi
        done
        fuser -k "${GATEWAY_PORT}/tcp" "${UI_PORT}/tcp" 2>/dev/null || true
        echo "Stopped"
        ;;
    status)
        # Port liveness is the source of truth; pidfiles go stale via setsid.
        for svc in gateway:$GATEWAY_PORT dashboard:$UI_PORT; do
            name="${svc%%:*}"; port="${svc##*:}"
            if ss -ltn 2>/dev/null | grep -q "127.0.0.1:${port} "; then
                echo "$name: running (port $port)"
            else
                echo "$name: not running"
            fi
        done
        ;;
    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;
    run)
        "$0" start
        tail -f /dev/null
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|run}"
        exit 1
        ;;
esac
