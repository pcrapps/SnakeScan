"""SQLite event log for SnakeScan.

Uses stdlib sqlite3 only — no extra dependencies.

Config (module-level):
    DB_PATH   – path to SQLite file (default ./events.db)
    DB_ENABLED – set False to disable all writes (default True)
"""

import sqlite3
import threading
import datetime as _dt

DB_PATH: str = "./events.db"
DB_ENABLED: bool = True

_local = threading.local()

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS events (
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
"""


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local connection (created lazily)."""
    conn = getattr(_local, "conn", None)
    path = getattr(_local, "path", None)
    if conn is None or path != DB_PATH:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
        _local.path = DB_PATH
    return conn


def init_db() -> None:
    """Create the events table if it doesn't exist."""
    if not DB_ENABLED:
        return
    conn = _get_conn()
    conn.executescript(_SCHEMA)


def log_event(event: dict) -> int | None:
    """Insert one event row. Returns the row id, or None if disabled."""
    if not DB_ENABLED:
        return None
    conn = _get_conn()
    ts = event.get("timestamp") or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO events (timestamp, freq_hz, rms, duration_s, held, gain, ppm, lat, lon, grid_square, ai_classification)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ts,
            int(event.get("freq_hz", 0)),
            float(event.get("rms", 0.0)),
            event.get("duration_s"),
            int(event.get("held", 0)),
            event.get("gain"),
            event.get("ppm"),
            event.get("lat"),
            event.get("lon"),
            event.get("grid_square"),
            event.get("ai_classification"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def query_events(*, limit: int = 100, freq_hz: int | None = None,
                 since: str | None = None) -> list[dict]:
    """Query events with optional filters. Returns list of dicts."""
    if not DB_ENABLED:
        return []
    conn = _get_conn()
    clauses: list[str] = []
    params: list = []
    if freq_hz is not None:
        clauses.append("freq_hz = ?")
        params.append(freq_hz)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM events{where} ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def heatmap_frequency(*, since: str | None = None,
                      bucket_minutes: int = 15) -> dict:
    """Return time×frequency heatmap data.

    Returns {buckets: [...], freqs: [...], counts: [[...]]}
    where counts[freq_idx][bucket_idx] = hit count.
    """
    if not DB_ENABLED:
        return {"buckets": [], "freqs": [], "counts": []}
    conn = _get_conn()
    params: list = []
    where = ""
    if since:
        where = " WHERE timestamp >= ?"
        params.append(since)
    rows = conn.execute(
        f"SELECT timestamp, freq_hz FROM events{where} ORDER BY timestamp",
        params,
    ).fetchall()
    if not rows:
        return {"buckets": [], "freqs": [], "counts": []}

    # Build time buckets and freq set
    freq_set: set[int] = set()
    parsed: list[tuple[_dt.datetime, int]] = []
    for r in rows:
        try:
            ts = _dt.datetime.fromisoformat(r["timestamp"])
        except (ValueError, TypeError):
            continue
        freq_set.add(r["freq_hz"])
        parsed.append((ts, r["freq_hz"]))

    if not parsed:
        return {"buckets": [], "freqs": [], "counts": []}

    freqs_sorted = sorted(freq_set)
    freq_idx = {f: i for i, f in enumerate(freqs_sorted)}

    t_min = parsed[0][0]
    t_max = parsed[-1][0]
    delta = _dt.timedelta(minutes=bucket_minutes)

    # Build bucket labels
    buckets: list[str] = []
    cur = t_min.replace(second=0, microsecond=0)
    cur = cur - _dt.timedelta(minutes=cur.minute % bucket_minutes)
    while cur <= t_max + delta:
        buckets.append(cur.isoformat(timespec="minutes"))
        cur += delta

    counts = [[0] * len(buckets) for _ in freqs_sorted]
    bucket_start = _dt.datetime.fromisoformat(buckets[0])
    for ts, fhz in parsed:
        bi = int((ts - bucket_start).total_seconds() / (bucket_minutes * 60))
        bi = max(0, min(bi, len(buckets) - 1))
        fi = freq_idx[fhz]
        counts[fi][bi] += 1

    return {
        "buckets": buckets,
        "freqs": freqs_sorted,
        "counts": counts,
    }


def heatmap_geo() -> dict:
    """Return GeoJSON FeatureCollection of hit locations aggregated by freq+grid."""
    if not DB_ENABLED:
        return {"type": "FeatureCollection", "features": []}
    conn = _get_conn()
    rows = conn.execute(
        "SELECT freq_hz, lat, lon, grid_square, COUNT(*) as cnt, MAX(timestamp) as last_seen"
        " FROM events WHERE lat IS NOT NULL AND lon IS NOT NULL"
        " GROUP BY freq_hz, grid_square"
    ).fetchall()
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["lon"], r["lat"]],
            },
            "properties": {
                "freq_hz": r["freq_hz"],
                "count": r["cnt"],
                "last_seen": r["last_seen"],
                "grid_square": r["grid_square"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def export_csv_rows() -> list[dict]:
    """Return all events as list of dicts for CSV export."""
    if not DB_ENABLED:
        return []
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def close() -> None:
    """Close the thread-local connection if open."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
        _local.path = None
