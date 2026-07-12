#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║   MINI SOC — FULL RESET & CLEAN START                       ║
# ║   Jalankan ini dari folder soc_final/                       ║
# ╚══════════════════════════════════════════════════════════════╝

echo "🔴 Step 1: Stop dan hapus semua container + volume..."
docker compose down -v --remove-orphans

echo ""
echo "🔴 Step 2: Hapus semua volume Docker yang terkait (termasuk plugin cache)..."
docker volume rm grafana-data victorialogs-data victoriametrics-data 2>/dev/null || true
# Nama volume dengan prefix project folder:
docker volume rm soc_final_grafana-data soc_final_victorialogs-data soc_final_victoriametrics-data 2>/dev/null || true
docker volume rm soc_test_grafana-data soc_test_victorialogs-data soc_test_victoriametrics-data 2>/dev/null || true

echo ""
echo "🔴 Step 3: Hapus container lama yang masih ada..."
docker rm -f tetragon victorialogs victoriametrics benthos grafana 2>/dev/null || true

echo ""
echo "🟡 Step 4: Cek struktur folder provisioning..."
ls -la grafana/provisioning/datasources/
ls -la grafana/provisioning/dashboards/
ls -la grafana/dashboards/

echo ""
echo "🟢 Step 5: Start ulang dari awal..."
docker compose up -d

echo ""
echo "🟢 Step 6: Tunggu Grafana install plugin (±60 detik)..."
sleep 60

echo ""
echo "🟢 Step 7: Cek status semua container..."
docker compose ps

echo ""
echo "🟢 Step 8: Cek Grafana berhasil install plugin..."
docker compose logs grafana | grep -E "plugin|Plugin|datasource|Datasource|error|Error" | tail -20

echo ""
echo "✅ Done! Buka: http://localhost:3000"
echo "   user: admin | pass: minisoc2026"
