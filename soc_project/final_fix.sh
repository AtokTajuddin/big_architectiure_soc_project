#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# FINAL FIX — Tetragon + Suricata
# Penyebab yang sudah diidentifikasi dari log:
#
# TETRAGON:
#   level=fatal "Failed to start tetragon" error="failed loading tracing policy
#   file /etc/tetragon/tetragon.tp.d/04-reverse-shell.yaml: failed to unmarshal
#   object ...matchBinaries of type []v1alpha1.BinarySelector"
#   → File 04-reverse-shell.yaml punya schema matchBinaries yang SALAH
#   → FIX: hapus file itu, restart tetragon
#
# SURICATA:
#   "The configuration file must begin with the following two lines: %YAML 1.1 and ---"
#   → suricata.yaml tidak punya header %YAML 1.1\n---
#   → FIX: sudah dipatch di paket ini, restart suricata
#
# Working dir: /home/atok/home/soc_dev
# ─────────────────────────────────────────────────────────────────────────────
WORKDIR="/home/atok/home/soc_dev"
cd "$WORKDIR" || { echo "ERROR: $WORKDIR tidak ada"; exit 1; }

GRN='\033[0;32m'; RED='\033[0;31m'; YLW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GRN}✅${NC} $*"; }
fail() { echo -e "${RED}❌${NC} $*"; }
info() { echo -e "${YLW}▶${NC}  $*"; }

echo ""
echo "═══════════════════════════════════════════════════"
echo " MINI SOC — TETRAGON + SURICATA FINAL FIX"
echo " $(date)"
echo "═══════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# FIX 1: TETRAGON — Hapus 04-reverse-shell.yaml yang schema-nya salah
# ───────────────────────────────────────────────────────────────────────────
info "FIX 1: Hapus policy Tetragon yang bermasalah..."

if [ -f ./tetragon-policies/04-reverse-shell.yaml ]; then
    rm -f ./tetragon-policies/04-reverse-shell.yaml
    ok "Deleted: 04-reverse-shell.yaml"
else
    ok "04-reverse-shell.yaml sudah tidak ada"
fi

info "Policy yang tersisa:"
ls -la ./tetragon-policies/ 2>/dev/null | grep ".yaml" | awk '{print "   " $NF}'

# ───────────────────────────────────────────────────────────────────────────
# FIX 2: SURICATA — Pastikan suricata.yaml punya header %YAML 1.1\n---
# ───────────────────────────────────────────────────────────────────────────
info "FIX 2: Cek header suricata.yaml..."

FIRST_LINE=$(head -1 ./suricata/suricata.yaml)
SECOND_LINE=$(sed -n '2p' ./suricata/suricata.yaml)

if [ "$FIRST_LINE" = "%YAML 1.1" ] && [ "$SECOND_LINE" = "---" ]; then
    ok "suricata.yaml header sudah benar (%YAML 1.1 + ---)"
else
    info "Header salah — menambahkan header yang benar..."
    # Tambahkan header di awal file
    printf '%%YAML 1.1\n---\n' | cat - ./suricata/suricata.yaml > /tmp/suri_fixed.yaml
    mv /tmp/suri_fixed.yaml ./suricata/suricata.yaml
    ok "Header %YAML 1.1 + --- ditambahkan ke suricata.yaml"
fi

# Verifikasi
FIRST_LINE=$(head -1 ./suricata/suricata.yaml)
SECOND_LINE=$(sed -n '2p' ./suricata/suricata.yaml)
[ "$FIRST_LINE" = "%YAML 1.1" ] && ok "Baris 1: %YAML 1.1 ✓" || fail "Baris 1 masih salah: $FIRST_LINE"
[ "$SECOND_LINE" = "---" ]      && ok "Baris 2: --- ✓"         || fail "Baris 2 masih salah: $SECOND_LINE"

# ───────────────────────────────────────────────────────────────────────────
# FIX 3: Restart containers
# ───────────────────────────────────────────────────────────────────────────
echo ""
info "FIX 3: Restart tetragon + suricata..."

docker stop tetragon suricata 2>/dev/null || true
docker rm   tetragon suricata 2>/dev/null || true
sleep 2

docker compose up -d tetragon suricata
echo "   Menunggu 15 detik..."
sleep 15

# ───────────────────────────────────────────────────────────────────────────
# VERIFY
# ───────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " HASIL"
echo "═══════════════════════════════════════════════════"

docker compose ps tetragon suricata 2>/dev/null || docker ps | grep -E "tetragon|suricata"

echo ""
RESTARTING=$(docker ps --filter "status=restarting" --format "{{.Names}}" 2>/dev/null | grep -E "tetragon|suricata")
if [ -z "$RESTARTING" ]; then
    ok "BERES! Tidak ada restart-loop pada tetragon dan suricata"
    echo ""
    echo "   Cek log normal:"
    echo "   docker logs tetragon 2>&1 | tail -20"
    echo "   docker logs suricata 2>&1 | tail -20"
else
    fail "Masih ada restart-loop: $RESTARTING"
    for C in $RESTARTING; do
        echo ""
        info "Log $C (last 30):"
        docker logs --tail=30 "$C" 2>&1 | sed 's/^/   /'
    done
fi
