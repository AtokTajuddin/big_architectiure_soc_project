#!/usr/bin/env python3
"""MISP Prometheus exporter — queries MySQL directly, NO API key required."""
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pymysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "misp-db")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_DB   = os.environ.get("MYSQL_DATABASE", "misp")
MYSQL_USER = os.environ.get("MYSQL_USER", "misp")
MYSQL_PASS = os.environ.get("MYSQL_PASSWORD", "mispdb2026")
PORT       = int(os.environ.get("PORT", "9419"))
INTERVAL   = int(os.environ.get("SCRAPE_INTERVAL", "60"))

state = {
    "events_active":    0,
    "indicators_total": 0,
    "ioc_ip":           0,
    "ioc_domain":       0,
    "ioc_malware":      0,
    "events_by_cat":    {},
    "last_update":      0,
}

def query_mysql():
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST, port=MYSQL_PORT,
            db=MYSQL_DB, user=MYSQL_USER,
            password=MYSQL_PASS, connect_timeout=10
        )
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM events")
            state["events_active"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM attributes")
            state["indicators_total"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM attributes WHERE type IN ('ip-src','ip-dst','ip')")
            state["ioc_ip"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM attributes WHERE type IN ('domain','hostname')")
            state["ioc_domain"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM attributes WHERE category='Malware'")
            state["ioc_malware"] = c.fetchone()[0]

            c.execute("SELECT category, COUNT(*) FROM attributes GROUP BY category LIMIT 20")
            state["events_by_cat"] = {r[0]: r[1] for r in c.fetchall()}

            state["last_update"] = time.time()
        conn.close()
        print(f"[MISP Exporter] OK: events={state['events_active']} indicators={state['indicators_total']}")
    except Exception as e:
        print(f"[MISP Exporter] MySQL error: {e}")

def update_loop():
    while True:
        query_mysql()
        time.sleep(INTERVAL)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/metrics"):
            lag = int(time.time() - state["last_update"]) if state["last_update"] > 0 else 0
            ioc_lines = (
                f'misp_ioc_match_total{{ioc_type="ip"}} {state["ioc_ip"]}\n'
                f'misp_ioc_match_total{{ioc_type="domain"}} {state["ioc_domain"]}\n'
                f'misp_ioc_match_total{{ioc_type="malware"}} {state["ioc_malware"]}\n'
            )
            cat_lines = "\n".join(
                f'misp_events_total{{category="{cat}"}} {cnt}'
                for cat, cnt in state["events_by_cat"].items()
            ) or 'misp_events_total{category="none"} 0'
            out = (
                "# HELP misp_events_active Currently active MISP events\n"
                "# TYPE misp_events_active gauge\n"
                f"misp_events_active {state['events_active']}\n"
                "# HELP misp_indicators_total Total IOC indicators in MISP database\n"
                "# TYPE misp_indicators_total gauge\n"
                f"misp_indicators_total {state['indicators_total']}\n"
                "# HELP misp_ioc_match_total IOC type counts from MISP database\n"
                "# TYPE misp_ioc_match_total counter\n"
                f"{ioc_lines}"
                "# HELP misp_events_total MISP attributes by category\n"
                "# TYPE misp_events_total counter\n"
                f"{cat_lines}\n"
                "# HELP misp_last_sync_lag_seconds Seconds since last successful DB query\n"
                "# TYPE misp_last_sync_lag_seconds gauge\n"
                f"misp_last_sync_lag_seconds {lag}\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode())
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a): pass

if __name__ == "__main__":
    threading.Thread(target=update_loop, daemon=True).start()
    print(f"[MISP Exporter] Listening on :{PORT} — MySQL {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
