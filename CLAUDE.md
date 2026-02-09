# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SnakeScan is a mobile-friendly web UI for Software Defined Radio (SDR) scanning of the 2m amateur radio band (144–148 MHz). It features real-time SSE-based updates, hold controls, optional browser GPS geotagging with Maidenhead grid squares, and quick bookmarks with notes — designed for eyes-off (in-car) use.

## Commands

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Run the app (recommended — auto-kills stale processes)
./start_scanner.sh              # serves on http://0.0.0.0:8080

# Run manually
python3 scanner_frontend.py

# Run simulator (no RTL-SDR hardware needed)
python3 simulate_scanner.py

# Run all tests (14 tests; no hardware required)
pytest -q

# Run a single test file
pytest test_frontend.py -v

# Run a single test
pytest test_frontend.py::test_hold_freezes_index -v
```

## Architecture

### Backend: `scanner_frontend.py`

Single-file Flask app (~390 lines) containing everything:

- **ScannerState** dataclass with a background `threading.Thread` that loops through 160 frequencies (144.000–147.975 MHz, 25 kHz steps). Uses `threading.Lock` for state, `threading.Event` for stop/kick signals.
- **REST API** endpoints under `/api/` (status, start, stop, toggle, hold, bookmark, bookmarks, geo, events).
- **SSE stream** at `/api/events` pushes status+activity events every 250ms; the frontend falls back to polling if SSE is unavailable.
- **GPS utilities**: `lat_lon_to_maidenhead()` converts coordinates to 6-char grid squares; `validate_gps_location()` filters by accuracy (≤100m).
- **CSV logging**: bookmarks.csv with auto-written headers, thread-safe via `_io_lock`.
- Activity detection uses `force_active_indices` (test hook); real RTL-SDR RMS thresholding is not yet wired in.

### Frontend: `web/index.html`

Self-contained single-page HTML/CSS/JS (no build step, no framework). Uses:
- `EventSource` for SSE with polling fallback
- `Web Speech API` for voice alerts (toggled via double-tap on frequency)
- `Geolocation API` for browser-based GPS
- CSS Grid with dark theme, mobile-first responsive layout

### Data Flow

1. Background thread advances through frequencies, dwells, detects activity, holds on active channels
2. UI receives updates via SSE (`/api/events`) or polls `/api/status` at 250ms
3. Browser GPS → `POST /api/geo` → server stores location + computes Maidenhead grid
4. Bookmark → server appends to `bookmarks.csv` (freq, timestamp, note, GPS fields)

## Branch & PR Workflow (Required)

Never commit directly to `main`. Create a feature branch per change (`feat/<topic>`, `fix/<topic>`, `docs/<topic>`), ensure `pytest -q` passes, push, and open a PR targeting `main`.

Commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.

## Coding Conventions

- Python 3.10+, 4-space indent, UTF-8
- snake_case functions/vars, PascalCase classes, UPPER_CASE constants
- Prefer standard library; minimal dependencies (Flask, NumPy, pytest)
- Don't commit generated CSV files or modify `sdrscan/` (local virtualenv)
- Tests use pytest; name files `test_*.py`; use Flask `app.test_client()`; prefer simulation over hardware; keep sleeps short to avoid flakes

## Key Files

| File | Role |
|---|---|
| `scanner_frontend.py` | Flask app, scanner loop, all API endpoints |
| `web/index.html` | Complete frontend (HTML+CSS+JS, no build) |
| `test_frontend.py` | Main test suite (11 tests: API, loop, GPS, bookmarks) |
| `simulate_scanner.py` | Simulated activity generator (no hardware) |
| `main.py` | Legacy CLI scanner using rtl_fm |
| `start_scanner.sh` | Process cleanup + startup wrapper |
| `requirements.txt` | Python deps: Flask, NumPy, pytest |
| `todo.md` | Roadmap and feature backlog |
