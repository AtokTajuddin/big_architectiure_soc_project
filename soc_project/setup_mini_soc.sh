#!/usr/bin/env bash
# Setup pertama kali Mini SOC di /home/atok/home/soc_dev
set -e

WORKDIR="/home/atok/home/soc_dev"
cd "$WORKDIR" || { echo "ERROR: $WORKDIR tidak ada — extract ZIP dulu!"; exit 1; }

echo "=== Mini SOC Setup ==="
echo "Working dir: $(pwd)"

mkdir -p ./logs ./logs/suricata ./grafana/plugins
chmod +x ./*.sh 2>/dev/null || true

echo "Menjalankan stack..."
docker compose up -d

sleep 12
docker compose ps

echo
echo "Akses:"
echo "  Grafana  -> http://localhost:3000  (admin / minisoc2026)"
echo "  VictoriaMetrics -> http://localhost:8428"
echo "  VictoriaLogs    -> http://localhost:9428"
echo "  Benthos  -> http://localhost:4195"
