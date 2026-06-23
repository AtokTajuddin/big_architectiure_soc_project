#!/usr/bin/env bash
# Fix & restart Mini SOC
# Working dir: /home/atok/home/soc_dev
set -e

WORKDIR="/home/atok/home/soc_dev"
cd "$WORKDIR" || { echo "ERROR: tidak bisa masuk ke $WORKDIR"; exit 1; }
echo "Working dir: $(pwd)"

echo "[1/5] Stop containers..."
docker compose down

echo "[2/5] Hapus container crash state..."
docker rm -f tetragon suricata benthos 2>/dev/null || true

echo "[3/5] Buat folder logs..."
mkdir -p ./logs ./logs/suricata

echo "[4/5] Start core (VictoriaLogs, VictoriaMetrics, Grafana)..."
docker compose up -d victorialogs victoriametrics grafana
sleep 5

echo "[5/5] Start sensors (Tetragon, Suricata, Benthos)..."
docker compose up -d tetragon suricata benthos
sleep 8

echo
echo "=== STATUS ==="
docker compose ps

echo
echo "=== TETRAGON LOG ==="
docker logs --tail=30 tetragon 2>&1 || true

echo
echo "=== SURICATA LOG ==="
docker logs --tail=30 suricata 2>&1 || true

echo
echo "=== BENTHOS LOG ==="
docker logs --tail=20 benthos 2>&1 || true

echo
echo "Grafana -> http://localhost:3000 (admin / minisoc2026)"
