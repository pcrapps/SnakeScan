# Feature: APRS Decode
*Branch: feat/aprs-decode*

## Goal
Decode APRS packets on 144.390 MHz. Display call signs, positions, and messages in the UI. Drop pins on a map.

## Approach
- Use `direwolf` (if installed) OR pure-Python `aprs` library as fallback
- Listen on 144.390000 Hz continuously in a background thread when `APRS_ENABLED=true`
- Parse APRS frames: extract callsign, lat/lon, symbol, comment, message
- Store last N packets in `ScannerState.aprs_log: list[dict]` (ring buffer, max 100)

## Backend
- New endpoint: `GET /api/aprs` — returns last N APRS packets as JSON
- SSE push when new packet arrives (reuse existing SSE pattern)
- New APRS capture thread: `rtl_fm -f 144.390M | direwolf -r 22050 -n 1 -b 16 -`
  - Falls back to `multimon-ng` if direwolf unavailable
  - Falls back to raw audio + `aprs` Python lib if neither available

## Frontend  
- New "APRS" tab or panel in the UI
- Live packet list: timestamp, callsign, position, comment
- Leaflet.js map (CDN) with markers for position packets
- Click marker → show full packet details

## Config
- `APRS_ENABLED`: bool, default False
- `APRS_FREQ_HZ`: int, default 144390000
- `APRS_LOG_SIZE`: int, default 100

## Dependencies
- `direwolf` (system package) — preferred
- `multimon-ng` (system package) — fallback
- `aprs>=1.1` (pip) — pure-Python last resort

## Commit message
`feat: add APRS decode — live packet display and map with Leaflet.js`
