# DTIClaw — Quick Start

## 🚀 Run DTIClaw Locally

### Option 1: Using the startup script (Recommended)

```bash
cd Agentic/dticlaw
bash start-dev.sh
```

Output:
```
📦 Starting DTIClaw...
✅ DTIClaw is running!
📍 Web Interface: http://127.0.0.1:3737
🔌 Gateway API: http://127.0.0.1:18789 (dev mode)
```

### Option 2: Manual startup

Terminal 1 (Gateway):
```bash
cd Agentic/dticlaw
node openclaw.mjs --dev gateway run --allow-unconfigured
```

Terminal 2 (Dashboard):
```bash
cd Agentic/dticlaw
DTICLAW_GATEWAY_PORT=18789 node scripts/dashboard-server.mjs
```

## 🌐 Access Web Interface

Open your browser to: **http://127.0.0.1:3737**

## ⚙️ Troubleshooting

### "Failed to Load Page" / Connection Refused

**Problem:** Dashboard shows error but interface is unreachable.

**Solution:** Make sure both services are running:
```bash
# Check if both are listening
ss -ltnp | grep -E ':(18789|3737)'

# If gateway not showing, check logs
tail -50 /tmp/dticlaw-logs/gateway.log

# If dashboard not showing, check logs
tail -20 /tmp/dticlaw-logs/dashboard.log
```

### Gateway port conflict

If you get "port already in use" error:

```bash
# Kill any existing processes
pkill -f 'node.*openclaw'
pkill -f 'node.*dashboard'

# Wait and retry
sleep 2
bash start-dev.sh
```

### pnpm or npm hangs/freezes

**Problem:** Running `pnpm install` or `pnpm build` causes system freeze.

**Solution:** Use Node directly without package managers for development:
- Use `node openclaw.mjs` to run (already configured in `start-dev.sh`)
- Don't run `pnpm build` unless rebuilding UI
- If you need to rebuild UI: `node scripts/tsdown-build.mjs`

For one-time builds during dev, prefer incremental scripts over full `pnpm build`.

## 📋 Service Details

| Service | Port | Purpose |
|---------|------|---------|
| Gateway | 18789 | OpenClaw agent runtime & API |
| Dashboard | 3737 | Control UI (web interface) |

## ⏹️ Stop Services

```bash
# Kill using script info
kill 16342 16363  # (use PID from start-dev.sh output)

# Or kill all at once
pkill -f 'node.*openclaw\|node.*dashboard'
```

## 📚 Logs

- Gateway log: `/tmp/dticlaw-logs/gateway.log`
- Dashboard log: `/tmp/dticlaw-logs/dashboard.log`

View live:
```bash
tail -f /tmp/dticlaw-logs/gateway.log
tail -f /tmp/dticlaw-logs/dashboard.log
```

## 🔑 Configuration

Default dev config uses:
- Isolated state: `~/.openclaw-dev/`
- Workspace: `~/.openclaw/workspace-dev`
- Auto-generated auth token (changes on restart)

To persist config:
```bash
node openclaw.mjs config set gateway.auth.mode token
node openclaw.mjs config set gateway.auth.token <your-token>
```

## 🛠️ Common Commands

```bash
# Check gateway health
curl http://127.0.0.1:18789/healthz

# View gateway status
node openclaw.mjs status

# Setup credentials
node openclaw.mjs configure

# Run one agent turn
node openclaw.mjs agent --message "Your message here"
```

---

**Ready?** Open http://127.0.0.1:3737 in your browser!
