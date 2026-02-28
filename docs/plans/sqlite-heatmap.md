# Feature: SQLite Event Log + Heatmap
*Branch: feat/sqlite-heatmap*

## Goal
Persist every scanner hit to SQLite with GPS coordinates. Render a time×frequency heatmap and a geographic signal map.

## Database (`events.db`)
Schema:
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    freq_hz INTEGER NOT NULL,
    rms REAL NOT NULL,
    duration_s REAL,
    held INTEGER DEFAULT 0,
    gain INTEGER,
    ppm INTEGER,
    lat REAL,
    lon REAL,
    grid_square TEXT,
    ai_classification TEXT
);
```
- Written on every activity detection (active=True)
- SQLite chosen for zero-config, Pi-friendly, no server needed

## Backend
- New `db.py` module: `init_db()`, `log_event(event_dict)`, `query_events(filters)`
- Integrate into scanner loop — log on activity with current GPS if available
- New endpoints:
  - `GET /api/events?limit=100&freq=146940000&since=<iso>` — query events
  - `GET /api/heatmap/frequency` — time×freq heatmap data (2D array)
  - `GET /api/heatmap/geo` — GeoJSON FeatureCollection of hit locations
  - `GET /api/export/csv` — download all events as CSV

## Frontend
- New "History" tab in UI
  - Time×frequency heatmap: x=time buckets, y=freq, color=hit count (Canvas)
  - Click cell → filter event list to that freq/time bucket
- New "Map" tab
  - Leaflet.js map with circle markers sized by hit count
  - Color by frequency band
  - Tooltip: freq, count, last seen

## Config
- `DB_PATH`: str, default `./events.db`
- `DB_ENABLED`: bool, default True

## Dependencies
- `sqlite3` (stdlib — no extra install)
- Leaflet.js (CDN)

## Commit message
`feat: SQLite event log + frequency heatmap + geo signal map`
