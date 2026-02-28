#!/bin/bash
# SnakeScan WiFi Hotspot Setup
# Configures hostapd + dnsmasq for captive-portal AP mode
# Run via setup_pi.sh --with-hotspot, or standalone: sudo bash hotspot_setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="/etc/snakescan"
PI_IP="192.168.4.1"

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: must run as root"
    exit 1
fi

# Read SSID from env file if available
SSID="SnakeScan"
if [ -f "$CONFIG_DIR/snakescan.env" ]; then
    source "$CONFIG_DIR/snakescan.env" 2>/dev/null || true
    SSID="${HOTSPOT_SSID:-SnakeScan}"
fi

echo "Configuring hotspot: SSID=$SSID"

# 1. Install hostapd config (apply SSID)
sed "s/^ssid=.*/ssid=$SSID/" "$SCRIPT_DIR/hostapd.conf" > /etc/hostapd/hostapd.conf
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd

# 2. Install dnsmasq config
cp "$SCRIPT_DIR/dnsmasq.conf" /etc/dnsmasq.d/snakescan.conf

# 3. Configure static IP for wlan0
if ! grep -q "interface wlan0" /etc/dhcpcd.conf 2>/dev/null; then
    cat >> /etc/dhcpcd.conf <<EOF

# SnakeScan hotspot
interface wlan0
    static ip_address=${PI_IP}/24
    nohook wpa_supplicant
EOF
fi

# 4. Enable and start services
systemctl unmask hostapd 2>/dev/null || true
systemctl enable hostapd dnsmasq
systemctl restart dhcpcd
systemctl restart hostapd dnsmasq

echo "Hotspot active: SSID=$SSID, IP=$PI_IP"
echo "Captive portal: all DNS resolves to $PI_IP -> SnakeScan UI"
