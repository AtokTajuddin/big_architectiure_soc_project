"""Jembatan ke Savior (savior_v2 di Ollama, GPU host).

Setelah alert diklasifikasikan ML, Savior menghasilkan verdict triase +
penjelasan bahasa awam (untuk pemilik usaha non-teknis). Serial lewat
semaphore karena GPU cuma satu; alert di bawah SAVIOR_MIN_SEVERITY dilewati
supaya antrean GPU tidak banjir.
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger("ML-Engine")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
SAVIOR_MODEL = os.getenv("SAVIOR_MODEL", "savior_v2:latest")
SAVIOR_ENABLED = os.getenv("SAVIOR_ENABLED", "true").lower() == "true"
SAVIOR_MIN_SEVERITY = os.getenv("SAVIOR_MIN_SEVERITY", "high").lower()
SAVIOR_TIMEOUT = float(os.getenv("SAVIOR_TIMEOUT", "120"))

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_gpu_semaphore = asyncio.Semaphore(1)

# Rem antrean: volume sensor bisa ribuan alert/menit (Tetragon), GPU cuma satu.
# Lebih dari ini yang menunggu -> alert baru ditandai SKIPPED, bukan ikut antre.
MAX_PENDING = int(os.getenv("SAVIOR_MAX_PENDING", "3"))
pending = 0

_PROMPT = """Alert SOC berikut sudah dideteksi sensor dan diklasifikasikan oleh ML engine.

Kategori : {owasp_category}
Severity : {severity}
Signature: {signature}
Sumber   : {source}
Koneksi  : {src_ip} -> {dest_ip}
Log mentah (terpotong):
{raw}

Tugas:
Baris pertama: VERDICT: <TP|FP|NEEDS-INVESTIGATION>
Setelah itu jelaskan untuk PEMILIK USAHA NON-TEKNIS, bahasa Indonesia, maksimal 3 kalimat pendek tanpa jargon:
1) Apa yang terjadi. 2) Seberapa berbahaya. 3) Apa yang harus dilakukan sekarang."""


def eligible(severity: str) -> bool:
    if not SAVIOR_ENABLED:
        return False
    return _SEVERITY_RANK.get(str(severity).lower(), 1) >= _SEVERITY_RANK.get(
        SAVIOR_MIN_SEVERITY, 2
    )


def queue_available() -> bool:
    return pending < MAX_PENDING


async def explain_alert(alert: dict) -> str:
    global pending
    prompt = _PROMPT.format(
        owasp_category=alert.get("owasp_category", "-"),
        severity=alert.get("severity", "-"),
        signature=alert.get("signature", "-"),
        source=alert.get("source", "-"),
        src_ip=alert.get("src_ip", "-"),
        dest_ip=alert.get("dest_ip", "-"),
        raw=str(alert.get("raw", ""))[:2000],
    )
    pending += 1
    try:
        async with _gpu_semaphore:
            async with httpx.AsyncClient(timeout=SAVIOR_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": SAVIOR_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 256},
                        "keep_alive": "30m",
                    },
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"].strip()
    finally:
        pending -= 1


async def health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
