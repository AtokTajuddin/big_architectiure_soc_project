#!/usr/bin/env python3
"""Savior Monitor — pendamping SOC otomatis.

Tiap INTERVAL (default 5 menit): tarik alert NYATA dari Wazuh Indexer, triase dengan
savior_v2 (Ollama/GPU), simpan ringkasan, sajikan ke dashboard web + log persistent.
Deterministik: model hanya menilai data yang benar-benar ada di Wazuh (anti-halusinasi).
"""
import json
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WAZUH_URL = os.environ.get("WAZUH_INDEXER_URL", "https://127.0.0.1:9200").rstrip("/")
WAZUH_USER = os.environ.get("WAZUH_INDEXER_USER", "admin")
WAZUH_PASS = os.environ.get("WAZUH_INDEXER_PASS", "SecretPassword")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
# Sumber data Grafana: VictoriaMetrics (metrics) + VictoriaLogs (log) — datasource
# yang sama dengan yang ditampilkan dashboard Grafana mini-SOC.
VM_URL = os.environ.get("VM_URL", "http://127.0.0.1:8428").rstrip("/")
VL_URL = os.environ.get("VL_URL", "http://127.0.0.1:9428").rstrip("/")
# label=promql, dipisah ';' — bisa dioverride via env tanpa rebuild
VM_QUERIES = os.environ.get("VM_QUERIES", ";".join([
    "IOC match MISP=sum(misp_ioc_match_total)",
    "Threat event MISP aktif=sum(misp_events_active)",
    "Alert diproses Shuffle SOAR=sum(shuffle_alerts_processed_total)",
    "Eksekusi workflow SOAR gagal=sum(shuffle_action_failures_total)",
    "Deteksi CVE oleh ML engine=sum(ml_cve_detections_total)",
    "Indikasi evasion (ML)=sum(ml_evasion_detected_total)",
]))
MODEL = os.environ.get("SAVIOR_MODEL", "savior_v2")
INTERVAL = int(os.environ.get("INTERVAL_SECONDS", "300"))
MAX_ALERTS = int(os.environ.get("MAX_ALERTS", "20"))
KNOWN_ASSETS = os.environ.get("KNOWN_ASSETS", "")  # mis. "192.168.56.10=admin bastion;10.0.0.5=scanner"
PORT = int(os.environ.get("PORT", "8899"))
DATA = os.environ.get("DATA_DIR", "/data")
HISTORY = os.path.join(DATA, "summaries.jsonl")

NO_VERIFY = ssl._create_unverified_context()
_LOCK = threading.Lock()
_SUMMARIES = []  # in-memory ring (terbaru di depan)


def log(*a):
    print(datetime.now(timezone.utc).isoformat(), *a, flush=True)


def wazuh_recent():
    """Alert dalam INTERVAL terakhir, terbaru dulu."""
    body = {
        "size": MAX_ALERTS,
        "sort": [{"timestamp": {"order": "desc"}}],
        "query": {"range": {"timestamp": {"gte": f"now-{INTERVAL}s"}}},
    }
    import base64
    tok = base64.b64encode(f"{WAZUH_USER}:{WAZUH_PASS}".encode()).decode()
    req = urllib.request.Request(
        f"{WAZUH_URL}/wazuh-alerts-*/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Basic " + tok},
        method="POST",
    )
    with urllib.request.urlopen(req, context=NO_VERIFY, timeout=20) as r:
        d = json.load(r)
    hits = d.get("hits", {}).get("hits", [])
    total = d.get("hits", {}).get("total", {}).get("value", 0)
    out = []
    for h in hits:
        s = h.get("_source", {})
        r_ = s.get("rule", {})
        out.append({
            "ts": s.get("timestamp", ""),
            "rule_id": r_.get("id"),
            "level": r_.get("level"),
            "desc": r_.get("description"),
            "groups": r_.get("groups"),
            "srcip": s.get("data", {}).get("srcip"),
            "agent": s.get("agent", {}).get("name"),
            "full_log": (s.get("full_log") or "")[:200],
        })
    return out, total


def _http_json(url, data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, context=NO_VERIFY, timeout=timeout) as r:
        return json.load(r)


def grafana_context():
    """Baca data yang sama dengan dashboard Grafana: metrics VictoriaMetrics
    (MISP/Shuffle/ML) + volume log VictoriaLogs per stream. Tiap query gagal
    dilewati diam-diam agar monitor tetap jalan walau stack Grafana mati."""
    lines = []
    for spec in VM_QUERIES.split(";"):
        if "=" not in spec:
            continue
        label, expr = spec.split("=", 1)
        try:
            d = _http_json(f"{VM_URL}/api/v1/query?" +
                           urllib.parse.urlencode({"query": expr.strip()}))
            res = d.get("data", {}).get("result", [])
            val = res[0]["value"][1] if res else "0"
            lines.append(f"- {label.strip()}: {val}")
        except Exception:  # noqa: BLE001
            pass
    # VictoriaLogs mengembalikan NDJSON (1 objek JSON per baris)
    try:
        q = urllib.parse.urlencode(
            {"query": f"_time:{INTERVAL}s * | stats by (_stream) count() n"})
        req = urllib.request.Request(f"{VL_URL}/select/logsql/query?{q}")
        with urllib.request.urlopen(req, timeout=15) as r:
            for raw in r.read().decode().strip().splitlines()[:8]:
                if not raw:
                    continue
                row = json.loads(raw)
                lines.append(
                    f"- Log {row.get('_stream', '?')}: {row.get('n', '?')} baris/interval")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def triage(alerts, metrics_ctx=""):
    listing = "\n".join(
        f"{i+1}. rule.id={a['rule_id']} level={a['level']} | {a['desc']} | "
        f"srcip={a['srcip']} groups={a['groups']} | log: {a['full_log']}"
        for i, a in enumerate(alerts)
    )
    assets = f"\nASET DIKENAL (sah): {KNOWN_ASSETS}" if KNOWN_ASSETS else ""
    grafana = (
        "\n\nKONTEKS PIPELINE (metrics Grafana/VictoriaMetrics, data nyata):\n" + metrics_ctx
    ) if metrics_ctx else ""
    prompt = (
        "Kamu Savior, analis SOC. Berikut alert NYATA dari Wazuh dalam 5 menit terakhir "
        "(JANGAN tambah data di luar ini)." + assets + grafana + "\n\n" + listing + "\n\n"
        "Buat RINGKASAN untuk SOC engineer:\n"
        "1) STATUS keseluruhan (TENANG / PERLU PERHATIAN / KRITIS).\n"
        "2) Hitung: berapa kemungkinan TRUE POSITIVE, FALSE POSITIVE, FALSE NEGATIVE.\n"
        "3) Sorot alert yang FALSE POSITIVE + alasan singkat.\n"
        "4) Sorot yang TRUE POSITIVE/butuh aksi + rekomendasi singkat.\n"
        "Ringkas, poin-poin."
    )
    body = json.dumps({"model": MODEL, "stream": False,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)["message"]["content"]


def cycle():
    ts = datetime.now(timezone.utc).isoformat()
    try:
        alerts, total = wazuh_recent()
    except Exception as e:  # noqa: BLE001
        rec = {"ts": ts, "error": f"gagal konek Wazuh: {e}", "n": 0, "summary": ""}
        log("ERROR wazuh:", e)
        _store(rec)
        return
    metrics_ctx = grafana_context()
    if not alerts:
        rec = {"ts": ts, "n": 0, "total": total,
               "summary": "STATUS: TENANG — tidak ada alert baru dalam 5 menit terakhir.",
               "metrics": metrics_ctx, "alerts": []}
    else:
        t0 = time.time()
        try:
            summary = triage(alerts, metrics_ctx)
        except Exception as e:  # noqa: BLE001
            summary = f"(gagal triase savior_v2: {e})"
        rec = {"ts": ts, "n": len(alerts), "total": total,
               "summary": summary, "metrics": metrics_ctx,
               "dur": round(time.time() - t0, 1),
               "alerts": alerts}
        log(f"cycle: {len(alerts)} alert ditriase dalam {rec.get('dur')}s")
    _store(rec)


def _store(rec):
    with _LOCK:
        _SUMMARIES.insert(0, rec)
        del _SUMMARIES[50:]
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(HISTORY, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:  # noqa: BLE001
        log("WARN tulis history:", e)


def loop():
    log(f"Savior Monitor mulai. Interval={INTERVAL}s, Wazuh={WAZUH_URL}, model={MODEL}")
    while True:
        cycle()
        time.sleep(INTERVAL)


PAGE = """<!doctype html><html lang=id><head><meta charset=utf-8>
<meta http-equiv=refresh content=30><title>Savior Monitor</title>
<style>
body{{font-family:ui-sans-serif,system-ui,Segoe UI,Roboto;background:#0d1117;color:#e6edf3;margin:0;padding:20px}}
h1{{font-size:18px}} .sub{{color:#8b949e;font-size:13px;margin-bottom:16px}}
.card{{background:#161b22;border:1px solid #2a3140;border-radius:12px;padding:16px;margin-bottom:14px}}
.latest{{border-color:#ff6b4a}} .ts{{color:#8b949e;font-size:12px}}
pre{{white-space:pre-wrap;word-wrap:break-word;font-family:inherit;line-height:1.5;margin:8px 0 0}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600}}
.ok{{background:#13361f;color:#3fb950}} .warn{{background:#3a2a13;color:#ff6b4a}} .err{{background:#3a1313;color:#f85149}}
</style></head><body>
<h1>🛡️ Savior Monitor — ringkasan SOC tiap {iv} dtk</h1>
<div class=sub>Sumber: Wazuh + Grafana/VictoriaMetrics (data nyata) · model savior_v2 (GPU) · auto-refresh 30s</div>
{cards}
</body></html>"""


def render():
    with _LOCK:
        items = list(_SUMMARIES[:20])
    if not items:
        cards = "<div class=card>Belum ada siklus. Menunggu pengumpulan pertama…</div>"
    else:
        cards = ""
        for i, r in enumerate(items):
            cls = "card latest" if i == 0 else "card"
            s = r.get("summary", "") or r.get("error", "")
            up = s.upper()
            badge = '<span class="badge ok">TENANG</span>' if "TENANG" in up else (
                '<span class="badge err">KRITIS</span>' if "KRITIS" in up else
                '<span class="badge warn">PERHATIAN</span>' if "PERHATIAN" in up else "")
            head = f"<span class=ts>{r.get('ts','')}</span> · {r.get('n',0)} alert {badge}"
            mx = r.get("metrics", "")
            mblock = (f'<details><summary class=ts>metrics pipeline (Grafana)</summary>'
                      f'<pre class=ts>{_esc(mx)}</pre></details>') if mx else ""
            cards += f'<div class="{cls}">{head}<pre>{_esc(s)}</pre>{mblock}</div>'
    return PAGE.format(iv=INTERVAL, cards=cards)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/latest"):
            with _LOCK:
                body = json.dumps(_SUMMARIES[0] if _SUMMARIES else {}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.end_headers(); self.wfile.write(body); return
        body = render().encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers(); self.wfile.write(body)


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    log(f"Dashboard di :{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
