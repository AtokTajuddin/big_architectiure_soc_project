#!/usr/bin/env bash
# ============================================================
# SOC Test Injection Script — Trigger ALL dashboard panels
# Sends realistic attack payloads covering OWASP Top 10
# ============================================================

set -euo pipefail

ML="http://localhost:8000"
LOKI="http://localhost:9428"
VM="http://localhost:8428"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[~]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${BLUE}[>]${NC} $*"; }

TS=$(date -u +"%Y-%m-%dT%H:%M:%S.000000%z")

# ── Helper: send to ML /ingest ─────────────────────────────
ingest() {
  local label="$1"
  local payload="$2"
  local resp
  resp=$(curl -s -X POST "$ML/ingest" \
    -H "Content-Type: application/json" \
    -d "{\"raw\": $payload, \"source_hint\": \"suricata\"}")
  if echo "$resp" | grep -q '"status":"ok"'; then
    log "$label → ML engine OK"
  else
    warn "$label → $resp"
  fi
}

# ── Helper: push log line to Loki/VictoriaLogs ────────────
push_loki() {
  local job="$1"
  local level="$2"
  local msg="$3"
  local nano_ts
  nano_ts=$(date +%s%N)
  curl -s -X POST "$LOKI/loki/api/v1/push" \
    -H "Content-Type: application/json" \
    -d "{\"streams\":[{\"stream\":{\"job\":\"$job\",\"level\":\"$level\",\"host\":\"soc-host\"},\"values\":[[\"$nano_ts\",\"$msg\"]]}]}" \
    >/dev/null && log "Loki push [$job/$level]"
}

# ── Helper: push metric to VictoriaMetrics ─────────────────
push_vm() {
  local metric="$1"
  local value="${2:-1}"
  curl -s -X POST "$VM/api/v1/import/prometheus" \
    -d "$metric $value" >/dev/null && log "VM metric: $metric=$value"
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  SOC Alert Injection — All Dashboard Coverage Test       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# SECTION 1: Suricata alerts → ML Engine (via /ingest)
# Covers: Dashboard 01, 04, 07
# ============================================================
info "=== SECTION 1: Suricata IDS Alerts → ML Engine ==="

# A03: SQL Injection (severity 1 = critical)
ingest "SQL Injection (UNION SELECT)" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"192.168.1.100\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER SQL Injection UNION SELECT\",\"category\":\"Web Application Attack\",\"severity\":1}}"'

sleep 0.5

# A01: Brute Force / Broken Access Control (severity 2 = high)
ingest "Login Brute Force A01" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.0.50\",\"dest_ip\":\"192.168.1.1\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET POLICY Brute Force Login Attempt\",\"category\":\"Attempted Administrator Privilege Gain\",\"severity\":2}}"'

sleep 0.5

# A03: XSS
ingest "XSS Attack A03" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"172.16.0.20\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER XSS Script Tag Detected\",\"category\":\"Web Application Attack\",\"severity\":2}}"'

sleep 0.5

# A05: Path Traversal / LFI (severity 2)
ingest "LFI Path Traversal A05" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"192.168.2.10\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER Path Traversal etc/passwd\",\"category\":\"Attempted Information Leak\",\"severity\":2}}"'

sleep 0.5

# A07: SSH Brute Force (severity 2)
ingest "SSH Brute Force A07" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"203.0.113.5\",\"dest_ip\":\"10.10.0.1\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET DOS Potential SSH Scan\",\"category\":\"Attempted Denial of Service\",\"severity\":2}}"'

sleep 0.5

# A03: Command Injection / RCE (severity 1)
ingest "Command Injection RCE A03" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.0.99\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER Remote Code Execution Attempt\",\"category\":\"Web Application Attack\",\"severity\":1}}"'

sleep 0.5

# A04: Webshell upload
ingest "Webshell Upload A04" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"192.168.1.200\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER PHP Webshell Upload Detected\",\"category\":\"Malware\",\"severity\":1}}"'

sleep 0.5

# A10: SSRF
ingest "SSRF Attack A10" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.0.33\",\"dest_ip\":\"169.254.169.254\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER SSRF Metadata Endpoint Access\",\"category\":\"Server-Side Request Forgery\",\"severity\":1}}"'

sleep 0.5

# A03: Base64 Evasion (double encoded)
ingest "Base64 Evasion Encoded" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.0.77\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER Obfuscated Payload\",\"category\":\"Web Application Attack\",\"severity\":1},\"http\":{\"url\":\"/dvwa/vulnerabilities/exec/?ip=dW5hbWUgLWE=|base64+-d|bash\",\"request_body\":\"echo dW5hbWUgLWE= | base64 -d | bash\"}}"'

sleep 0.5

# UNION SELECT evasion (double URL encode)
ingest "Double URL Encoding Evasion" \
  '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.0.88\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER SQL UNION SELECT Evasion\",\"category\":\"Web Application Attack\",\"severity\":1},\"http\":{\"url\":\"/dvwa/?id=1%2520UNION%2520SELECT%25201%252C2%252C3\"}}"'

sleep 0.5

echo ""
info "=== SECTION 2: ML Analyze (NETWORK/IOT/LOGS specialists) ==="

# Network anomaly — DoS
resp=$(curl -s -X POST "$ML/analyze" \
  -H "Content-Type: application/json" \
  -d '{"source":"NETWORK","data":[500,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],"hint":"DoS Attack"}')
log "NETWORK specialist: $(echo $resp | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get(\"status\",r))' 2>/dev/null || echo "$resp")"

sleep 0.5

# IoT anomaly
resp=$(curl -s -X POST "$ML/analyze" \
  -H "Content-Type: application/json" \
  -d '{"source":"IOT","data":[9.5,8.2,0.1,100,0,0,0,0,0,0,0,0,0,0,1],"hint":"Authentication Failure"}')
log "IOT specialist: $(echo $resp | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get(\"status\",r))' 2>/dev/null || echo "$resp")"

sleep 0.5

# Logs anomaly
resp=$(curl -s -X POST "$ML/analyze" \
  -H "Content-Type: application/json" \
  -d '{"source":"LOGS","data":[1,1,0,500,1,0,0,0,0,1],"hint":"SSH Brute Force"}')
log "LOGS specialist: $(echo $resp | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get(\"status\",r))' 2>/dev/null || echo "$resp")"

sleep 0.5

# Network R2L
resp=$(curl -s -X POST "$ML/analyze" \
  -H "Content-Type: application/json" \
  -d '{"source":"NETWORK","data":[0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],"hint":"R2L Access Brute Force"}')
log "NETWORK R2L: $(echo $resp | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get(\"status\",r))' 2>/dev/null || echo "$resp")"

echo ""
info "=== SECTION 3: Tetragon eBPF events → Loki (Dashboard 01, 02) ==="

# Privilege escalation event
TETRA_PRIV='{\"process_kprobe\":{\"function_name\":\"commit_creds\",\"action\":\"Post\",\"process\":{\"binary\":\"/usr/bin/sudo\",\"uid\":1000,\"pid\":12345},\"args\":[]}}'
push_loki "tetragon" "warn" "$TETRA_PRIV"

sleep 0.3

# SSH scan
TETRA_SSH='{\"process_kprobe\":{\"function_name\":\"tcp_v4_connect\",\"action\":\"Post\",\"process\":{\"binary\":\"/usr/bin/nmap\",\"uid\":0,\"pid\":23456},\"args\":[{\"sock_arg\":{\"dport\":22}}]}}'
push_loki "tetragon" "warn" "$TETRA_SSH"

sleep 0.3

# Process exec suspicious
TETRA_EXEC='{\"process_exec\":{\"process\":{\"binary\":\"/bin/bash\",\"uid\":0,\"pid\":34567,\"arguments\":\"-c /tmp/exploit.sh\"}}}'
push_loki "tetragon" "warn" "$TETRA_EXEC"

sleep 0.3

# Kprobe security_bprm_check
TETRA_KPROBE='{\"process_kprobe\":{\"function_name\":\"security_bprm_check\",\"action\":\"SIGKILL\",\"process\":{\"binary\":\"/tmp/malware\",\"uid\":0,\"pid\":99999}}}'
push_loki "tetragon" "critical" "$TETRA_KPROBE"

sleep 0.3

# Normal exec (to show contrast)
TETRA_NORM='{\"process_exec\":{\"process\":{\"binary\":\"/usr/sbin/cron\",\"uid\":0,\"pid\":100,\"arguments\":\"\"}}}'
push_loki "tetragon" "info" "$TETRA_NORM"

echo ""
info "=== SECTION 4: Suricata alerts → Loki (raw eve.json format) ==="

# SQLi alert in Loki
SURICATA_SQLi="{\"timestamp\":\"$TS\",\"event_type\":\"alert\",\"src_ip\":\"192.168.1.50\",\"dest_ip\":\"10.0.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER SQLi UNION SELECT Attack DVWA\",\"category\":\"Web Application Attack\",\"severity\":1}}"
push_loki "suricata" "critical" "$SURICATA_SQLi"

sleep 0.3

SURICATA_XSS="{\"timestamp\":\"$TS\",\"event_type\":\"alert\",\"src_ip\":\"192.168.1.51\",\"dest_ip\":\"10.0.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER XSS Script Tag\",\"category\":\"Web Application Attack\",\"severity\":2}}"
push_loki "suricata" "warn" "$SURICATA_XSS"

sleep 0.3

SURICATA_LFI="{\"timestamp\":\"$TS\",\"event_type\":\"alert\",\"src_ip\":\"192.168.1.52\",\"dest_ip\":\"10.0.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB_SERVER LFI etc/passwd Attempt\",\"category\":\"Attempted Information Leak\",\"severity\":2}}"
push_loki "suricata" "warn" "$SURICATA_LFI"

sleep 0.3

SURICATA_BRUTE="{\"timestamp\":\"$TS\",\"event_type\":\"alert\",\"src_ip\":\"203.0.113.10\",\"dest_ip\":\"10.0.0.1\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET SCAN SSH Brute Force Attempt\",\"category\":\"Attempted Denial of Service\",\"severity\":2}}"
push_loki "suricata" "warn" "$SURICATA_BRUTE"

sleep 0.3

SURICATA_EVASION="{\"timestamp\":\"$TS\",\"event_type\":\"alert\",\"src_ip\":\"10.0.0.77\",\"dest_ip\":\"10.0.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"EVASION(base64_encoding) + RCE\",\"category\":\"Web Application Attack\",\"severity\":1}}"
push_loki "suricata" "critical" "$SURICATA_EVASION"

echo ""
info "=== SECTION 5: ML CVE log events → Loki (Dashboard 04, 06) ==="

# Push enriched ML events as job=ml-cve (for dashboard 04 logs + 06 Shuffle logs)
ML_CVE1="{\"source\":\"suricata\",\"signature\":\"ET WEB SQLi UNION\",\"severity\":\"critical\",\"owasp_id\":\"A03:2021\",\"owasp_name\":\"Injection\",\"cwe\":[\"CWE-89\"],\"cve\":\"CVE-2023-40044\",\"nist_iso_controls\":\"AC-3 (Access Enforcement)\",\"mitre_mitigation\":\"Privileged Account Management\",\"owasp\":\"A03:2021\"}"
push_loki "ml-cve" "critical" "$ML_CVE1"

sleep 0.3

ML_CVE2="{\"source\":\"tetragon\",\"action\":\"Post\",\"function\":\"commit_creds\",\"severity\":\"critical\",\"owasp_id\":\"A01:2021\",\"owasp_name\":\"Broken Access Control\",\"cwe\":[\"CWE-284\"],\"cve\":\"CVE-2021-4034\",\"nist_iso_controls\":\"AC-6 (Least Privilege)\",\"mitre_mitigation\":\"Privileged Account Management\",\"owasp\":\"A01:2021\"}"
push_loki "ml-cve" "critical" "$ML_CVE2"

sleep 0.3

ML_CVE3="{\"source\":\"suricata\",\"signature\":\"EVASION+RCE decoded\",\"severity\":\"high\",\"owasp_id\":\"A03:2021\",\"owasp_name\":\"Injection\",\"cwe\":[\"CWE-78\"],\"cve\":\"CVE-2022-0847\",\"nist_iso_controls\":\"SI-3 (Malicious Code Protection)\",\"mitre_mitigation\":\"Code Signing\",\"owasp\":\"A03:2021\"}"
push_loki "ml-cve" "warn" "$ML_CVE3"

echo ""
info "=== SECTION 6: Push synthetic Prometheus metrics to VictoriaMetrics ==="
info "    (for MISP + Shuffle panels that have no backend data)"

EPOCH=$(date +%s)

# MISP synthetic metrics
push_vm 'misp_events_active{job="misp",instance="misp-exporter:9419"}' 3
push_vm 'misp_indicators_total{job="misp",instance="misp-exporter:9419"}' 47
push_vm 'misp_ioc_match_total{ioc_type="ip",job="misp",instance="misp-exporter:9419"}' 12
push_vm 'misp_ioc_match_total{ioc_type="domain",job="misp",instance="misp-exporter:9419"}' 8
push_vm 'misp_ioc_match_total{ioc_type="malware",job="misp",instance="misp-exporter:9419"}' 5
push_vm 'misp_events_total{category="Network activity",job="misp",instance="misp-exporter:9419"}' 15
push_vm 'misp_events_total{category="Malware",job="misp",instance="misp-exporter:9419"}' 9
push_vm 'misp_events_total{category="Vulnerability",job="misp",instance="misp-exporter:9419"}' 6
push_vm 'misp_last_sync_lag_seconds{job="misp",instance="misp-exporter:9419"}' 45

# Shuffle synthetic metrics
push_vm 'shuffle_workflow_executions_total{workflow="SOC-A03-Injection",job="shuffle",instance="shuffle-exporter:9420"}' 7
push_vm 'shuffle_workflow_executions_total{workflow="SOC-A01-Broken-Access-Control",job="shuffle",instance="shuffle-exporter:9420"}' 4
push_vm 'shuffle_workflow_executions_total{workflow="SOC-A07-Auth-Failures",job="shuffle",instance="shuffle-exporter:9420"}' 3
push_vm 'shuffle_workflow_failures_total{job="shuffle",instance="shuffle-exporter:9420"}' 1
push_vm 'shuffle_action_executions_total{job="shuffle",instance="shuffle-exporter:9420"}' 28
push_vm 'shuffle_workflows_active{job="shuffle",instance="shuffle-exporter:9420"}' 10
push_vm 'shuffle_alerts_processed_total{job="shuffle",instance="shuffle-exporter:9420"}' 14
push_vm 'shuffle_workflow_duration_seconds_sum{workflow="SOC-A03-Injection",job="shuffle",instance="shuffle-exporter:9420"}' 12.5
push_vm 'shuffle_workflow_duration_seconds_count{workflow="SOC-A03-Injection",job="shuffle",instance="shuffle-exporter:9420"}' 7
push_vm 'shuffle_workflow_duration_seconds_sum{workflow="SOC-A01-Broken-Access-Control",job="shuffle",instance="shuffle-exporter:9420"}' 8.2
push_vm 'shuffle_workflow_duration_seconds_count{workflow="SOC-A01-Broken-Access-Control",job="shuffle",instance="shuffle-exporter:9420"}' 4
push_vm 'shuffle_action_failures_total{job="shuffle",instance="shuffle-exporter:9420"}' 2

# Benthos metrics (expose via VictoriaMetrics for dashboard 03 "connection up" fallback)
push_vm 'up{job="benthos",instance="benthos:4195"}' 1

echo ""
info "=== SECTION 7: Multi-round burst (populate timeseries charts) ==="

for i in $(seq 1 5); do
  ingest "Burst[$i] SQLi" \
    '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.'"$i"'.100\",\"dest_ip\":\"10.10.0.5\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET WEB SQLi OR 1=1 DVWA\",\"category\":\"Web Application Attack\",\"severity\":1}}"'
  
  ingest "Burst[$i] Brute" \
    '"{\"timestamp\":\"'"$TS"'\",\"event_type\":\"alert\",\"src_ip\":\"10.0.'"$i"'.50\",\"dest_ip\":\"10.0.0.1\",\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET SCAN SSH Brute Force\",\"category\":\"Attempted Denial of Service\",\"severity\":2}}"'

  # Also push Tetragon kprobe
  push_loki "tetragon" "warn" \
    "{\"process_kprobe\":{\"function_name\":\"tcp_v4_connect\",\"action\":\"Post\",\"process\":{\"binary\":\"/usr/bin/nmap\",\"uid\":0,\"pid\":$((RANDOM+10000))}}}"

  sleep 0.3
done

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Injection Complete! Summary:                            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Final check
REPORT=$(curl -s "$ML/report/json" | python3 -c "
import sys,json
r=json.load(sys.stdin)
print(f'  ML Engine threat store: {r[\"total\"]} alerts')
if r['alerts']:
    for a in r['alerts'][:5]:
        sev = a.get('severity','?')
        owasp = a.get('owasp_id','?')
        cve = a.get('cve','?')
        src = a.get('source','?')
        print(f'  [{sev.upper():8s}] {owasp} {cve} ({src})')
" 2>/dev/null || echo "  (could not parse report)")

echo "$REPORT"
echo ""
echo "  Metrics exposed: http://localhost:8000/metrics"
echo "  Full report:     http://localhost:8000/report"
echo "  VictoriaMetrics: http://localhost:8428/vmui"
echo "  Grafana:         http://localhost:3000"
echo ""
echo -e "${YELLOW}► Buka Grafana dan refresh dashboard untuk melihat data!${NC}"
echo -e "${YELLOW}► Klik time picker → 'Last 15 minutes' jika data tidak muncul${NC}"
