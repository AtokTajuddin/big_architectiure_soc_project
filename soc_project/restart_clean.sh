#!/bin/bash
# ================================================================
# SOC Stack Clean Restart
# Jalankan: bash restart_clean.sh
# ================================================================
set -e

COMPOSE="docker compose -f /home/atokdins/soc_project/docker-compose.yml"
cd /home/atokdins/soc_project

echo "======================================================"
echo " SOC Stack Clean Restart"
echo "======================================================"

# 1. Stop semua container
echo ""
echo "[1/6] Stopping all containers..."
$COMPOSE down --remove-orphans

# 2. Hapus grafana-data volume agar datasource UIDs ter-reset bersih
#    (aman karena semua dashboard & datasource di-provision dari file)
echo ""
echo "[2/6] Removing grafana-data volume (clean datasource UID state)..."
docker volume rm soc_project_grafana-data 2>/dev/null || \
docker volume rm grafana-data 2>/dev/null || \
echo "  -> Volume sudah bersih atau nama berbeda, skip."

# 3. Pastikan direktori logs ada
echo ""
echo "[3/6] Ensuring log directories exist..."
mkdir -p ./logs/suricata
mkdir -p ./grafana/plugins

# 4. Pastikan suricata eve.json ada (agar Benthos tidak error saat awal)
if [ ! -f ./logs/suricata/eve.json ]; then
    echo "  -> Creating empty eve.json placeholder..."
    touch ./logs/suricata/eve.json
fi

# 5. Start semua service
echo ""
echo "[4/6] Starting all services..."
$COMPOSE up -d

# 6. Tunggu Grafana download plugin (butuh ~30-60 detik)
echo ""
echo "[5/6] Waiting 60s for Grafana plugin installation..."
sleep 60

# 7. Status check
echo ""
echo "[6/6] Checking container status..."
$COMPOSE ps

echo ""
echo "======================================================"
echo " Checking critical services..."
echo "======================================================"

echo ""
echo "--- Tetragon (last 10 lines) ---"
docker logs tetragon --tail 10 2>&1

echo ""
echo "--- Suricata interface detection ---"
docker logs suricata --tail 5 2>&1 | grep -E "Using interface|Suricata|ERROR|error" || true

echo ""
echo "--- Grafana plugin install ---"
docker logs grafana --tail 15 2>&1 | grep -E "plugin|Plugin|datasource|provisioning|error|Error" || true

echo ""
echo "======================================================"
echo " Done! Buka Grafana di: http://localhost:3000"
echo " Login: admin / minisoc2026"
echo "======================================================"
