#!/usr/bin/env bash
# Ganti "otak" model DTIClaw. Yang diedit hanyalah field model di
#   .dticlaw-state/openclaw.json  ->  agents.defaults.model + agents.list[].model.primary
#
# Usage:
#   bash scripts/switch-model.sh qwen       # LOKAL: qwen2.5 (custom dticlaw-qwen, tool-calling)
#   bash scripts/switch-model.sh gemma2     # LOKAL: gemma2 (custom dticlaw-gemma, completion-only)
#   bash scripts/switch-model.sh deepseek   # CLOUD: deepseek-v4-pro:cloud (tool-calling, butuh Ollama Cloud)
#   bash scripts/switch-model.sh gemini     # CLOUD: gemini-3-flash-preview:cloud
#   bash scripts/switch-model.sh <model-id> # bebas, mis. qwen2.5:14b-instruct atau llama3.1:8b
#
# Catatan:
#   - Model LOKAL "dticlaw-*" dibuat dari Modelfile di .dticlaw-state/ollama/ (atur num_ctx/temperature di sana).
#   - Model CLOUD "*:cloud" perlu login Ollama Cloud (API key) di dalam container: `ollama signin`.
#   - Provider Ollama didaftarkan via env OLLAMA_API_KEY di scripts/dticlaw-service.sh.
set -euo pipefail

DTICLAW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$DTICLAW_DIR/.dticlaw-state/openclaw.json"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

set_model() {  # $1 = full model id (mis. "ollama/dticlaw-qwen")
  python3 - "$CONFIG" "$1" <<'PY'
import json, sys
cfg_path, model = sys.argv[1], sys.argv[2]
cfg = json.load(open(cfg_path))
cfg["agents"]["defaults"]["model"] = model
for a in cfg["agents"]["list"]:
    a["model"] = {"primary": model}
json.dump(cfg, open(cfg_path, "w"), indent=2, ensure_ascii=False)
print("  config.model =", model)
PY
}

restart() {
  echo "→ Restart layanan ..."
  bash "$DTICLAW_DIR/scripts/dticlaw-service.sh" restart >/dev/null 2>&1 || true
  sleep 8
  bash "$DTICLAW_DIR/scripts/dticlaw-service.sh" status
}

target="${1:-}"
case "$target" in
  qwen|gemma2)
    if [ "$target" = qwen ]; then base="qwen2.5:7b-instruct"; custom="dticlaw-qwen"; mf="Modelfile.dticlaw-qwen"
    else base="gemma2:9b"; custom="dticlaw-gemma"; mf="Modelfile.dticlaw"; fi
    grep -q "^FROM " "$DTICLAW_DIR/.dticlaw-state/ollama/$mf" && base="$(awk '/^FROM /{print $2}' "$DTICLAW_DIR/.dticlaw-state/ollama/$mf")"
    if ! ollama list 2>/dev/null | grep -q "${base%%:*}"; then
      echo "✗ Model dasar '$base' belum ada. Jalankan: ollama pull $base"; exit 1
    fi
    echo "→ Membuat model kustom LOKAL '$custom' dari $base ..."
    ollama create "$custom" -f "$DTICLAW_DIR/.dticlaw-state/ollama/$mf" >/dev/null
    set_model "ollama/$custom"; restart; echo "✅ Aktif (LOKAL): ollama/$custom" ;;
  deepseek)
    set_model "ollama/deepseek-v4-pro:cloud"; restart; echo "✅ Aktif (CLOUD): deepseek-v4-pro:cloud" ;;
  gemini)
    set_model "ollama/gemini-3-flash-preview:cloud"; restart; echo "✅ Aktif (CLOUD): gemini-3-flash-preview:cloud" ;;
  "")
    echo "Usage: $0 {qwen|gemma2|deepseek|gemini|<ollama-model-id>}"; exit 1 ;;
  *)
    # Model id bebas (lokal/cloud). Tidak membuat model kustom.
    if ! ollama list 2>/dev/null | grep -q "${target%%:*}"; then
      echo "⚠️ '$target' belum ada di ollama list. Pastikan sudah di-pull / login cloud."
    fi
    set_model "ollama/$target"; restart; echo "✅ Aktif: ollama/$target" ;;
esac
