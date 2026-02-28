# Feature: Pi In-Car Deployment
*Branch: feat/pi-incar-deployment*

## Goal
Package SnakeScan for Raspberry Pi in-car use: WiFi hotspot, captive portal pointing to UI, systemd service, health endpoint, driving mode UI layout.

## Components

### 1. systemd service (`snakescan.service`)
- Auto-start on boot
- Watchdog restart if rtl_* fails
- EnvironmentFile for config
- Runs as dedicated user

### 2. Setup script (`setup_pi.sh`)
- Install deps: `rtl-sdr`, `python3-venv`, `hostapd`, `dnsmasq`
- Create venv, install requirements
- Install systemd service
- Configure hotspot (optional flag: `--with-hotspot`)

### 3. WiFi Hotspot config (`hotspot/`)
- `hostapd.conf` template — AP name `SnakeScan`, password configurable
- `dnsmasq.conf` template — DHCP + DNS redirect to Pi IP
- `hotspot_setup.sh` — applies config, enables services

### 4. Captive portal
- All DNS resolves to Pi IP
- HTTP redirect from any URL → SnakeScan UI at port 5000

### 5. Driving mode UI
- New URL route: `/drive` — minimal layout
- Large freq display, big HOLD button, muted color scheme
- No small controls — glove/thumb friendly
- Auto-redirects mobile browsers

### 6. Health endpoint
- `GET /api/health` — returns RTL-SDR status, scanner state, disk space, uptime
- Returns 503 if RTL-SDR not found

## Config
- `DRIVING_MODE`: bool — auto-enable minimal UI
- `HOTSPOT_SSID`: str, default `SnakeScan`

## Commit message  
`feat: Pi in-car deployment — systemd, hotspot, captive portal, driving mode UI`
