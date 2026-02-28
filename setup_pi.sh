#!/bin/bash
# SnakeScan Raspberry Pi Setup Script
# Usage: sudo ./setup_pi.sh [--with-hotspot]
set -euo pipefail

INSTALL_DIR="/opt/snakescan"
CONFIG_DIR="/etc/snakescan"
SERVICE_USER="snakescan"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WITH_HOTSPOT=false

for arg in "$@"; do
    case "$arg" in
        --with-hotspot) WITH_HOTSPOT=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: must run as root (sudo ./setup_pi.sh)"
    exit 1
fi

echo "=== SnakeScan Pi Setup ==="

# 1. Install system dependencies
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq rtl-sdr python3-venv python3-pip

if [ "$WITH_HOTSPOT" = true ]; then
    apt-get install -y -qq hostapd dnsmasq
fi

# 2. Create service user
echo "[2/6] Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
# Grant RTL-SDR device access
usermod -aG plugdev "$SERVICE_USER" 2>/dev/null || true

# 3. Install application
echo "[3/6] Installing SnakeScan to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR"/scanner_frontend.py "$INSTALL_DIR/"
cp "$SCRIPT_DIR"/simulate_scanner.py "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR"/requirements.txt "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/web "$INSTALL_DIR/"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

# 4. Create venv and install dependencies
echo "[4/6] Setting up Python venv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# 5. Install config and systemd service
echo "[5/6] Installing systemd service..."
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/snakescan.env" ]; then
    cp "$SCRIPT_DIR/snakescan.env" "$CONFIG_DIR/snakescan.env"
fi
cp "$SCRIPT_DIR/snakescan.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable snakescan.service

# 6. Optional hotspot setup
if [ "$WITH_HOTSPOT" = true ]; then
    echo "[6/6] Configuring WiFi hotspot..."
    bash "$SCRIPT_DIR/hotspot/hotspot_setup.sh"
else
    echo "[6/6] Skipping hotspot (use --with-hotspot to enable)"
fi

echo ""
echo "=== Setup complete ==="
echo "Start with: sudo systemctl start snakescan"
echo "Logs:       journalctl -u snakescan -f"
echo "UI:         http://<pi-ip>:8080"
