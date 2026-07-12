#!/bin/bash
# ================================================================
# Script install VictoriaLogs Grafana plugin OFFLINE
# Jalankan SEBELUM docker compose up
# ================================================================
set -e

PLUGIN_DIR="./grafana/plugins"
PLUGIN_NAME="victoriametrics-logs-datasource"
PLUGIN_VERSION="0.26.3"
PLUGIN_URL="https://github.com/VictoriaMetrics/victorialogs-datasource/releases/download/v${PLUGIN_VERSION}/${PLUGIN_NAME}-v${PLUGIN_VERSION}.zip"

mkdir -p "$PLUGIN_DIR"

echo "Downloading VictoriaLogs Grafana plugin v${PLUGIN_VERSION}..."
if curl -fL "$PLUGIN_URL" -o /tmp/victorialogs-plugin.zip; then
    echo "Extracting plugin..."
    unzip -o /tmp/victorialogs-plugin.zip -d "$PLUGIN_DIR/"
    rm /tmp/victorialogs-plugin.zip
    chmod -R 755 "$PLUGIN_DIR/"
    echo "Plugin installed: $PLUGIN_DIR/$PLUGIN_NAME"
    echo ""
    echo "Restart grafana container:"
    echo "  docker compose restart grafana"
    echo ""
    echo "Atau jika stack belum running:"
    echo "  docker compose up -d"
else
    echo "Download gagal!"
    echo "Jalankan stack tanpa plugin native - semua dashboard tetap bekerja via VictoriaLogs-Loki datasource"
fi
