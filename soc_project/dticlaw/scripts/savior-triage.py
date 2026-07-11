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
# Aset sah (whitelist) agar model punya konteks membedakan FP dari TP. Format
# "ip=keterangan;ip2=..." — sumber: env KNOWN_ASSETS (sama dengan savior-monitor)
# atau flag --assets. Tanpa ini model men-default brute-force jadi TP.
KNOWN_ASSETS = os.environ.get(
    "KNOWN_ASSETS", ENV.get("KNOWN_ASSETS", "192.168.56.10=admin jump host/bastion sah"))


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


def parse_assets():
    """KNOWN_ASSETS 'ip=desc;ip2=desc2' -> {ip: desc}."""
    out = {}
    for part in KNOWN_ASSETS.split(";"):
        part = part.strip()
        if "=" in part:
            ip, desc = part.split("=", 1)
            out[ip.strip()] = desc.strip()
    return out


ASSETS = parse_assets()


def dedupe(alerts):
    """Gabung alert dgn tanda-tangan sama (rule+srcip+desc) jadi satu entri bercount.
    Alert brute-force yang sama HARUS dapat verdict sama; menilai tiap salinan terpisah
    bikin model tak konsisten. full_log diabaikan agar variasi port tidak memecah grup."""
    groups = {}
    for a in alerts:
        key = (a["rule_id"], a["srcip"], a["desc"])
        g = groups.setdefault(key, dict(a, count=0))
        g["count"] += 1
    return sorted(groups.values(), key=lambda x: -x["count"])


# Rule Wazuh keluarga "login gagal / user-group tak ada" (sinyal khas FP dari aset sah).
AUTH_FAIL_RULES = {"5710", "5711", "5712", "5716", "5720", "5758", "5760"}


def deterministic_verdict(a):
    """Verdict OTORITATIF dihitung di kode — tidak bergantung LLM (yang bisa halusinasi).
    Fokus: sinyal FP paling umum = brute-force/login-gagal dari aset yang sah."""
    srcip = a.get("srcip")
    rid = str(a.get("rule_id"))
    known = bool(srcip) and srcip in ASSETS
    if known and rid in AUTH_FAIL_RULES:
        return "FP", f"login gagal dari aset sah {srcip} ({ASSETS[srcip]}) — bukan serangan"
    if not known and rid in AUTH_FAIL_RULES and a.get("count", 1) >= 3:
        return "TP", f"pola brute-force ({a['count']}x) dari IP tak dikenal {srcip}"
    if not known and rid in AUTH_FAIL_RULES:
        return "NEEDS-INVESTIGATION", f"login gagal dari IP tak dikenal {srcip} — volume rendah"
    return "NEEDS-INVESTIGATION", "perlu konteks tambahan (rule di luar pola auth-failure)"


def asset_tag(srcip):
    """Pencocokan aset DETERMINISTIK (di kode, bukan diserahkan ke LLM yang sering
    salah cross-reference). Kembalikan anotasi eksplisit untuk disisipkan ke prompt."""
    if srcip and srcip in ASSETS:
        return f"ASET SAH/DIKENAL ({ASSETS[srcip]}) -> condong FALSE POSITIVE"
    if not srcip:
        return "tanpa srcip"
    return "srcip TIDAK dikenal -> nilai berdasarkan pola"


def triage(alerts):
    uniq = dedupe(alerts)
    listing = "\n".join(
        f"{i+1}. (x{a['count']}) rule.id={a['rule_id']} level={a['level']} | {a['desc']} | "
        f"srcip={a['srcip']} [{asset_tag(a['srcip'])}] | log: {a['full_log']}"
        for i, a in enumerate(uniq)
    )
    prompt = (
        "Kamu analis SOC. Berikut alert NYATA dari Wazuh Indexer (jangan tambah data di luar ini). "
        "Tiap alert SUDAH diberi anotasi status aset di dalam [ ] — PERCAYAI anotasi itu, "
        "jangan menebak ulang apakah IP dikenal.\n"
        "Aturan: anotasi 'ASET SAH/DIKENAL' + pola login gagal/user salah = FALSE POSITIVE "
        "(admin salah ketik / probe sah). 'srcip TIDAK dikenal' + pola brute-force = TRUE POSITIVE.\n"
        "Untuk SETIAP nomor beri satu baris: "
        "'N. VERDICT: <TP|FP|FN|NEEDS-INVESTIGATION> — alasan singkat + rekomendasi'.\n\n"
        + listing
    )
    body = json.dumps({"model": MODEL, "stream": False,
                       "options": {"temperature": 0},  # deterministik
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    d = json.load(urllib.request.urlopen(req, timeout=180))
    return d["message"]["content"], time.time() - t, len(uniq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--ip")
    ap.add_argument("--rule")
    ap.add_argument("--min-level", type=int)
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--no-ai", action="store_true", help="verdict deterministik saja, tanpa panggil model")
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

    # 1) VERDICT OTORITATIF (deterministik di kode — tahan halusinasi)
    uniq = dedupe(alerts)
    print("\n=== VERDICT (deterministik, otoritatif) ===")
    for i, a in enumerate(uniq):
        v, why = deterministic_verdict(a)
        print(f"{i+1}. (x{a['count']}) rule {a['rule_id']} srcip={a['srcip']} "
              f"→ VERDICT: {v} — {why}")

    # 2) Penjelasan AI (advisory; boleh divariasikan/dikoreksi operator)
    if not args.no_ai:
        print("\n=== Penjelasan savior_v2 (advisory) ===")
        out, dur, nuniq = triage(alerts)
        print(out)
        print(f"\n--- {len(alerts)} alert ({nuniq} unik) dalam {dur:.1f}s "
              f"(savior_v2 @ GPU, temp=0) · verdict otoritatif = blok di atas ---")


if __name__ == "__main__":
    main()
