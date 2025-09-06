# SnakeScan TODO

A focused backlog to evolve SnakeScan into a safe, mobile, in‑car SDR scanner (starting with 2m band) that you can operate eyes‑off.

## Short Term
- Wire backend to real RTL‑SDR scanning engine (RMS, squelch, HOLD)
- Speak only on activity: “Active 146.940 megahertz, holding”
- Big, glove‑friendly controls: Start/Pause, Hold, Priority star
- Bookmark enhancements: tags/notes, quick undo, CSV/JSON export
- SSE/WebSocket status events (replace polling)
- requirements.txt and systemd unit for auto‑start

## Scanner Engine
- Adaptive squelch: rolling noise floor per channel/segment
- Priority + lockout lists; memory banks (repeaters/simplex)
- Band presets + step sizes (2m/70cm/airband/weather)
- HOLD behavior: configurable hang‑time and resume strategy
- PPM auto‑calibration using NOAA 162.55 MHz or known repeaters
- Gain strategy: manual/AGC off; probe multiple gains on suspected hits
- NFM and de‑emphasis options; tone decode (CTCSS/DCS) for repeaters

## Web UI/UX
- Live spectrum/waterfall (FFT) with peak markers; click‑to‑tune
- Audio streaming to browser (WebRTC/Opus or chunked WAV)
- Events pane: recent hits with duration, RMS, play snippet, Bookmark
- Voice alerts toggle control + activity‑specific phrases
- Preset selector, dwell slider, step size, gain/squelch controls
- “Driving mode” layout: minimal info, large buttons, dark high‑contrast

## Data & Persistence
- SQLite event log (timestamp, freq, RMS, duration, HOLD, gain, PPM)
- GPS integration (gpsd) to geotag events and bookmarks
- Geofenced scan lists that switch based on location
- Export: CSV for logs, KML/GeoJSON for mapping, audio clip bundling
- Bookmark manager page with search/filter and quick export

## Mobility & Ops
- Raspberry Pi in‑car deployment
  - Host Wi‑Fi AP + captive portal to UI
  - systemd service; watchdog restart if rtl_* fails
  - Health endpoint showing device state and actionable errors
- Simulation fallback when hardware absent (auto‑enable, clear UI banner)
- Log rotation for events/audio, disk‑space guardrails

## Performance
- Wideband pre‑scan (rtl_power) to find hot bins quickly
- Retune optimization: scan within tuner span before shifting center
- Smart dwell: shorter on quiet channels, longer near activity spikes

## Packaging
- requirements.txt and pinned versions
- Optional Dockerfile for x86/arm builds
- Simple setup docs for macOS/Linux/Raspberry Pi

## Testing
- Unit: engine state, adaptive squelch thresholds, priority/lockout logic
- API: SSE/WebSocket stream, bookmarks CRUD, health checks
- Integration: simulated hits → HOLD → audio stream/voice alert
- GPS mocking for geotagging
- Performance tests on Pi (latency, CPU, audio underruns)

## Nice‑to‑Have
- Heatmap of activity (time × frequency); click to tune
- Repeater directory integration (import from RepeaterBook or CSV)
- Basic talkgroup/tone identification display
