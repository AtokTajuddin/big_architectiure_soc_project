"""Kredensial Nexus Sentinel — dua tingkat, meniru pola provider AI (AI Studio).

1. Bearer key  (nx_live_...)  — untuk integrasi sederhana: Benthos, curl, script.
   Dikirim via header:  Authorization: Bearer <key>

2. Agent keypair (nxa_...)    — identitas kriptografis per-agent (Ed25519).
   Private key DIEKSPOR SEKALI ke pengguna (file kredensial JSON) lalu dipasang
   ke agent mana pun (Savior, dticlaw, sistem eksternal). Gateway hanya
   menyimpan public key, jadi bocornya database TIDAK membocorkan kredensial.

   Agent menandatangani setiap request:
     message   = "<METHOD>\n<PATH>\n<UNIX_TS>\n<SHA256_HEX(BODY)>"
     signature = base64(Ed25519_sign(private_key, message))
   Header:
     X-Agent-Key-Id:    nxa_...
     X-Agent-Timestamp: <unix detik>
     X-Agent-Signature: <base64>
"""
import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature

import db

# Toleransi beda jam agent vs gateway (anti replay lama)
SIG_MAX_SKEW_SECONDS = int(os.getenv("AGENT_SIG_MAX_SKEW", "300"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------- bearer keys ----------

def create_bearer_key(label: str) -> dict:
    key = f"nx_live_{secrets.token_hex(16)}"
    db.add_bearer_key(key, label, _now_iso())
    return {"label": label, "key": key}


def seed_bearer_key(key: str, label: str):
    """Idempoten — dipakai untuk bootstrap key default (mis. milik Benthos)."""
    db.add_bearer_key(key, label, _now_iso())


def verify_bearer(token: str) -> Optional[str]:
    """Return label kalau valid, None kalau tidak."""
    return db.bearer_key_valid(token)


# ---------- agent keypairs ----------

def canonical_message(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}".encode()


def create_agent_keypair(label: str) -> dict:
    """Buat identitas agent baru. Private key hanya ada di return value ini —
    tidak pernah disimpan server. Tampilkan/unduh sekali, seperti API key
    provider AI."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    key_id = f"nxa_{secrets.token_hex(8)}"
    created_at = _now_iso()
    db.add_agent_key(key_id, label, public_pem, created_at)

    return {
        "type": "nexus-sentinel-agent-credential",
        "version": 1,
        "key_id": key_id,
        "label": label,
        "algorithm": "Ed25519",
        "created_at": created_at,
        "private_key_pem": private_pem,
        "public_key_pem": public_pem,
        "sign_format": "METHOD\\nPATH\\nUNIX_TIMESTAMP\\nSHA256_HEX(BODY)",
        "headers": {
            "key_id": "X-Agent-Key-Id",
            "timestamp": "X-Agent-Timestamp",
            "signature": "X-Agent-Signature (base64)",
        },
    }


def verify_agent_signature(
    key_id: str,
    timestamp: str,
    signature_b64: str,
    method: str,
    path: str,
    body: bytes,
) -> Optional[str]:
    """Return label agent kalau tanda tangan sah, None kalau tidak."""
    row = db.get_agent_key(key_id)
    if not row or row["revoked"]:
        return None

    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return None
    if abs(time.time() - ts) > SIG_MAX_SKEW_SECONDS:
        return None

    try:
        public_key = serialization.load_pem_public_key(row["public_key_pem"].encode())
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, canonical_message(method, path, timestamp, body))
    except (InvalidSignature, ValueError, TypeError):
        return None

    db.touch_agent_key(key_id, _now_iso())
    return row["label"]
