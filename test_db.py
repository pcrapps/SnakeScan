#!/usr/bin/env python3
"""Tests for db.py module and new API endpoints."""
import os
import time

import db
import scanner_frontend as sf

# Disable RTL-SDR hardware for all tests
sf.state._rtl_available = False


# ---- db.py unit tests ----

def test_init_db_creates_table(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()
    assert os.path.exists(db_file)
    # Verify table exists by querying
    rows = db.query_events(limit=10)
    assert rows == []
    db.close()


def test_log_event_and_query(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    row_id = db.log_event({
        "timestamp": "2025-01-15T12:00:00+00:00",
        "freq_hz": 146520000,
        "rms": 0.042,
        "held": 1,
        "gain": 25,
        "ppm": 0,
        "lat": 37.7749,
        "lon": -122.4194,
        "grid_square": "CM87ss",
    })
    assert row_id is not None and row_id > 0

    rows = db.query_events(limit=10)
    assert len(rows) == 1
    assert rows[0]["freq_hz"] == 146520000
    assert rows[0]["rms"] == 0.042
    assert rows[0]["lat"] == 37.7749
    assert rows[0]["grid_square"] == "CM87ss"
    db.close()


def test_query_events_filter_by_freq(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"freq_hz": 146520000, "rms": 0.01})
    db.log_event({"freq_hz": 146940000, "rms": 0.02})
    db.log_event({"freq_hz": 146520000, "rms": 0.03})

    rows = db.query_events(freq_hz=146520000)
    assert len(rows) == 2
    assert all(r["freq_hz"] == 146520000 for r in rows)

    rows2 = db.query_events(freq_hz=146940000)
    assert len(rows2) == 1
    db.close()


def test_query_events_filter_by_since(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"timestamp": "2025-01-01T00:00:00+00:00", "freq_hz": 144000000, "rms": 0.01})
    db.log_event({"timestamp": "2025-06-01T00:00:00+00:00", "freq_hz": 145000000, "rms": 0.02})

    rows = db.query_events(since="2025-03-01T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["freq_hz"] == 145000000
    db.close()


def test_query_events_limit(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    for i in range(10):
        db.log_event({"freq_hz": 144000000 + i * 25000, "rms": 0.01})

    rows = db.query_events(limit=3)
    assert len(rows) == 3
    db.close()


def test_db_disabled(tmp_path):
    db_file = str(tmp_path / "disabled.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = False
    db.close()

    db.init_db()
    assert not os.path.exists(db_file)

    result = db.log_event({"freq_hz": 146520000, "rms": 0.01})
    assert result is None

    rows = db.query_events()
    assert rows == []

    # Restore
    db.DB_ENABLED = True


def test_heatmap_frequency(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"timestamp": "2025-01-15T12:00:00+00:00", "freq_hz": 146520000, "rms": 0.01})
    db.log_event({"timestamp": "2025-01-15T12:05:00+00:00", "freq_hz": 146520000, "rms": 0.02})
    db.log_event({"timestamp": "2025-01-15T12:30:00+00:00", "freq_hz": 146940000, "rms": 0.03})

    data = db.heatmap_frequency()
    assert "buckets" in data
    assert "freqs" in data
    assert "counts" in data
    assert len(data["freqs"]) == 2
    assert 146520000 in data["freqs"]
    assert 146940000 in data["freqs"]
    db.close()


def test_heatmap_geo(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({
        "freq_hz": 146520000, "rms": 0.01,
        "lat": 37.7749, "lon": -122.4194, "grid_square": "CM87ss",
    })
    db.log_event({
        "freq_hz": 146520000, "rms": 0.02,
        "lat": 37.7749, "lon": -122.4194, "grid_square": "CM87ss",
    })

    geo = db.heatmap_geo()
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == 1
    f = geo["features"][0]
    assert f["properties"]["count"] == 2
    assert f["properties"]["freq_hz"] == 146520000
    assert f["geometry"]["coordinates"] == [-122.4194, 37.7749]
    db.close()


def test_export_csv_rows(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"freq_hz": 146520000, "rms": 0.01})
    db.log_event({"freq_hz": 146940000, "rms": 0.02})

    rows = db.export_csv_rows()
    assert len(rows) == 2
    assert rows[0]["freq_hz"] == 146520000
    assert rows[1]["freq_hz"] == 146940000
    db.close()


# ---- API endpoint tests ----

def test_api_events_query(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"timestamp": "2025-01-15T12:00:00+00:00", "freq_hz": 146520000, "rms": 0.01})
    db.log_event({"timestamp": "2025-01-15T12:05:00+00:00", "freq_hz": 146940000, "rms": 0.02})

    client = sf.app.test_client()
    resp = client.get('/api/events?limit=10')
    assert resp.status_code == 200
    data = resp.get_json()
    assert "events" in data
    assert len(data["events"]) == 2

    # Filter by freq
    resp2 = client.get('/api/events?freq=146520000')
    data2 = resp2.get_json()
    assert len(data2["events"]) == 1
    assert data2["events"][0]["freq_hz"] == 146520000

    # Filter by since
    resp3 = client.get('/api/events?since=2025-01-15T12:03:00%2B00:00')
    data3 = resp3.get_json()
    assert len(data3["events"]) == 1
    db.close()


def test_api_heatmap_frequency(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"timestamp": "2025-01-15T12:00:00+00:00", "freq_hz": 146520000, "rms": 0.01})

    client = sf.app.test_client()
    resp = client.get('/api/heatmap/frequency')
    assert resp.status_code == 200
    data = resp.get_json()
    assert "buckets" in data
    assert "freqs" in data
    assert "counts" in data
    db.close()


def test_api_heatmap_geo(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({
        "freq_hz": 146520000, "rms": 0.01,
        "lat": 37.7749, "lon": -122.4194, "grid_square": "CM87ss",
    })

    client = sf.app.test_client()
    resp = client.get('/api/heatmap/geo')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    db.close()


def test_api_export_csv(tmp_path):
    db_file = str(tmp_path / "test.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    db.log_event({"freq_hz": 146520000, "rms": 0.01})

    client = sf.app.test_client()
    resp = client.get('/api/export/csv')
    assert resp.status_code == 200
    assert resp.content_type == 'text/csv; charset=utf-8'
    body = resp.data.decode()
    assert 'freq_hz' in body
    assert '146520000' in body
    db.close()


def test_api_export_csv_empty(tmp_path):
    db_file = str(tmp_path / "empty.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    client = sf.app.test_client()
    resp = client.get('/api/export/csv')
    assert resp.status_code == 200
    db.close()


def test_scanner_logs_to_db(tmp_path):
    """When force_active_indices triggers a hit, event is logged to SQLite."""
    db_file = str(tmp_path / "scanner.db")
    db.DB_PATH = db_file
    db.DB_ENABLED = True
    db.close()
    db.init_db()

    sf.state.stop()
    sf.state.hold_seconds = 0.0
    sf.state._hold_until_ts = 0.0
    sf.state.current_index = 0
    # Use a wide range of active indices so the scanner hits one regardless of
    # where it starts scanning from (avoids race condition).
    active_set = set(range(0, 20))
    sf.state.force_active_indices = active_set

    client = sf.app.test_client()
    client.post('/api/start', json={'dwell_seconds': 0.03})
    time.sleep(0.3)
    client.post('/api/stop')
    sf.state.force_active_indices = set()

    rows = db.query_events(limit=100)
    assert len(rows) >= 1
    assert rows[0]["rms"] > 0
    db.close()
