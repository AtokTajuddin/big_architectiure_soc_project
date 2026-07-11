---
name: dticlaw-guardian
description: "Permission gate, behavioral drift detection, anti-hallucination guard, and audit trail for agent actions. Use for security enforcement."
metadata: { "openclaw": { "emoji": "🛡️" } }
allowed-tools: ["write", "read", "exec", "memory_search"]
user-invocable: true
---

# DTIClaw Guardian

Security guardian engine: permission enforcement, hallucination detection, behavioral monitoring.

## Permission Model (P0–P3)

| Level | Description | Action |
|-------|-------------|--------|
| **P0: Free** | Safe reads, queries, file reads | ✅ Auto-approved |
| **P1: Confirm** | Non-destructive writes, file creation | 📝 Log + execute |
| **P2: Ask** | System changes, installs, network | ⚠️ User must approve |
| **P3: Block** | Destructive ops, self-modification | 🚫 Never allowed |

## P3 — Hard Block (Never Execute)

- `rm -rf`, `mkfs`, `dd if=`, `shred`, `wipefs`
- `chmod 777`, `chmod -R 777`
- Self-modification: edit AGENTS.md, SOUL.md, IDENTITY.md, MEMORY.md
- Curl-to-bash, wget-to-shell
- Reverse shells, C2 beacons
- Permission bypass attempts

## P2 — Needs Approval

- `apt/pip/npm install`
- `systemctl`, `crontab`
- `ufw`, `iptables`, firewall changes
- Bind to `0.0.0.0` (instead of `127.0.0.1`)
- Docker operations
- External sending (email, API to 3rd party)

## P1 — Confirm & Log

- File writes, edits, creates
- `mv`, `cp`, `touch`, `mkdir`
- Git commits, pushes
- Code generation

## Hallucination Detection

Monitor output for fabrication markers:
- ❌ "According to my knowledge..." (no knowledge, only search)
- ❌ "Studies show..." tanpa citation
- ❌ Precise numbers tanpa sumber
- ❌ Future predictions stated as facts
- ✅ "Based on search results from [source]..."
- ✅ "Gue gak yakin, tapi sepertinya..."
- ✅ "Mau gue research lebih dalam?"

## Behavioral Drift Alerts

- Tool call pattern deviation >50% → alert
- Response length spike >3x average → alert
- Uncertainty marker drop >50% → alert
- Self-modification attempt → BLOCK + alert

## Audit Trail

```bash
# Check audit log
cat ~/dticlaw/logs/audit.log

# Search for specific action
grep "EXEC:" ~/dticlaw/logs/audit.log
```

## Integrity Check

```bash
# Verify core config files haven't been modified
python3 skills/dticlaw-guardian/scripts/integrity_check.py
```
