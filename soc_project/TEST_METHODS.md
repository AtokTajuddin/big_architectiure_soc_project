# SOC Project — Test & Verification Methods

Dokumen ini mencatat semua metode pengujian untuk memastikan sistem SOC (Suricata → Benthos → ML Engine → Grafana) berjalan dengan benar.

---

## Arsitektur Pipeline

```
DVWA (172.18.0.15:80)
        ↓ HTTP traffic on soc-br0
Suricata (af-packet soc-br0) → eve.json
        ↓ tail -F via Benthos
Benthos → VictoriaLogs (Loki)
        ↓ POST /ingest (alerts only)
ML Engine (OWASP/CVE enrichment) → Prometheus metrics
        ↓
VictoriaMetrics + Grafana dashboard
```

---

## 1. Cek Status Semua Container

```bash
sudo docker ps --format "table {{.Names}}\t{{.Status}}" | grep -v "Exited"
```

**Expected**: semua container `Up`, tidak ada yang `Restarting` atau `Exited`.

---

## 2. Verifikasi Suricata Rules Load Bersih

```bash
sudo docker logs suricata 2>&1 | grep -E "^E:|Engine started"
```

**Expected**: 
- Baris `Engine started` ada
- **Tidak ada baris** yang diawali `E:` (syntax error)

---

## 3. Cek Interface Suricata Monitoring

```bash
# Pastikan soc-br0 adalah bridge untuk soc_project_soc-net
sudo docker network inspect soc_project_soc-net | python3 -c \
  "import sys,json; d=json.load(sys.stdin)[0]; print('Bridge:', d['Options'].get('com.docker.network.bridge.name'))"
```

**Expected**: `Bridge: soc-br0`

---

## 4. Generate DVWA Attacks (dari dalam container)

> ⚠️ PENTING: Attack harus dijalankan **dari dalam container** (bukan dari host),
> karena af-packet pada bridge tidak capture traffic yang berasal dari host gateway (172.18.0.1).

### 4a. Quick restart Suricata sebelum test batch (recommended)

```bash
sudo docker compose -f /home/atokdins/soc_project/docker-compose.yml \
  up -d --force-recreate suricata && sleep 10
sudo docker logs suricata 2>&1 | grep -E "^E:|Engine started"
```

### 4b. Jalankan attack suite dari ml-engine container

```bash
sudo docker exec ml-engine python3 -c "
import urllib.request, urllib.parse, http.cookiejar
base='http://172.18.0.15'
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def get(url, data=None):
    try: return opener.open(urllib.request.Request(url, data)).status
    except Exception as e: return str(e)[:50]

# Login
print('login:', get(base+'/login.php',
    urllib.parse.urlencode({'username':'admin','password':'password','Login':'Login'}).encode()))

# A03 — SQL Injection
print('sqli:', get(base+'/vulnerabilities/sqli/?id=1+UNION+SELECT+user(),database()--+-'))

# A03 — XSS
print('xss:', get(base+'/vulnerabilities/xss_r/?name=%3Cscript%3Ealert(1)%3C%2Fscript%3E'))

# A03 — Command Injection
print('exec:', get(base+'/vulnerabilities/exec/',
    urllib.parse.urlencode({'ip':'127.0.0.1|id','Submit':'Submit'}).encode()))

# A05 — LFI
print('lfi:', get(base+'/vulnerabilities/fi/?page=../../../../../../etc/passwd'))

# A01 — Brute Force (6x)
for i in range(6):
    urllib.request.urlopen(urllib.request.Request(base+'/login.php',
        urllib.parse.urlencode({'username':'admin','password':f'bad{i}','Login':'Login'}).encode()))
print('brute force: done')
"
```

**Expected**: semua bernilai `200`.

---

## 5. Verifikasi Suricata Alerts

```bash
sleep 6 && python3 -c "
import json, subprocess
res = subprocess.run(['grep', '\"event_type\":\"alert\"',
    '/home/atokdins/soc_project/logs/suricata/eve.json'],
    capture_output=True, text=True)
sigs = {}
for l in res.stdout.strip().split('\n'):
    if not l: continue
    try:
        e = json.loads(l)
        s = e['alert']['signature']
        if 'DNS' not in s:
            sigs[s] = sigs.get(s, 0) + 1
    except: pass
print(f'Total non-DNS alerts: {sum(sigs.values())}')
for k,v in sorted(sigs.items(), key=lambda x: -x[1]):
    print(f'  {v:>3}x {k}')
"
```

**Expected alerts** (minimal):
- `SOC DVWA SQLi UNION SELECT Attack`
- `SOC DVWA XSS Script Tag` + `SOC DVWA XSS alert() Payload`
- `SOC DVWA Command Injection POST pipe`
- `SOC DVWA LFI etc passwd`
- `SOC DVWA Security Level Cookie Tamper`

---

## 6. Verifikasi Benthos Forwarding

```bash
sudo docker logs benthos --since 60s 2>&1 | grep -v "^$" | tail -5
```

**Expected**: tidak ada `connection refused` atau `error` terbaru.
Jika ada error → restart Benthos:
```bash
sudo docker compose -f /home/atokdins/soc_project/docker-compose.yml restart benthos
```

---

## 7. Verifikasi ML Engine Enrichment

```bash
curl -s http://localhost:8000/metrics | grep -E "ml_ingest_events_total|ml_cve_detections_total{" | grep -v "^#"
```

**Expected**:
```
ml_ingest_events_total{source="suricata"} > 0
ml_ingest_events_total{source="tetragon"} > 0
ml_cve_detections_total{owasp="A03:2021",...} > 0
```

---

## 8. Verifikasi OWASP Mapping (per alert)

```bash
curl -s http://localhost:8000/metrics | grep "ml_cve_detections_total{" | grep -v "^#" | \
  python3 -c "
import sys, re
for l in sys.stdin:
    m = re.search(r'owasp=\"([^\"]+)\".*?} (\S+)', l)
    if m: print(f'  {m.group(1)} : {m.group(2)} events')
" | sort | uniq
```

**Expected OWASP categories**:
- `A01:2021` — Broken Access Control (cookie tamper, brute force)
- `A03:2021` — Injection (SQLi, XSS, Command Injection, LFI)
- `A10:2021` — SSRF

---

## 9. Verifikasi VictoriaLogs (Loki)

```bash
curl -s 'http://localhost:9428/select/logsql/query' \
  --data-urlencode 'query={job="suricata"} |= "\"event_type\":\"alert\"" | limit 3' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); [print(r['_msg'][:120]) for r in d.get('hits',[])]"
```

**Expected**: baris JSON alert dari Suricata dengan `"event_type":"alert"`.

---

## 10. Verifikasi Grafana Dashboard

1. Buka `http://localhost:3000` → login `admin` / `minisoc2026`
2. Dashboard `07 - Suricata DVWA Attacks`:
   - Panel **"Suricata Alerts Over Time by Attack Type"**: harus ada timeseries
   - Panel **"Top Attack Signatures"**: list signatures SQLi, XSS, CMDi, LFI
3. Dashboard `04 - ML Engine`: stat panels `Suricata Events ML`, `CVE Matches` harus > 0

---

## Troubleshooting Cepat

| Symptom | Diagnosa | Fix |
|---------|----------|-----|
| Suricata tidak alert sama sekali | Traffic tidak melewati soc-br0 dari host | Gunakan `docker exec ml-engine python3` untuk attack |
| Alert ada tapi ML engine `source="suricata"=0` | Benthos failed saat ml-engine restart | Restart Benthos + kirim attack ulang |
| OWASP mapping semua A06 | Bug `get_owasp(cat or sig)` sudah difix → `get_owasp(text)` | Restart ml-engine |
| Rule syntax error saat Suricata start | Cek `E:` di logs | Fix di `suricata/suricata.rules` |
| Attack ke-2 tidak menghasilkan alerts | Flow tracking state issue (af-packet) | `--force-recreate suricata` lalu attack segera |

---

## Key Facts

- **DVWA IP di bridge**: `172.18.0.15` (bukan `localhost:8080`)
- **Port di soc-br0**: `80` (bukan `8080` — Docker DNAT terjadi sebelum bridge)
- **Attack source harus**: dari container (mis. `docker exec ml-engine`)
- **Suricata interface**: `soc-br0` (af-packet mode)
- **ML Engine port**: `8000` (http://localhost:8000/metrics untuk Prometheus)
- **Grafana login**: `admin` / `minisoc2026`, port `3000`
