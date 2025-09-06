# SnakeScan

Minimal web UI for mobile SDR scanning of the 2m ham band. Shows the currently scanned frequency, lets you Start/Stop, and bookmark interesting frequencies for later review. Voice alerts are available for eyes‑off operation.

## Quick Start
1) Install Python deps
```
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
```

2) Run the frontend
```
python3 scanner_frontend.py
```
The server listens on `http://0.0.0.0:8080` (open from the same device: `http://localhost:8080`).

## Using the UI
- Start: begins looping 144–148 MHz in 25 kHz steps.
- Stop: pauses scanning (index/frequency stays put).
- Bookmark: saves the current frequency with a UTC timestamp to `bookmarks.csv`.
- Voice alerts: double‑tap the frequency readout to toggle; the browser will speak the current frequency as it changes.
 - Geotagging (optional): click the "Geo OFF" button to enable location from your browser (phone recommended for GPS). Bookmarks and status will include lat/lon.

Notes
- Bookmarks are appended to `bookmarks.csv` in the repo root.
- Basic status polling updates about 4×/sec.

## Tests
Run all tests (UI/API work without RTL‑SDR):
```
pytest -q
```

## Optional Scripts
- Simulated activity (no hardware):
```
python3 simulate_scanner.py
```
- Legacy CLI scanner (RTL‑SDR + `rtl_fm` required):
```
python3 main.py
```

## Next Steps (Roadmap)
- Integrate real RTL‑SDR scanning (RMS, squelch, HOLD) into the web backend.
- Stream audio to browser; add “Driving Mode” layout and priority/lockout.
- GPS tagging and geofenced scan lists. See `todo.md` for details.

## Security
This uses Flask’s dev server for local/LAN use. Do not expose it directly to the internet. For in‑car setups (e.g., Raspberry Pi), run behind a reverse proxy and/or a systemd unit.
