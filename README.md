# SnakeScan

Mobile‑friendly web UI for SDR scanning of the 2m ham band. Live updates via SSE, start/stop + hold controls, optional geotagging, and quick bookmarks (with notes) designed for eyes‑off use.

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
- Hold: freeze on current frequency for N seconds (default 3s).
- Bookmark: saves current frequency with timestamp (and optional note) to `bookmarks.csv`.
- Voice alerts: double‑tap the frequency readout to toggle speaking frequency/activity.
- Geotagging (optional): click the "Geo OFF" button to enable location from your browser (phone recommended for GPS). Bookmarks and status will include lat/lon.

Notes
- Bookmarks are appended to `bookmarks.csv` in the repo root.
- Live updates use Server‑Sent Events (SSE). If SSE is unavailable, the UI falls back to polling ~4×/sec.

## Tests
Run all tests (UI/API work without RTL‑SDR):
```
pytest -q
```

## Screenshots
Below are reference screenshots. Replace with your own captures as the UI evolves.

Main UI (running):
![Main UI](docs/screenshots/ui-main.png)

With geotagging enabled and hold active:
![Geo + Hold](docs/screenshots/ui-geo-hold.png)

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
- “Driving Mode” layout with larger controls; priority/lockout channels.
- Stream audio to the browser (WebRTC/Opus) and log activity with clips.
- Adaptive squelch and wideband pre‑scan to speed up hit detection.
- GPS tagging improvements and geofenced scan lists. See `todo.md`.

## Security
This uses Flask’s dev server for local/LAN use on port 8080. Do not expose it directly to the internet. Prefer a reverse proxy if remote access is needed.

## API Summary
- `GET /api/status` — current status (running, frequency/index, dwell, hold_remaining, optional location)
- `POST /api/start` — start scanning; body: `{ dwell_seconds? }`
- `POST /api/stop` — stop scanning
- `POST /api/toggle` — toggle running state
- `POST /api/hold` — hold on current freq; body: `{ seconds }`
- `GET /api/events` — SSE stream of status/activity events
- `POST /api/geo` — set last known location; body: `{ lat, lon, accuracy?, speed?, heading? }`
- `POST /api/bookmark` — save current freq; body: `{ note?, location? }`
- `GET /api/bookmarks` — list saved bookmarks
