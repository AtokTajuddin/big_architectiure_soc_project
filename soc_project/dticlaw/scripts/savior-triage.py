#!/usr/bin/env python3
"""savior-triage — koneksi NYATA ke Wazuh + triase savior_v2 (deterministik, cepat).

Tidak bergantung agentic loop: kode menarik alert ASLI dari Wazuh Indexer lalu
memberikannya ke savior_v2 (Ollama/GPU) untuk verdict TP/FP/FN. Anti-halusinasi:
model hanya menilai data yang benar-benar ada di Wazuh.

Pakai:
  savior-triage.py                  # 5 alert terbaru
  savior-triage.py --limit 10
  savior-triage.py --ip 192.168.56.10
  savior-triage.py --rule 5710
  savior-triage.py --min-level 7    # hanya level >= 7
  savior-triage.py --raw            # cuma tampilkan alert mentah (tanpa AI)
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("SAVIOR_MODEL", "savior_v2")
NO_VERIFY = ssl._create_unverified_context()


def load_env():
    env = dict(os.environ)
    here = Path(__file__).resolve()
    for p in [Path.cwd() / ".env", here.parent.parent / ".env",
              here.parent.parent.parent / ".env"]:
        if p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    return env


ENV = load_env()


def wazuh_search(query):
    base = ENV.get("WAZUH_INDEXER_URL", "https://127.0.0.1:9200").rstrip("/")
    user = ENV.get("WAZUH_INDEXER_USER", "admin")
    pw = ENV.get("WAZUH_INDEXER_PASS", "")
    import base64
    tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req = urllib.request.Request(
        f"{base}/wazuh-alerts-*/_search",
        data=json.dumps(query).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Basic " + tok},
        method="POST",
    )
    with urllib.request.urlopen(req, context=NO_VERIFY, timeout=20) as r:
        return json.load(r)


def build_query(args):
    must = []
    if args.ip:
        must.append({"match": {"data.srcip": args.ip}})
    if args.rule:
        must.append({"match": {"rule.id": str(args.rule)}})
    if args.min_level:
        must.append({"range": {"rule.level": {"gte": args.min_level}}})
    q = {"bool": {"must": must}} if must else {"match_all": {}}
    return {"size": args.limit, "sort": [{"timestamp": {"order": "desc"}}], "query": q}


def fmt_alert(src):
    r = src.get("rule", {})
    d = src.get("data", {})
    return {
        "ts": src.get("timestamp", ""),
        "rule_id": r.get("id"),
        "level": r.get("level"),
        "desc": r.get("description"),
        "groups": r.get("groups"),
        "srcip": d.get("srcip"),
        "agent": src.get("agent", {}).get("name"),
        "full_log": (src.get("full_log") or "")[:240],
    }


def triage(alerts):
    listing = "\n".join(
        f"{i+1}. rule.id={a['rule_id']} level={a['level']} | {a['desc']} | "
        f"srcip={a['srcip']} groups={a['groups']} | log: {a['full_log']}"
        for i, a in enumerate(alerts)
    )
    prompt = (
        "Berikut alert NYATA dari Wazuh Indexer (jangan tambah data di luar ini). "
        "Untuk SETIAP nomor beri satu baris: 'N. VERDICT: <TP|FP|FN|NEEDS-INVESTIGATION> — alasan singkat + rekomendasi'.\n\n"
        + listing
    )
    body = json.dumps({"model": MODEL, "stream": False,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    d = json.load(urllib.request.urlopen(req, timeout=180))
    return d["message"]["content"], time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--ip")
    ap.add_argument("--rule")
    ap.add_argument("--min-level", type=int)
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()

    try:
        res = wazuh_search(build_query(args))
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] gagal konek Wazuh Indexer ({ENV.get('WAZUH_INDEXER_URL')}): {e}")
        sys.exit(2)

    hits = res.get("hits", {}).get("hits", [])
    total = res.get("hits", {}).get("total", {}).get("value", 0)
    alerts = [fmt_alert(h["_source"]) for h in hits]
    print(f"=== Wazuh: {len(alerts)} alert (dari {total} match) ===")
    for i, a in enumerate(alerts):
        print(f"{i+1}. [{a['level']}] rule {a['rule_id']} {a['desc']} | srcip={a['srcip']} | {a['ts']}")

    if args.raw or not alerts:
        return
    print("\n=== Triase savior_v2 ===")
    out, dur = triage(alerts)
    print(out)
    print(f"\n--- {len(alerts)} alert ditriase dalam {dur:.1f}s (savior_v2 @ GPU) ---")


if __name__ == "__main__":
    main()
