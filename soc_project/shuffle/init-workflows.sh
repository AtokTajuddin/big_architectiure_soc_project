#!/bin/sh
# Shuffle SOAR — OWASP Top 10 Verification & Setup Guide
# Shuffle tidak mendukung create workflow via API otomatis.
# Workflow harus dibuat/import manual via UI.
#
# Usage: ./init-workflows.sh [shuffle_host]

SHUFFLE_HOST="${1:-http://shuffle-backend:5001}"

echo "========================================"
echo "  SOC Mini Stack — Shuffle SOAR Setup  "
echo "========================================"
echo ""

# --- Verifikasi konektivitas -----------------------------------------------
echo "[check] Testing Shuffle backend at $SHUFFLE_HOST ..."
STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "$SHUFFLE_HOST/api/v1/health" 2>/dev/null)
if [ "$STATUS" = "200" ] || [ "$STATUS" = "401" ] || [ "$STATUS" = "403" ]; then
  echo "[check] Shuffle backend is reachable (HTTP $STATUS)."
else
  echo "[check] Shuffle backend NOT reachable (HTTP $STATUS)."
  echo "        Tunggu 2-3 menit lalu jalankan ulang script ini."
  exit 1
fi

# --- Cek OpenSearch -------------------------------------------------------
ES=$(curl -s --max-time 3 http://shuffle-db:9200 2>/dev/null | grep -o '"tagline"')
if [ -n "$ES" ]; then
  echo "[check] OpenSearch (shuffle-db) is healthy."
else
  echo "[check] WARNING: OpenSearch belum ready."
fi

echo ""
echo "========================================"
echo "  LANGKAH SETUP MANUAL (WAJIB)       "
echo "========================================"
echo ""
echo "1. Buka Shuffle UI di browser:"
echo "   http://localhost:3001"
echo "   Login: admin / Admin1234!"
echo ""
echo "2. Klik menu Workflows → + Create Workflow (10 kali):"
echo ""
echo "   ┌─────────────────────────────────────────────────┐"
echo "   │ # │ Workflow Name                    │ Trigger │"
echo "   ├───┼──────────────────────────────────┼─────────┤"
echo "   │ 1 │ SOC-A01-Broken-Access-Control   │ Webhook │"
echo "   │ 2 │ SOC-A02-Crypto-Failures         │ Webhook │"
echo "   │ 3 │ SOC-A03-Injection               │ Webhook │"
echo "   │ 4 │ SOC-A04-Insecure-Design         │ Webhook │"
echo "   │ 5 │ SOC-A05-Security-Misconfig      │ Webhook │"
echo "   │ 6 │ SOC-A06-Vulnerable-Components   │ Webhook │"
echo "   │ 7 │ SOC-A07-Auth-Failures           │ Webhook │"
echo "   │ 8 │ SOC-A08-Integrity-Failures      │ Webhook │"
echo "   │ 9 │ SOC-A09-Logging-Failures        │ Webhook │"
echo "   │10 │ SOC-A10-SSRF                    │ Webhook │"
echo "   └─────────────────────────────────────────────────┘"
echo ""
echo "3. Setiap workflow WAJIB tambahkan node Webhook:"
echo "   - Drag 'Webhook' app ke canvas"
echo "   - Klik Edit → Method: POST → Save"
echo "   - Copy URL yang muncul (contoh:"
echo "     http://localhost:3001/api/v1/hooks/webhook_xxxx )"
echo ""
echo "4. Edit docker-compose.yml ml-engine environment:"
echo "   SHUFFLE_WEBHOOK_URL: 'http://localhost:3001/api/v1/hooks/webhook_xxxx'"
echo ""
echo "5. Restart ml-engine:"
echo "   sudo docker compose -f /home/atokdins/soc_project/docker-compose.yml up -d --force-recreate ml-engine"
echo ""
echo "6. Test trigger:"
echo "   curl -X POST http://localhost:8000/ingest -H 'Content-Type: application/json'"
echo "     -d '{\"raw\":\"{\\\"event_type\\\":\\\"alert\\\",\\\"alert\\\":{\\\"signature\\\":\\\"ET DOS\\\",\\\"category\\\":\\\"Attempted Denial of Service\\\",\\\"severity\\\":2}}\"}'"
echo ""
echo "========================================"
echo ""
echo "Referensi lengkap: shuffle/owasp-workflows-setup.md"
