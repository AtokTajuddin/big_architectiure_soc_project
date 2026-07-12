#!/usr/bin/env python3
"""savior-bridge — jembatan akses Savior agent ke Wazuh & Shuffle SOAR.

Dipanggil oleh Savior agent (tool `exec`) untuk memeriksa log & mengambil tindakan
saat menentukan true positive / false positive / false negative.

Subcommands:
  shuffle-trigger '<json>'   POST payload ke webhook Shuffle (webhook_wazuh)
  shuffle-exec <workflow_id> '<json>'   jalankan workflow via Shuffle API (shuffle_api_key)
  wazuh-alerts [--limit N] [--q "rule.level>=10"]   ambil alert terbaru via Wazuh API
  wazuh-query  '<index-query-json>'   query indexer Wazuh (Opensearch) bila dikonfigurasi
  env                        tampilkan konfigurasi yang terdeteksi (tanpa bocorkan secret)

Konfigurasi dibaca dari .env (cwd dan parent):
  shuffle_api_key, webhook_wazuh
  WAZUH_API_URL (mis. https://127.0.0.1:55000), WAZUH_API_USER, WAZUH_API_PASS
  WAZUH_INDEXER_URL, WAZUH_INDEXER_USER, WAZUH_INDEXER_PASS
"""
import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path


def load_env():
    env = dict(os.environ)
    for p in [Path.cwd() / ".env", Path.cwd().parent / ".env",
              Path(__file__).resolve().parent.parent / ".env",
              Path(__file__).resolve().parent.parent.parent / ".env"]:
        if p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


ENV = load_env()
# Wazuh self-signed cert umum -> jangan verifikasi by default (lokal SOC).
NO_VERIFY = ssl._create_unverified_context()


def http(method, url, headers=None, data=None, auth=None, insecure=True):
    h = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    if auth:
        import base64
        tok = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", "Basic " + tok)
    ctx = NO_VERIFY if insecure else None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def need(key):
    v = ENV.get(key)
    if not v:
        print(json.dumps({"error": f"{key} belum diset di .env"}))
        sys.exit(2)
    return v


def require_approval(action):
    """Human-in-the-loop: tindakan butuh persetujuan eksplisit.
    Lewati hanya bila operator memberi --approved atau SAVIOR_ALLOW_ACTIONS=1."""
    approved = "--approved" in sys.argv or ENV.get("SAVIOR_ALLOW_ACTIONS") == "1"
    if not approved:
        print(json.dumps({
            "blocked": action,
            "reason": "human-in-the-loop: tindakan butuh persetujuan operator.",
            "how": f"minta operator setujui, lalu jalankan ulang dengan flag --approved (mis. savior-bridge.py {action} '<json>' --approved)",
        }))
        sys.exit(3)


def cmd_shuffle_trigger(argv):
    require_approval("shuffle-trigger")
    argv = [a for a in argv if a != "--approved"]
    url = need("webhook_wazuh")
    payload = json.loads(argv[0]) if argv else {"source": "savior-agent", "ping": True}
    status, body = http("POST", url, data=payload)
    print(json.dumps({"action": "shuffle-trigger", "http": status, "result": body}))


def cmd_shuffle_exec(argv):
    require_approval("shuffle-exec")
    argv = [a for a in argv if a != "--approved"]
    wf = argv[0]
    payload = json.loads(argv[1]) if len(argv) > 1 else {}
    key = need("shuffle_api_key")
    url = f"https://shuffler.io/api/v1/workflows/{wf}/execute"
    status, body = http("POST", url, headers={"Authorization": f"Bearer {key}"}, data=payload)
    print(json.dumps({"action": "shuffle-exec", "workflow": wf, "http": status, "result": body}))


def _wazuh_token():
    base = need("WAZUH_API_URL").rstrip("/")
    user = need("WAZUH_API_USER")
    pw = need("WAZUH_API_PASS")
    status, body = http("POST", f"{base}/security/user/authenticate", auth=(user, pw))
    if status == 200 and isinstance(body, dict):
        return base, body.get("data", {}).get("token")
    print(json.dumps({"error": "auth Wazuh gagal", "http": status, "body": body}))
    sys.exit(2)


def cmd_wazuh_alerts(argv):
    base, token = _wazuh_token()
    limit = "20"
    q = None
    i = 0
    while i < len(argv):
        if argv[i] == "--limit":
            limit = argv[i + 1]; i += 2
        elif argv[i] == "--q":
            q = argv[i + 1]; i += 2
        else:
            i += 1
    url = f"{base}/manager/logs?limit={limit}" + (f"&q={urllib.parse.quote(q)}" if q else "")
    status, body = http("GET", url, headers={"Authorization": f"Bearer {token}"})
    print(json.dumps({"action": "wazuh-alerts", "http": status, "result": body}))


def cmd_wazuh_query(argv):
    base = need("WAZUH_INDEXER_URL").rstrip("/")
    user = need("WAZUH_INDEXER_USER")
    pw = need("WAZUH_INDEXER_PASS")
    query = json.loads(argv[0]) if argv else {"query": {"match_all": {}}, "size": 10}
    url = f"{base}/wazuh-alerts-*/_search"
    status, body = http("POST", url, data=query, auth=(user, pw))
    print(json.dumps({"action": "wazuh-query", "http": status, "result": body}))


def cmd_env(_argv):
    def has(k):
        return "set" if ENV.get(k) else "MISSING"
    print(json.dumps({
        "shuffle_api_key": has("shuffle_api_key"),
        "webhook_wazuh": has("webhook_wazuh"),
        "WAZUH_API_URL": ENV.get("WAZUH_API_URL", "MISSING"),
        "WAZUH_API_USER": has("WAZUH_API_USER"),
        "WAZUH_INDEXER_URL": ENV.get("WAZUH_INDEXER_URL", "MISSING"),
    }, indent=2))


COMMANDS = {
    "shuffle-trigger": cmd_shuffle_trigger,
    "shuffle-exec": cmd_shuffle_exec,
    "wazuh-alerts": cmd_wazuh_alerts,
    "wazuh-query": cmd_wazuh_query,
    "env": cmd_env,
}

if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (dipakai di wazuh_alerts)
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
