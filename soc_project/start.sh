#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  SOC Mini — One-shot startup script
#  Usage: bash start.sh [--build] [--rebuild-cve] [--clean]
#
#  --build        : Force rebuild Docker images
#  --rebuild-cve  : Download CISA KEV + retrain ML model before start
#  --clean        : Remove all containers + volumes (fresh start)
# ════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BLUE}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

DO_BUILD=false; DO_REBUILD_CVE=false; DO_CLEAN=false
for arg in "$@"; do
  case $arg in
    --build)       DO_BUILD=true ;;
    --rebuild-cve) DO_REBUILD_CVE=true ;;
    --clean)       DO_CLEAN=true ;;
    *) warn "Unknown arg: $arg" ;;
  esac
done

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     SOC Mini — Security Operations Center Stack             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Prerequisite checks ───────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || err "Docker not found. Install Docker first."
docker info >/dev/null 2>&1       || err "Docker daemon not running. Start it first."
[ -f ".env" ] || { warn ".env not found — copying from SOC_Local/.env"; cp ../.env .env 2>/dev/null || warn "Could not copy .env, using defaults"; }

# ── Ensure log directories exist (required by tetragon + suricata) ────────────
info "Creating required log directories..."
mkdir -p logs/suricata
touch logs/suricata/eve.json 2>/dev/null || true
touch logs/tetragon.log 2>/dev/null || true
# Tetragon expects this path
mkdir -p logs && touch logs/tetragon.log 2>/dev/null || true

# ── Optional: clean ───────────────────────────────────────────────────────────
if $DO_CLEAN; then
  warn "Cleaning all containers and volumes..."
  docker compose down -v --remove-orphans 2>/dev/null || true
  log "Clean done"
fi

# ── Optional: rebuild CVE knowledge base on host ──────────────────────────────
if $DO_REBUILD_CVE; then
  info "Rebuilding CVE knowledge base (CISA KEV + MITRE + signatures)..."
  VENV_PY="$(dirname $0)/../.venv/bin/python"
  if [ -f "$VENV_PY" ]; then
    cd soc-dashboard && "$VENV_PY" src/build_cve_kb.py --bake-only 2>&1 | grep -E "(✓|→|DONE|ERROR|rows|CVEs|Saved)"
    cd ..
    log "CVE knowledge base rebuilt"
  else
    warn "Virtual env not found at ../.venv — skipping local rebuild"
    warn "CVE KB will be built inside Docker during image build"
  fi
fi

# ── Build images ──────────────────────────────────────────────────────────────
BUILD_ARGS=""
if $DO_BUILD; then
  info "Building Docker images (this may take 3-5 min first time)..."
  BUILD_ARGS="--build"
fi

# Always build if images don't exist
if ! docker image inspect soc-ml-engine:latest >/dev/null 2>&1; then
  info "ML engine image not found — building (includes CVE KB)..."
  BUILD_ARGS="--build"
fi
if ! docker image inspect soc-misp-exporter:latest >/dev/null 2>&1; then
  info "MISP exporter image not found — building..."
  BUILD_ARGS="--build"
fi
if ! docker image inspect soc-shuffle-exporter:latest >/dev/null 2>&1; then
  info "Shuffle exporter image not found — building..."
  BUILD_ARGS="--build"
fi

# ── Start stack ───────────────────────────────────────────────────────────────
info "Starting SOC stack..."
docker compose up -d $BUILD_ARGS --remove-orphans

# ── Wait for core services ────────────────────────────────────────────────────
info "Waiting for core services to be healthy..."
wait_healthy() {
  local name="$1"; local max_wait="${2:-60}"; local elapsed=0
  while [ $elapsed -lt $max_wait ]; do
    status=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "none")
    [ "$status" = "healthy" ] && return 0
    [ "$status" = "none" ] && return 0  # no healthcheck, assume ok
    sleep 3; elapsed=$((elapsed+3))
    echo -n "."
  done
  echo ""
  warn "$name did not become healthy in ${max_wait}s (status: $status)"
  return 1
}

echo -n "  VictoriaMetrics "; wait_healthy victoriametrics 60 && log "VictoriaMetrics OK"
echo -n "  VictoriaLogs    "; wait_healthy victorialogs   60 && log "VictoriaLogs OK"
echo -n "  ML Engine       "; wait_healthy ml-engine      90 && log "ML Engine OK"
echo -n "  Grafana         "; wait_healthy grafana        90 && log "Grafana OK"

# ── Status report ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  SOC Stack Running!                                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
printf "  %-22s %s\n" "Service" "URL"
printf "  %-22s %s\n" "──────────────────────" "───────────────────────────────"
printf "  %-22s %s\n" "Grafana"          "http://localhost:3000    (admin / minisoc2026)"
printf "  %-22s %s\n" "DVWA"             "http://localhost:8080"
printf "  %-22s %s\n" "ML Engine"        "http://localhost:8000"
printf "  %-22s %s\n" "ML Report"        "http://localhost:8000/report"
printf "  %-22s %s\n" "ML CVE Lookup"    "http://localhost:8000/cve-lookup"
printf "  %-22s %s\n" "VictoriaMetrics"  "http://localhost:8428/vmui"
printf "  %-22s %s\n" "Loki/VL"          "http://localhost:9428"
printf "  %-22s %s\n" "Benthos"          "http://localhost:4195"
printf "  %-22s %s\n" "MISP"             "http://localhost:8081    (admin@misp.local / Admin1234!)"
printf "  %-22s %s\n" "Shuffle"          "http://localhost:3001    (admin / Admin1234!)"
echo ""

# ── ML health check ───────────────────────────────────────────────────────────
ML_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
echo "  ML Engine Status:"
echo "$ML_HEALTH" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(f'    Models     : {d.get(\"models\",[])}')
    print(f'    Remediator : {\"✓\" if d.get(\"remediator\") else \"✗\"}')
    print(f'    CVE Sigs   : {d.get(\"cve_signatures\",0)} patterns')
    print(f'    KEV CVEs   : {d.get(\"kev_cves\",0)} actively exploited')
except: print('    (could not parse health response)')
" 2>/dev/null || echo "    (ML engine starting...)"

echo ""
echo "  Quick test:"
echo "  bash test_inject_all.sh"
echo ""
echo "  Retrain model:"
echo "  curl -X POST http://localhost:8000/retrain"
echo ""
echo "  Stop stack:"
echo "  docker compose down"
echo ""
