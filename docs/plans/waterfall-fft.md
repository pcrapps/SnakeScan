# Feature: Live Waterfall FFT
*Branch: feat/waterfall-fft*

## Goal
Real-time spectrum + waterfall display in the browser UI. Click-to-tune on the waterfall.

## Backend
- New endpoint: `GET /api/fft` — returns FFT snapshot as JSON array (freq bins + power dB)
- Computed via `numpy.fft.rfft` on the most recent `rtl_power` or short `rtl_fm` capture
- Runs in background thread, result cached in `ScannerState.last_fft: dict | None`
- FFT refresh rate: every 1s (configurable via `FFT_INTERVAL_SECONDS` env var, default 1.0)
- Returns: `{"bins": [freq_hz...], "power_db": [float...], "timestamp": "..."}`

## Frontend
- New `<canvas>` element in the UI below the scan controls
- Waterfall: scrolling rows of colored pixels (power mapped to color — inferno palette)
- Spectrum: line chart above waterfall showing current FFT snapshot
- Click on canvas → POST `/api/set_freq` (or update scan priority) to that frequency
- Uses `requestAnimationFrame` loop polling `/api/fft` every 1s
- Peak markers: red dot + freq label on strongest signal

## Config
- `FFT_ENABLED`: bool, default True
- `FFT_INTERVAL_SECONDS`: float, default 1.0
- `FFT_BINS`: int, default 256

## Commit message
`feat: add live waterfall FFT spectrum display with click-to-tune`
