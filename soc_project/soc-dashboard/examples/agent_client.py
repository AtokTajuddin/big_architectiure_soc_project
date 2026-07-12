#!/usr/bin/env python3
"""Contoh klien agent Nexus Sentinel.

Pakai file kredensial JSON yang diunduh dari dashboard
(API Key Access Manager -> Agent Identity Keypairs -> Generate Keypair),
lalu tanda tangani setiap request dengan Ed25519.

Contoh:
    python3 agent_client.py nxa_xxxx-credential.json whoami
    python3 agent_client.py nxa_xxxx-credential.json ingest '{"event_type":"alert",...}'
"""
import base64
import hashlib
import json
import sys
import time

import requests
from cryptography.hazmat.primitives import serialization

GATEWAY = "http://localhost:8000"


def sign_request(credential: dict, method: str, path: str, body: bytes) -> dict:
    private_key = serialization.load_pem_private_key(
        credential["private_key_pem"].encode(), password=None
    )
    timestamp = str(int(time.time()))
    body_hash = hashlib.sha256(body or b"").hexdigest()
    message = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}".encode()
    signature = base64.b64encode(private_key.sign(message)).decode()
    return {
        "X-Agent-Key-Id": credential["key_id"],
        "X-Agent-Timestamp": timestamp,
        "X-Agent-Signature": signature,
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    credential = json.load(open(sys.argv[1]))
    command = sys.argv[2]

    if command == "whoami":
        method, path, body = "GET", "/api/whoami", b""
    elif command == "ingest":
        method, path = "POST", "/ingest"
        raw = sys.argv[3] if len(sys.argv) > 3 else '{"test": "hello from agent"}'
        body = json.dumps({"raw": raw, "source_hint": "test"}).encode()
    else:
        print(f"Perintah tidak dikenal: {command}")
        sys.exit(1)

    headers = sign_request(credential, method, path, body)
    headers["Content-Type"] = "application/json"

    resp = requests.request(method, f"{GATEWAY}{path}", data=body or None, headers=headers, timeout=30)
    print(f"HTTP {resp.status_code}")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
