#!/usr/bin/env bash
# Diagnose & inject test data ke Mini SOC
# Working dir: /home/atok/home/soc_dev
cd "/home/atok/home/soc_dev" || exit 1

echo "=== HEALTH CHECK ==="
echo -n "VictoriaMetrics : "
curl -s http://localhost:8428/-/healthy || echo "DOWN"
echo -n "VictoriaLogs    : "
curl -s http://localhost:9428/health || echo "DOWN"
echo -n "Grafana         : "
curl -s http://localhost:3000/api/health | python3 -m json.tool 2>/dev/null || echo "DOWN"

echo
echo "=== INJECT METRICS (timestamp = NOW) ==="
NOW_MS=$(date +%s%3N)

inject_metric() {
  local name=$1
  local labels=$2
  local v1=$3
  local v2=$4
  local v3=$5
  curl -s -X POST "http://localhost:8428/api/v1/import"     -H 'Content-Type: application/json'     -d "{"metric":{"__name__":"$name",$labels},"values":[$v1,$v2,$v3],"timestamps":[$((NOW_MS-120000)),$((NOW_MS-60000)),$NOW_MS]}"
}

inject_metric "tetragon_events_total"              '"type":"process_exec","namespace":"default"'  100 150 200
inject_metric "tetragon_events_total"              '"type":"process_kprobe","namespace":"default"'  40  60  87
inject_metric "tetragon_events_total"              '"type":"process_exit","namespace":"default"'    90 140 198
inject_metric "tetragon_policy_violations_total"   '"policy":"network-monitor","action":"Post"'     5   9  12
inject_metric "benthos_input_received_total"       '"label":"tetragon_reader","path":"root.input"' 400 480 527
inject_metric "benthos_input_connection_up"        '"label":"tetragon_reader","path":"root.input"'   1   1   1
inject_metric "benthos_output_connection_up"       '"label":"victorialogs_push","path":"root.output"' 1 1 1
inject_metric "soc_cve_detections_total"           '"severity":"CRITICAL","cve":"CVE-2024-3094"'    1   1   2
inject_metric "soc_cve_detections_total"           '"severity":"HIGH","cve":"CVE-2024-1234"'        3   4   5
inject_metric "soc_misp_ioc_hits_total"            '"feed":"threatfox","type":"ip"'                 5   7   9
inject_metric "soc_misp_ioc_hits_total"            '"feed":"abuse.ch","type":"domain"'              2   3   4
inject_metric "soc_soar_playbooks_triggered_total" '"workflow":"alert-response","status":"success"' 2   4   6
inject_metric "soc_soar_playbooks_triggered_total" '"workflow":"ioc-block","status":"success"'      1   2   3
inject_metric "soc_security_events_total"          '"source":"tetragon","severity":"high"'         10  15  22
inject_metric "soc_security_events_total"          '"source":"tetragon","severity":"medium"'       30  40  47

echo
echo "Metrics injected!"

echo
echo "=== INJECT LOGS ke VictoriaLogs ==="
NOW_NS=$(date +%s%N)
TS="$NOW_NS"

# Tetragon: curl request
curl -s -X POST http://localhost:9428/insert/loki/api/v1/push   -H 'Content-Type: application/json'   --data-raw "{"streams":[
    {"stream":{"job":"tetragon","level":"info"},
     "values":[["$TS","{\"process_exec\":{\"binary\":\"/usr/bin/curl\",\"arguments\":\"https://example.com\",\"pid\":12345,\"uid\":1000},\"namespace\":\"default\",\"node\":\"lab-host\"}}"]]}
  ]}"

# Suricata: SSH brute force alert
curl -s -X POST http://localhost:9428/insert/loki/api/v1/push   -H 'Content-Type: application/json'   --data-raw "{"streams":[
    {"stream":{"job":"suricata","level":"critical"},
     "values":[["$TS","{\"event_type\":\"alert\",\"src_ip\":\"192.168.1.100\",\"dest_ip\":\"10.0.0.5\",\"dest_port\":22,\"proto\":\"TCP\",\"alert\":{\"signature\":\"ET SCAN SSH Brute Force Attempt\",\"category\":\"attempted-admin\",\"severity\":1}}"}]]}
  ]}"

# Suricata: HTTP curl request captured
curl -s -X POST http://localhost:9428/insert/loki/api/v1/push   -H 'Content-Type: application/json'   --data-raw "{"streams":[
    {"stream":{"job":"suricata","level":"info"},
     "values":[["$TS","{\"event_type\":\"http\",\"src_ip\":\"10.0.0.5\",\"http\":{\"hostname\":\"example.com\",\"url\":\"/\",\"http_user_agent\":\"curl/7.88.1\",\"http_method\":\"GET\",\"status\":200}}"}]]}
  ]}"

echo
echo "Logs injected!"
echo
echo "Buka Grafana Explore -> VictoriaLogs -> {job="suricata"}"
echo "Buka Grafana Explore -> VictoriaLogs -> {job="tetragon"}"
