#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Mini SOC — Full Diagnose & Auto-Fix Script
# Working dir: /home/atok/home/soc_dev
# ─────────────────────────────────────────────────────────────────────────────
set -e
WORKDIR="/home/atok/home/soc_dev"
cd "$WORKDIR"

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[OK]${NC}    $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }
hr()    { echo "───────────────────────────────────────────────────────"; }

hr
echo "🔍 MINI SOC DIAGNOSE — $(date)"
hr

# ═══════════════════════════════════════════════════════════════════════════════
# 1. KERNEL & BPF CHECK
# ═══════════════════════════════════════════════════════════════════════════════
info "Kernel version: $(uname -r)"
info "Architecture: $(uname -m)"

if [ "$(uname -m)" = "aarch64" ]; then
  warn "⚠️  ARM64 detected! Tetragon v1.1.0 TIDAK support ARM."
  warn "   Gunakan: quay.io/cilium/tetragon:latest (v1.3+) atau skip tetragon di ARM"
fi

if [ -d /sys/kernel/debug/bpf ] || [ -d /sys/fs/bpf ]; then
  ok "BPF filesystem tersedia"
else
  warn "BPF filesystem tidak ditemukan — mount secara manual:"
  warn "  sudo mount -t bpf bpf /sys/fs/bpf"
  warn "  sudo mount -t debugfs nodev /sys/kernel/debug"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 2. NETWORK INTERFACE CHECK
# ═══════════════════════════════════════════════════════════════════════════════
hr
info "Network interfaces yang tersedia:"
ip -o link show up | awk -F': ' '{print "  → " $2}'

IFACE=$(ip -o link show up | awk -F': ' '{print $2}' | grep -v -E '^(lo|docker|veth|br-)' | head -1)
if [ -n "$IFACE" ]; then
  ok "Interface untuk Suricata: $IFACE"
else
  fail "Tidak ada interface yang bisa dideteksi! Cek ip link"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 3. CONTAINER STATUS
# ═══════════════════════════════════════════════════════════════════════════════
hr
info "Container status:"
docker compose ps 2>/dev/null || docker ps --filter "name=tetragon|suricata|victorialogs|victoriametrics|benthos|grafana" 2>/dev/null

hr
info "Container yang sedang Restarting:"
RESTARTING=$(docker ps --filter "status=restarting" --format "{{.Names}}" 2>/dev/null)
if [ -z "$RESTARTING" ]; then
  ok "Tidak ada container yang restart-loop"
else
  for CNAME in $RESTARTING; do
    fail "Container restart-loop: $CNAME"
    info "Last 30 baris log $CNAME:"
    docker logs --tail=30 "$CNAME" 2>&1 | sed 's/^/    /'
    hr
  done
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 4. TETRAGON SPECIFIC FIX
# ═══════════════════════════════════════════════════════════════════════════════
hr
info "Checking Tetragon..."
TLOG=$(docker logs --tail=50 tetragon 2>&1 || echo "")
if echo "$TLOG" | grep -q "level=fatal\|level=error\|failed to"; then
  fail "Tetragon ada error:"
  echo "$TLOG" | grep -E "level=fatal|level=error|failed to" | head -10 | sed 's/^/    /'

  # Cek apakah kernel support
  if echo "$TLOG" | grep -qi "arm\|architecture\|unsupported"; then
    fail "Tetragon TIDAK support arsitektur ini"
    warn "Fix: ganti image ke versi yang support ARM atau gunakan x86_64"
  fi

  if echo "$TLOG" | grep -qi "bpf\|debug\|permission"; then
    warn "BPF permission issue — mounting filesystems..."
    mount -t bpf bpf /sys/fs/bpf 2>/dev/null || true
    mount -t debugfs nodev /sys/kernel/debug 2>/dev/null || true
    ok "BPF filesystem mounted, restart tetragon..."
    docker restart tetragon
  fi
else
  ok "Tetragon logs look clean"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 5. SURICATA SPECIFIC FIX
# ═══════════════════════════════════════════════════════════════════════════════
hr
info "Checking Suricata..."
SLOG=$(docker logs --tail=50 suricata 2>&1 || echo "")
if echo "$SLOG" | grep -qi "error\|failed\|cannot"; then
  fail "Suricata ada error:"
  echo "$SLOG" | grep -iE "error|failed|cannot" | head -10 | sed 's/^/    /'

  # Auto-detect dan patch interface
  if echo "$SLOG" | grep -qi "interface\|eth0\|no such\|device not found"; then
    fail "Interface eth0 tidak ditemukan di container"
    info "Auto-detecting interface..."
    IFACE=$(ip -o link show up | awk -F': ' '{print $2}' | grep -v -E '^(lo|docker|veth|br-)' | head -1)
    if [ -n "$IFACE" ]; then
      ok "Interface ditemukan: $IFACE — patch suricata.yaml..."
      sed -i "s/interface: eth0/interface: $IFACE/g" ./suricata/suricata.yaml
      ok "suricata.yaml di-patch: interface → $IFACE"
      docker restart suricata
    fi
  fi

  if echo "$SLOG" | grep -qi "rules\|classification"; then
    warn "Rules issue — pastikan file ada:"
    ls -la ./suricata/
  fi
else
  ok "Suricata logs look clean"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 6. HEALTH CHECK SEMUA SERVICE
# ═══════════════════════════════════════════════════════════════════════════════
hr
info "Health check semua service:"

check_http() {
  local name="$1" url="$2"
  if curl -sf "$url" -o /dev/null --max-time 3; then
    ok "$name — UP ($url)"
  else
    fail "$name — DOWN ($url)"
  fi
}

check_http "VictoriaMetrics" "http://localhost:8428/-/healthy"
check_http "VictoriaLogs"    "http://localhost:9428/health"
check_http "Grafana"         "http://localhost:3000/api/health"
check_http "Benthos"         "http://localhost:4195/ready"

# ═══════════════════════════════════════════════════════════════════════════════
# 7. GRAFANA DATASOURCE UID VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
hr
info "Grafana Datasource UIDs:"
curl -s http://admin:minisoc2026@localhost:3000/api/datasources 2>/dev/null | \
  python3 -c "
import sys,json
try:
    ds=json.load(sys.stdin)
    for d in ds:
        print(f\"  {d['name']:30s} uid={d['uid']:30s} type={d['type']}\" )
except:
    print('  Grafana belum ready')
"

hr
echo ""
echo "✅ Diagnose selesai — $(date)"
echo ""
echo "📋 Ringkasan:"
echo "   - Tetragon crash  → lihat bagian 4 di atas"
echo "   - Suricata crash  → lihat bagian 5 di atas (kemungkinan interface bukan eth0)"
echo "   - Benthos crash   → tetragon.log belum ada, tunggu tetragon sehat dulu"
echo "   - Grafana issue   → lihat UID datasource di bagian 7"
echo ""
