#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Fix Tetragon + Suricata restart loop
# Confirmed: interface = eth0 (correct)
# Root causes:
#   Tetragon  → BPF/debugfs mount issue atau kernel version
#   Suricata  → missing rules file, config issue, atau privilege
# Working dir: /home/atok/home/soc_dev
# ─────────────────────────────────────────────────────────────────────────────
WORKDIR="/home/atok/home/soc_dev"
cd "$WORKDIR"

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLU}[INFO]${NC} $*"; }
ok()   { echo -e "${GRN}[OK]${NC}   $*"; }
warn() { echo -e "${YLW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }

echo "=================================================="
echo " Mini SOC — Tetragon + Suricata Fix"
echo " $(date)"
echo "=================================================="

# ─── STEP 1: Tampilkan log error sebelum kita stop ─────────────────────────
echo ""
info "=== TETRAGON LOGS (last 40) ==="
docker logs --tail=40 tetragon 2>&1 || echo "(container tidak ada)"

echo ""
info "=== SURICATA LOGS (last 40) ==="
docker logs --tail=40 suricata 2>&1 || echo "(container tidak ada)"

# ─── STEP 2: Stop containers ───────────────────────────────────────────────
echo ""
info "=== Stop tetragon + suricata ==="
docker stop tetragon suricata 2>/dev/null || true
docker rm   tetragon suricata 2>/dev/null || true

# ─── STEP 3: Kernel + BPF check ────────────────────────────────────────────
echo ""
info "=== Kernel + BPF Check ==="
KVER=$(uname -r)
ARCH=$(uname -m)
info "Kernel: $KVER  | Arch: $ARCH"

# Check BPF support
if [ -f /proc/config.gz ]; then
    BPF_SUPPORTED=$(zcat /proc/config.gz 2>/dev/null | grep CONFIG_BPF=y | wc -l)
elif [ -f /boot/config-$KVER ]; then
    BPF_SUPPORTED=$(grep CONFIG_BPF=y /boot/config-$KVER 2>/dev/null | wc -l)
else
    BPF_SUPPORTED=1  # assume yes
fi

if [ "$BPF_SUPPORTED" -gt 0 ]; then
    ok "Kernel BPF support: YES"
else
    fail "Kernel TIDAK support BPF! Tetragon tidak bisa jalan."
    fail "Gunakan kernel >= 5.4 dengan CONFIG_BPF=y"
fi

# Mount BPF filesystems
info "Mounting BPF filesystems..."
mount | grep -q "bpf on /sys/fs/bpf"      || { mount -t bpf bpf /sys/fs/bpf 2>/dev/null && ok "/sys/fs/bpf mounted" || warn "/sys/fs/bpf mount failed (mungkin sudah ada)"; }
mount | grep -q "debugfs on /sys/kernel/debug" || { mount -t debugfs nodev /sys/kernel/debug 2>/dev/null && ok "/sys/kernel/debug mounted" || warn "debugfs mount failed (mungkin sudah ada)"; }

# Verify
ls /sys/fs/bpf >/dev/null 2>&1      && ok "/sys/fs/bpf accessible" || fail "/sys/fs/bpf NOT accessible"
ls /sys/kernel/debug >/dev/null 2>&1 && ok "/sys/kernel/debug accessible" || fail "/sys/kernel/debug NOT accessible"

# ─── STEP 4: Suricata prerequisites ────────────────────────────────────────
echo ""
info "=== Suricata Prerequisites ==="

# Pastikan folder logs ada
mkdir -p ./logs/suricata
ok "logs/suricata dir: ready"

# Pastikan rules file ada dan tidak kosong
if [ -s ./suricata/suricata.rules ]; then
    RULE_COUNT=$(grep -c "^alert\|^drop\|^reject\|^pass" ./suricata/suricata.rules 2>/dev/null || echo 0)
    ok "suricata.rules ada: $RULE_COUNT rules"
else
    warn "suricata.rules kosong atau tidak ada — membuat dummy rule..."
    cat > ./suricata/suricata.rules << 'RULES'
# Mini SOC Suricata Rules
alert icmp any any -> any any (msg:"ICMP Ping"; sid:1000001; rev:1;)
alert tcp any any -> any 22 (msg:"SSH Connection Attempt"; sid:1000002; rev:1;)
alert tcp any any -> any 80 (msg:"HTTP Traffic"; sid:1000003; rev:1;)
alert tcp any any -> any 443 (msg:"HTTPS Traffic"; sid:1000004; rev:1;)
alert dns any any -> any any (msg:"DNS Query"; sid:1000005; rev:1;)
RULES
    ok "dummy suricata.rules dibuat"
fi

# ─── STEP 5: Tulis ulang suricata.yaml yang terbukti bekerja ───────────────
echo ""
info "=== Rebuild suricata.yaml (minimal, proven) ==="
cat > ./suricata/suricata.yaml << 'SURIYAML'
%YAML 1.1
---
vars:
  address-groups:
    HOME_NET: "[192.168.0.0/16,10.0.0.0/8,172.16.0.0/12]"
    EXTERNAL_NET: "!$HOME_NET"
  port-groups:
    HTTP_PORTS: "80"
    HTTPS_PORTS: "443"
    SSH_PORTS: "22"

default-log-dir: /var/log/suricata/

outputs:
  - eve-log:
      enabled: yes
      filetype: regular
      filename: eve.json
      community-id: true
      types:
        - alert:
            enabled: yes
        - flow:
            enabled: yes
        - http:
            enabled: yes
        - dns:
            enabled: yes
        - tls:
            enabled: yes
        - ssh:
            enabled: yes
        - stats:
            enabled: yes
            interval: 30

af-packet:
  - interface: eth0
    cluster-id: 99
    cluster-type: cluster_flow
    defrag: yes

pcap:
  - interface: eth0

default-rule-path: /var/lib/suricata/rules
rule-files:
  - suricata.rules

host-os-policy:
  windows: [0.0.0.0/0]

defrag:
  memcap: 32mb
  hash-size: 65536
  trackers: 65535
  max-frags: 65535
  prealloc: yes
  timeout: 60

flow:
  memcap: 32mb
  hash-size: 65536
  prealloc: 10000
  emergency-recovery: 30

stream:
  memcap: 32mb
  checksum-validation: no
  inline: auto
  reassembly:
    memcap: 64mb
    depth: 1mb
    toserver-chunk-size: 2560
    toclient-chunk-size: 2560
    randomize-chunk-size: yes

host:
  hash-size: 4096
  prealloc: 1000
  memcap: 32mb

detect:
  profile: medium
  sgh-mpm-context: auto
  inspection-recursion-limit: 3000
  prefilter:
    default: mpm

logging:
  default-log-level: notice
  outputs:
    - console:
        enabled: yes

app-layer:
  protocols:
    http:
      enabled: yes
    dns:
      enabled: yes
    tls:
      enabled: yes
    ssh:
      enabled: yes
    smtp:
      enabled: yes
    ftp:
      enabled: yes
    smb:
      enabled: yes
SURIYAML
ok "suricata.yaml rebuilt (minimal proven config)"

# ─── STEP 6: Check tetragon image support ──────────────────────────────────
echo ""
info "=== Tetragon Image Check ==="
TIMAGE="quay.io/cilium/tetragon:v1.1.0"

# Check jika arsitektur ARM — tetragon v1.1.0 ada issue di beberapa ARM builds
if echo "$ARCH" | grep -qi "arm\|aarch"; then
    warn "ARM architecture — Tetragon v1.1.0 mungkin tidak stabil"
    warn "Rekomendasi: gunakan image quay.io/cilium/tetragon:latest"
    info "Mengubah docker-compose.yml ke tetragon:latest..."
    sed -i 's|quay.io/cilium/tetragon:v1.1.0|quay.io/cilium/tetragon:latest|g' docker-compose.yml
    ok "Image updated to :latest"
fi

# ─── STEP 7: Start ulang ───────────────────────────────────────────────────
echo ""
info "=== Start containers ==="
docker compose up -d tetragon suricata
info "Menunggu 15 detik..."
sleep 15

# ─── STEP 8: Final status ──────────────────────────────────────────────────
echo ""
echo "=================================================="
echo " FINAL STATUS"
echo "=================================================="
docker compose ps

echo ""
RESTARTING=$(docker ps --filter "status=restarting" --format "{{.Names}}" 2>/dev/null)
if [ -z "$RESTARTING" ]; then
    ok "✅ TIDAK ADA container restart-loop!"
else
    fail "⚠️  Masih ada restart-loop:"
    for C in $RESTARTING; do
        echo ""
        fail "  Container: $C"
        docker logs --tail=20 "$C" 2>&1 | grep -E "error|Error|fatal|Failed|FAIL|panic" | head -10 | sed 's/^/    /'
    done
    echo ""
    warn "Jalankan perintah ini untuk lihat full log:"
    echo "  docker logs tetragon 2>&1 | tail -50"
    echo "  docker logs suricata 2>&1 | tail -50"
fi

echo ""
ok "Script selesai — $(date)"
