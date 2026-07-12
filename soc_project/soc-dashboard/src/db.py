"""Lapisan persistensi SQLite untuk Nexus Sentinel.

Menggantikan state in-memory (alerts_history, api_keys_db) supaya data
selamat dari restart container. Satu koneksi global + lock tulis karena
beban tulis rendah (alert SOC, bukan telemetri mentah).
"""
import os
import sqlite3
import threading
from typing import List, Optional

DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nexus.db"),
)

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    raw TEXT NOT NULL,
    source TEXT,
    src_ip TEXT,
    dest_ip TEXT,
    signature TEXT,
    owasp_category TEXT,
    cve_id TEXT,
    cwe_id TEXT,
    nist_mapping TEXT,
    severity TEXT,
    confidence REAL,
    soar_status TEXT,
    false_positive INTEGER NOT NULL DEFAULT 0,
    savior_status TEXT,
    savior_explanation TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);

CREATE TABLE IF NOT EXISTS bearer_keys (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_keys (
    key_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    public_key_pem TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    last_used TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        with _conn:
            _conn.executescript(_SCHEMA)
    return _conn


# ---------- alerts ----------

# Retensi: sensor bisa mengirim ribuan alert/menit; tabel dipangkas berkala
# supaya SQLite tidak membengkak. Riwayat penuh tetap ada di VictoriaLogs.
MAX_ALERT_ROWS = int(os.getenv("MAX_ALERT_ROWS", "5000"))
_insert_counter = 0


def insert_alert(a: dict):
    global _insert_counter
    conn = get_conn()
    with _lock, conn:
        conn.execute(
            """INSERT OR REPLACE INTO alerts
               (id, ts, raw, source, src_ip, dest_ip, signature, owasp_category,
                cve_id, cwe_id, nist_mapping, severity, confidence, soar_status,
                false_positive, savior_status, savior_explanation)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                a["id"], a["timestamp"], a["raw"], a.get("source"),
                a.get("src_ip"), a.get("dest_ip"), a.get("signature"),
                a.get("owasp_category"), a.get("cve_id"), a.get("cwe_id"),
                a.get("nist_mapping"), a.get("severity"), a.get("confidence"),
                a.get("soar_status"), int(a.get("false_positive", False)),
                a.get("savior_status"), a.get("savior_explanation"),
            ),
        )
        _insert_counter += 1
        if _insert_counter % 1000 == 0:
            conn.execute(
                "DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT ?)",
                (MAX_ALERT_ROWS,),
            )


def _row_to_alert(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["timestamp"] = d.pop("ts")
    d["false_positive"] = bool(d["false_positive"])
    return d


def list_alerts(limit: int = 50) -> List[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_alert(r) for r in rows]


def get_alert(alert_id: int) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
    return _row_to_alert(r) if r else None


def set_false_positive(alert_id: int, is_fp: bool) -> bool:
    """True jika status barusan berubah (bukan sekadar alert ada)."""
    conn = get_conn()
    with _lock, conn:
        cur = conn.execute(
            "UPDATE alerts SET false_positive=? WHERE id=? AND false_positive != ?",
            (int(is_fp), alert_id, int(is_fp)),
        )
        return cur.rowcount > 0


def alert_exists(alert_id: int) -> bool:
    return get_conn().execute(
        "SELECT 1 FROM alerts WHERE id=?", (alert_id,)
    ).fetchone() is not None


def update_savior(alert_id: int, status: str, explanation: Optional[str] = None):
    conn = get_conn()
    with _lock, conn:
        conn.execute(
            "UPDATE alerts SET savior_status=?, savior_explanation=? WHERE id=?",
            (status, explanation, alert_id),
        )


def count_alerts() -> int:
    return get_conn().execute("SELECT COUNT(*) FROM alerts").fetchone()[0]


def count_false_positives() -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM alerts WHERE false_positive=1"
    ).fetchone()[0]


# ---------- bearer keys (integrasi sederhana: Benthos, script, curl) ----------

def add_bearer_key(key: str, label: str, created_at: str):
    conn = get_conn()
    with _lock, conn:
        conn.execute(
            "INSERT OR IGNORE INTO bearer_keys (key, label, created_at) VALUES (?,?,?)",
            (key, label, created_at),
        )


def list_bearer_keys() -> List[dict]:
    rows = get_conn().execute(
        "SELECT key, label, created_at, revoked FROM bearer_keys WHERE revoked=0"
    ).fetchall()
    return [dict(r) for r in rows]


def bearer_key_valid(key: str) -> Optional[str]:
    r = get_conn().execute(
        "SELECT label FROM bearer_keys WHERE key=? AND revoked=0", (key,)
    ).fetchone()
    return r["label"] if r else None


def revoke_bearer_key(key: str):
    conn = get_conn()
    with _lock, conn:
        conn.execute("UPDATE bearer_keys SET revoked=1 WHERE key=?", (key,))


# ---------- agent keys (keypair Ed25519 per-agent) ----------

def add_agent_key(key_id: str, label: str, public_key_pem: str, created_at: str):
    conn = get_conn()
    with _lock, conn:
        conn.execute(
            "INSERT INTO agent_keys (key_id, label, public_key_pem, created_at) VALUES (?,?,?,?)",
            (key_id, label, public_key_pem, created_at),
        )


def get_agent_key(key_id: str) -> Optional[dict]:
    r = get_conn().execute(
        "SELECT * FROM agent_keys WHERE key_id=?", (key_id,)
    ).fetchone()
    return dict(r) if r else None


def list_agent_keys() -> List[dict]:
    rows = get_conn().execute(
        "SELECT key_id, label, created_at, revoked, last_used FROM agent_keys ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_agent_key(key_id: str) -> bool:
    conn = get_conn()
    with _lock, conn:
        cur = conn.execute("UPDATE agent_keys SET revoked=1 WHERE key_id=?", (key_id,))
        return cur.rowcount > 0


def touch_agent_key(key_id: str, when: str):
    conn = get_conn()
    with _lock, conn:
        conn.execute("UPDATE agent_keys SET last_used=? WHERE key_id=?", (when, key_id))
