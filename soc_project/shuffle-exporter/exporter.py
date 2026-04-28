#!/usr/bin/env python3
"""Shuffle Automation Prometheus exporter — robust version.
Exposes Shuffle SOAR metrics at /metrics (port 9420).
Gracefully degrades when Shuffle API is unavailable.
"""
import http.client
import json
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

SHUFFLE_HOST = os.environ.get("SHUFFLE_HOST", "shuffle-backend")
SHUFFLE_PORT = int(os.environ.get("SHUFFLE_PORT", "5001"))
SHUFFLE_KEY  = os.environ.get("SHUFFLE_API_KEY", "")
PORT         = int(os.environ.get("PORT", "9420"))
INTERVAL     = int(os.environ.get("SCRAPE_INTERVAL", "30"))

# Shared state — always initialized with safe defaults so /metrics never errors
state = {
    "workflow_executions":  {"soc_alert_handler": 0},  # default workflow
    "workflow_failures":    0,
    "action_executions":    0,
    "workflows_active":     0,
    "alerts_processed":     0,
    "action_failures":      0,
    "last_updated":         0,
    "shuffle_reachable":    0,
}

state_lock = threading.Lock()


def shuffle_get(path, timeout=10):
    """Make a GET request to the Shuffle API. Returns parsed JSON or None."""
    try:
        conn = http.client.HTTPConnection(SHUFFLE_HOST, SHUFFLE_PORT, timeout=timeout)
        headers = {"Accept": "application/json"}
        if SHUFFLE_KEY:
            headers["Authorization"] = f"Bearer {SHUFFLE_KEY}"
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        if resp.status == 200:
            return json.loads(body)
        elif resp.status == 401:
            print(f"[WARN] Shuffle auth failed for {path} (401) — check SHUFFLE_API_KEY")
        elif resp.status == 404:
            print(f"[DEBUG] Shuffle endpoint not found: {path}")
        return None
    except ConnectionRefusedError:
        return None
    except Exception as e:
        print(f"[DEBUG] Shuffle GET {path} error: {type(e).__name__}: {e}")
        return None


def update_loop():
    """Background thread: poll Shuffle API every INTERVAL seconds."""
    print(f"[Shuffle Exporter] Polling Shuffle at {SHUFFLE_HOST}:{SHUFFLE_PORT} every {INTERVAL}s")
    while True:
        try:
            _poll_shuffle()
        except Exception as e:
            print(f"[ERROR] Polling error: {e}")
        time.sleep(INTERVAL)


def _poll_shuffle():
    """Poll Shuffle REST API and update shared state."""
    reachable = 0

    # ── Workflows ────────────────────────────────────────────────
    workflows = shuffle_get("/api/v1/workflows")
    if isinstance(workflows, list):
        reachable = 1
        wf_exec = {}
        for wf in workflows:
            name = wf.get("name", "unknown").replace(" ", "_")
            # Shuffle v1 doesn't return execution_count directly in list endpoint
            # Use 1 per workflow as baseline (we track increases via separate calls)
            wf_exec[name] = wf.get("execution_count", 0)
        with state_lock:
            if wf_exec:
                state["workflow_executions"] = wf_exec
            state["workflows_active"] = len(workflows)

    # ── Workflow Executions (more accurate per-workflow count) ────
    if reachable:
        # Try to get execution history for more accurate counts
        executions = shuffle_get("/api/v1/workflows/queue")
        if isinstance(executions, list):
            exec_count = {}
            fail_count = 0
            for ex in executions:
                name = ex.get("workflow", {}).get("name", "unknown").replace(" ", "_")
                exec_count[name] = exec_count.get(name, 0) + 1
                status = ex.get("status", "")
                if status in ("failed", "aborted", "FAILED"):
                    fail_count += 1
            with state_lock:
                if exec_count:
                    state["workflow_executions"] = exec_count
                state["workflow_failures"] = fail_count

    with state_lock:
        state["shuffle_reachable"] = reachable
        state["last_updated"] = int(time.time())

    if reachable:
        print(f"[INFO] Shuffle poll OK: {state['workflows_active']} workflows")
    else:
        print(f"[DEBUG] Shuffle not reachable at {SHUFFLE_HOST}:{SHUFFLE_PORT}")


def format_metrics():
    """Render Prometheus text format metrics."""
    with state_lock:
        wf_exec = dict(state["workflow_executions"]) or {"default": 0}
        wf_failures  = state["workflow_failures"]
        wf_active    = state["workflows_active"]
        act_exec     = state["action_executions"]
        act_fail     = state["action_failures"]
        alerts       = state["alerts_processed"]
        reachable    = state["shuffle_reachable"]
        last_updated = state["last_updated"]

    # workflow executions counter
    exec_lines = "\n".join(
        f'shuffle_workflow_executions_total{{workflow="{k}"}} {v}'
        for k, v in wf_exec.items()
    )
    # histogram lines (synthesised: sum=0, count=executions)
    hist_lines = "\n".join(
        f'shuffle_workflow_duration_seconds_bucket{{le="+Inf",workflow="{k}"}} {v}\n'
        f'shuffle_workflow_duration_seconds_count{{workflow="{k}"}} {v}\n'
        f'shuffle_workflow_duration_seconds_sum{{workflow="{k}"}} 0'
        for k, v in wf_exec.items()
    )

    out = (
        "# HELP shuffle_workflow_executions_total Total workflow executions\n"
        "# TYPE shuffle_workflow_executions_total counter\n"
        f"{exec_lines}\n"
        "# HELP shuffle_workflow_failures_total Total workflow failures\n"
        "# TYPE shuffle_workflow_failures_total counter\n"
        f"shuffle_workflow_failures_total {wf_failures}\n"
        "# HELP shuffle_action_executions_total Total action executions\n"
        "# TYPE shuffle_action_executions_total counter\n"
        f"shuffle_action_executions_total {act_exec}\n"
        "# HELP shuffle_action_failures_total Total action failures\n"
        "# TYPE shuffle_action_failures_total counter\n"
        f"shuffle_action_failures_total {act_fail}\n"
        "# HELP shuffle_workflows_active Number of configured active workflows\n"
        "# TYPE shuffle_workflows_active gauge\n"
        f"shuffle_workflows_active {wf_active}\n"
        "# HELP shuffle_alerts_processed_total Total SOAR alerts processed\n"
        "# TYPE shuffle_alerts_processed_total counter\n"
        f"shuffle_alerts_processed_total {alerts}\n"
        "# HELP shuffle_up Whether Shuffle backend is reachable\n"
        "# TYPE shuffle_up gauge\n"
        f"shuffle_up {reachable}\n"
        "# HELP shuffle_exporter_last_scrape_timestamp Unix timestamp of last successful scrape\n"
        "# TYPE shuffle_exporter_last_scrape_timestamp gauge\n"
        f"shuffle_exporter_last_scrape_timestamp {last_updated}\n"
        "# HELP shuffle_workflow_duration_seconds Workflow execution duration histogram\n"
        "# TYPE shuffle_workflow_duration_seconds histogram\n"
        f"{hist_lines}\n"
    )
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/metrics"):
            body = format_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # Suppress noisy per-request logs, only log errors
        if args and str(args[1]) not in ("200", "404"):
            print(f"[HTTP] {fmt % args}")


if __name__ == "__main__":
    # Start polling thread immediately
    t = threading.Thread(target=update_loop, daemon=True)
    t.start()
    print(f"[Shuffle Exporter] Listening on 0.0.0.0:{PORT}")
    print(f"[Shuffle Exporter] Shuffle backend: {SHUFFLE_HOST}:{SHUFFLE_PORT}")
    print(f"[Shuffle Exporter] API key configured: {'yes' if SHUFFLE_KEY else 'NO'}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
