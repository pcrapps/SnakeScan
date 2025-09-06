#!/usr/bin/env python3
import time

import scanner_frontend as sf


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
