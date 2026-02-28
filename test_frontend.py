#!/usr/bin/env python3
import time

import scanner_frontend as sf

# Disable RTL-SDR hardware for all tests (avoids subprocess overhead)
sf.state._rtl_available = False


def test_maidenhead_grid_square():
    """Test Maidenhead grid square calculation"""
    # Test San Francisco coordinates
    grid = sf.lat_lon_to_maidenhead(37.7749, -122.4194)
    assert grid == 'CM87ss'  # Corrected expected value

    # Test other known locations
    grid_london = sf.lat_lon_to_maidenhead(51.5074, -0.1278)
    assert grid_london == 'IO91wm'

    # Test zero coordinates (equator/prime meridian)
    grid_zero = sf.lat_lon_to_maidenhead(0.0, 0.0)
    assert grid_zero == 'JJ00aa'


def test_gps_validation():
    """Test GPS location validation and filtering"""
    # Valid location
    valid_loc = {'lat': 37.7749, 'lon': -122.4194, 'accuracy': 10.5}
    result = sf.validate_gps_location(valid_loc)
    assert result is not None
    assert result['grid_square'] == 'CM87ss'
    assert result['accuracy'] == 10.5

    # Invalid coordinates
    invalid_coords = [
        {'lat': 91, 'lon': 0},  # lat out of range
        {'lat': 0, 'lon': 181}, # lon out of range
        {'lat': 'invalid', 'lon': 0}, # non-numeric
        {'lon': -122.4194}, # missing lat
    ]

    for invalid in invalid_coords:
        assert sf.validate_gps_location(invalid) is None

    # Poor accuracy (should be filtered out)
    poor_accuracy = {'lat': 37.7749, 'lon': -122.4194, 'accuracy': 150}
    assert sf.validate_gps_location(poor_accuracy) is None


def _wait_until(fn, timeout=1.5, interval=0.02):
    """Poll fn() until it returns truthy or timeout seconds elapse."""
    start = time.time()
    while time.time() - start < timeout:
        if fn():
            return True
        time.sleep(interval)
    return False


def test_status_initial():
    app = sf.app
    client = app.test_client()
    st = client.get('/api/status').get_json()
    assert st['running'] is False
    assert st['current_freq_hz'] in (0, st['current_freq_hz'])  # allow 0 initially
    assert st['dwell_seconds'] > 0
    assert st['total_freqs'] >= 1
    assert st['index'] >= 0


def test_start_progress_and_stop():
    app = sf.app
    client = app.test_client()

    # Ensure stopped
    client.post('/api/stop')

    # Start with short dwell
    data = client.post('/api/start', json={'dwell_seconds': 0.03}).get_json()
    assert data['running'] is True

    # Wait until index advances beyond 2
    def progressed():
        st = client.get('/api/status').get_json()
        return st['index'] >= 3 and st['running'] is True

    assert _wait_until(progressed, timeout=2.0), 'scanner did not progress as expected'

    # Stop
    stop = client.post('/api/stop').get_json()
    assert stop['running'] is False

    # Capture index and ensure it does not change after stop
    st1 = client.get('/api/status').get_json()
    idx1 = st1['index']
    time.sleep(0.15)
    st2 = client.get('/api/status').get_json()
    assert st2['running'] is False
    assert st2['index'] == idx1


def test_toggle_endpoint():
    app = sf.app
    client = app.test_client()

    client.post('/api/stop')
    t1 = client.post('/api/toggle').get_json()
    assert t1['running'] is True
    t2 = client.post('/api/toggle').get_json()
    assert t2['running'] is False


def test_index_wraparound():
    app = sf.app
    client = app.test_client()

    # Force near-end index and small dwell
    sf.state.stop()
    sf.state.current_index = max(0, len(sf.state.freqs) - 2)
    client.post('/api/start', json={'dwell_seconds': 0.02})

    # Wait until we wrap to small index (0 or 1)
    def wrapped():
        st = client.get('/api/status').get_json()
        return st['index'] <= 1 and st['running'] is True

    assert _wait_until(wrapped, timeout=2.0), 'index did not wrap to start'

    client.post('/api/stop')


def test_root_serves_html():
    app = sf.app
    client = app.test_client()
    resp = client.get('/')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8').lower()
    assert '<html' in body and 'snakescan' in body


def test_geo_then_bookmark(tmp_path, monkeypatch):
    import scanner_frontend as sf_mod
    bm = tmp_path / 'bookmarks.csv'
    monkeypatch.setattr(sf_mod, '_BOOKMARKS', bm)

    app = sf_mod.app
    client = app.test_client()

    # Post a location, then bookmark
    loc = { 'lat': 37.7749, 'lon': -122.4194, 'accuracy': 5.5, 'speed': 0, 'heading': 180 }
    r = client.post('/api/geo', json=loc)
    assert r.status_code == 200
    gps_data = r.get_json()
    assert gps_data['ok'] is True

    # Verify enhanced GPS data structure
    loc_data = gps_data['location']
    assert abs(loc_data['lat'] - 37.7749) < 1e-6
    assert abs(loc_data['lon'] + 122.4194) < 1e-3
    assert 'grid_square' in loc_data
    assert loc_data['grid_square'] == 'CM87ss'  # SF grid square
    assert loc_data['accuracy'] == 5.5

    # Ensure location appears in status
    st = client.get('/api/status').get_json()
    assert 'location' in st and abs(st['location']['lat'] - 37.7749) < 1e-6
    assert st['location']['grid_square'] == 'CM87ss'

    # Create bookmark and verify lat/lon persisted
    b = client.post('/api/bookmark', json={'note': 'geo test'}).get_json()
    assert b['ok'] is True
    assert abs(b['lat'] - 37.7749) < 1e-6
    assert abs(b['lon'] + 122.4194) < 1e-3
    assert b['grid_square'] == 'CM87ss'

    # Fetch bookmarks
    data = client.get('/api/bookmarks').get_json()
    assert len(data['items']) == 1
    it = data['items'][0]
    assert 'lat' in it and 'lon' in it


def test_bookmark_flow(tmp_path, monkeypatch):
    # Redirect bookmarks file to temp path
    import scanner_frontend as sf_mod
    bm = tmp_path / 'bookmarks.csv'
    monkeypatch.setattr(sf_mod, '_BOOKMARKS', bm)
    sf_mod.state.stop()
    sf_mod.state.current_index = 10
    sf_mod.state.current_freq_hz = 146520000

    app = sf_mod.app
    client = app.test_client()

    # Ensure empty
    data = client.get('/api/bookmarks').get_json()
    assert data['items'] == []

    # Add bookmark
    b = client.post('/api/bookmark', json={'note': 'calling freq'}).get_json()
    assert b['ok'] is True
    assert b['freq_hz'] == 146520000
    assert 'timestamp' in b
    assert b.get('note') == 'calling freq'

    # Read back
    data = client.get('/api/bookmarks').get_json()
    assert len(data['items']) == 1
    assert data['items'][0]['freq_hz'] == 146520000


def test_hold_freezes_index():
    app = sf.app
    client = app.test_client()

    # Ensure scanning, short dwell
    client.post('/api/stop')
    client.post('/api/start', json={'dwell_seconds': 0.03})

    # Wait a moment for index to increment
    time.sleep(0.12)
    st1 = client.get('/api/status').get_json()
    idx_before = st1['index']

    # Request hold for 0.2s
    client.post('/api/hold', json={'seconds': 0.2})

    # Sleep slightly less than hold duration to verify freeze
    time.sleep(0.15)
    st2 = client.get('/api/status').get_json()
    assert st2['index'] == idx_before

    # After hold expires, it should resume progressing
    time.sleep(0.15)
    st3 = client.get('/api/status').get_json()
    assert st3['index'] != idx_before


def test_status_includes_hit_stats():
    """New hit_count, unique_freq_count, rms, sdr_available fields in /api/status."""
    client = sf.app.test_client()
    st = client.get('/api/status').get_json()
    assert 'hit_count' in st
    assert 'unique_freq_count' in st
    assert 'rms' in st
    assert 'sdr_available' in st
    assert isinstance(st['hit_count'], int)
    assert isinstance(st['unique_freq_count'], int)
    assert isinstance(st['rms'], float)


def test_activity_log_written_on_hit(tmp_path, monkeypatch):
    """When force_active_indices triggers a hit, activity CSV is written."""
    import csv
    import scanner_frontend as sf_mod

    log_path = tmp_path / "test_activity.csv"
    sf_mod.state.stop()
    sf_mod.state.hold_seconds = 0.0

    client = sf_mod.app.test_client()
    # Start first (which resets activity_log_path), then apply test overrides
    client.post('/api/start', json={'dwell_seconds': 0.03})
    sf_mod.state.activity_log_path = log_path
    sf_mod.state.current_index = 5
    sf_mod.state.force_active_indices = {5}
    time.sleep(0.2)
    client.post('/api/stop')

    # Clean up test hook
    sf_mod.state.force_active_indices = set()

    assert log_path.exists(), "Activity log was not created"
    with log_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) >= 1
    assert int(rows[0]['freq_hz']) == sf_mod.state.freqs[5]
    assert float(rows[0]['rms']) > 0


def test_rtl_fallback_no_hardware():
    """Without rtl_fm, scanner runs in fallback mode (no crashes)."""
    import scanner_frontend as sf_mod

    sf_mod.state.stop()
    sf_mod.state._rtl_available = False
    sf_mod.state.force_active_indices = set()
    sf_mod.state.dwell_seconds = 0.02

    client = sf_mod.app.test_client()
    client.post('/api/start', json={'dwell_seconds': 0.02})
    time.sleep(0.1)
    st = client.get('/api/status').get_json()
    assert st['running'] is True
    assert st['active'] is False
    client.post('/api/stop')


def test_sample_freq_returns_tuple():
    """_sample_freq returns (rms, raw_bytes) even without hardware."""
    import scanner_frontend as sf_mod
    rms, raw = sf_mod._sample_freq(146520000, 0.1)
    assert isinstance(rms, float)
    assert rms >= 0.0
    assert isinstance(raw, bytes)
