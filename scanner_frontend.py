#!/usr/bin/env python3
import threading
import time
from dataclasses import dataclass, field
from typing import List
import subprocess
import sys
import os

from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
import csv
import datetime as _dt
import pathlib


# ----- GPS Utilities -----
def lat_lon_to_maidenhead(lat: float, lon: float) -> str:
    """Convert latitude/longitude to Maidenhead grid square (6-character)"""
    lon += 180
    lat += 90

    field_lon = int(lon / 20)
    field_lat = int(lat / 10)
    square_lon = int((lon % 20) / 2)
    square_lat = int(lat % 10)
    subsquare_lon = int(((lon % 20) % 2) * 12)
    subsquare_lat = int(((lat % 10) % 1) * 24)

    return (chr(ord('A') + field_lon) + chr(ord('A') + field_lat) +
            str(square_lon) + str(square_lat) +
            chr(ord('a') + subsquare_lon) + chr(ord('a') + subsquare_lat))


def validate_gps_location(location_data: dict) -> dict | None:
    """Validate and clean GPS location data from browser"""
    if not location_data or 'lat' not in location_data or 'lon' not in location_data:
        return None

    try:
        lat = float(location_data['lat'])
        lon = float(location_data['lon'])

        # Basic coordinate validation
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Accuracy filtering - reject if accuracy > 100m
        accuracy = location_data.get('accuracy')
        if accuracy and float(accuracy) > 100:
            return None

        cleaned = {
            'lat': round(lat, 6),
            'lon': round(lon, 6),
            'grid_square': lat_lon_to_maidenhead(lat, lon),
            'timestamp': _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')
        }

        # Optional fields
        for field in ['accuracy', 'altitude', 'speed', 'heading']:
            if field in location_data and location_data[field] is not None:
                cleaned[field] = round(float(location_data[field]), 2)

        return cleaned
    except (ValueError, TypeError):
        return None


# ----- Scanner Core (simple frequency loop) -----
def build_freqs_2m_25khz() -> List[int]:
    freqs = []
    for freq_khz in range(144000, 148001, 25):
        freqs.append(freq_khz * 1000)  # Hz
    return freqs


def freq_to_str_hz(freq_hz: int) -> str:
    return f"{freq_hz/1e6:.3f} MHz"


@dataclass
class ScannerState:
    freqs: List[int] = field(default_factory=build_freqs_2m_25khz)
    dwell_seconds: float = 0.5
    running: bool = False
    current_index: int = 0
    current_freq_hz: int = 0
    active: bool = False
    rms: float = 0.0
    rms_threshold: float = 0.008
    hold_seconds: float = 0.0
    _hold_until_ts: float = 0.0
    # For tests / deterministic activity: indices to force activity on
    force_active_indices: set[int] = field(default_factory=set)
    _thread: threading.Thread | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _kick_event: threading.Event = field(default_factory=threading.Event)
    # Latest client-provided location (optional)
    last_location: dict | None = None

    def start(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            self._stop_event.clear()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()

    def stop(self):
        with self._lock:
            self.running = False
            self._stop_event.set()
            self._kick_event.set()

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def _run_loop(self):
        while True:
            if not self.running:
                # Sleep briefly when stopped, but keep thread alive for quick resume
                time.sleep(0.05)
                continue

            now = time.time()
            # Hold logic: if within hold window, keep frequency and sleep briefly
            if self._hold_until_ts > now:
                self.active = True
                self.current_freq_hz = self.freqs[self.current_index]
                # Sleep a short interval while holding; allow stop to interrupt
                self._stop_event.wait(min(0.05, self._hold_until_ts - now))
                continue

            # Set current frequency for this dwell period
            self.current_freq_hz = self.freqs[self.current_index]

            # Activity detection: deterministic hook for tests
            self.active = self.current_index in self.force_active_indices

            # If active, set hold window
            if self.active and self.hold_seconds > 0:
                self._hold_until_ts = time.time() + self.hold_seconds
                continue

            # Wait for dwell, but interrupt immediately if stop/hold is requested
            self._kick_event.clear()
            woke_stop = self._stop_event.wait(self.dwell_seconds)
            woke_kick = self._kick_event.is_set()
            if woke_stop or woke_kick:
                # Interrupted: do not advance index
                continue

            # Advance to next only if not stopped during dwell and not holding
            self.current_index = (self.current_index + 1) % len(self.freqs)


# ----- Flask App -----
app = Flask(__name__, static_url_path="", static_folder="web")
state = ScannerState()
_io_lock = threading.Lock()
_BOOKMARKS = pathlib.Path("bookmarks.csv")


@app.get("/")
def index():
    return send_from_directory("web", "index.html")


@app.get("/api/status")
def api_status():
    hold_remaining = max(0.0, state._hold_until_ts - time.time()) if state._hold_until_ts else 0.0
    payload = dict(
        running=state.running,
        current_freq_hz=state.current_freq_hz,
        current_freq_str=freq_to_str_hz(state.current_freq_hz),
        dwell_seconds=state.dwell_seconds,
        total_freqs=len(state.freqs),
        index=state.current_index,
        active=state.active,
        hold_seconds=state.hold_seconds,
        hold_remaining=round(hold_remaining, 3),
    )
    if state.last_location:
        payload["location"] = state.last_location
    return jsonify(payload)


@app.post("/api/start")
def api_start():
    dwell = request.json.get("dwell_seconds") if request.is_json else None
    if isinstance(dwell, (int, float)) and dwell > 0:
        state.dwell_seconds = float(dwell)
    state.start()
    return jsonify(ok=True, running=state.running, dwell_seconds=state.dwell_seconds)


@app.post("/api/stop")
def api_stop():
    state.stop()
    return jsonify(ok=True, running=state.running)


@app.post("/api/toggle")
def api_toggle():
    state.toggle()
    return jsonify(ok=True, running=state.running)


@app.post("/api/hold")
def api_hold():
    seconds = 0
    if request.is_json:
        seconds = float(request.json.get("seconds") or 0)
    seconds = max(0.0, seconds)
    state.hold_seconds = seconds
    if seconds > 0:
        state._hold_until_ts = time.time() + seconds
        state.active = True
        state._kick_event.set()
    else:
        state._hold_until_ts = 0.0
        state.active = False
    return jsonify(ok=True, hold_seconds=state.hold_seconds)


# --- Server-Sent Events (SSE) ---
def _sse_format(event: str, data: dict) -> str:
    import json as _json
    return f"event: {event}\n" f"data: {_json.dumps(data, separators=(',',':'))}\n\n"


@app.get("/api/events")
def api_events():
    def _status_snapshot() -> dict:
        hold_remaining = max(0.0, state._hold_until_ts - time.time()) if state._hold_until_ts else 0.0
        return {
            "running": state.running,
            "current_freq_hz": state.current_freq_hz,
            "current_freq_str": freq_to_str_hz(state.current_freq_hz),
            "dwell_seconds": state.dwell_seconds,
            "total_freqs": len(state.freqs),
            "index": state.current_index,
            "active": state.active,
            "hold_seconds": state.hold_seconds,
            "hold_remaining": round(hold_remaining, 3),
        }

    def stream():
        # Emit periodic status updates; include heartbeat comments to avoid buffering
        heartbeat = 0
        while True:
            st = _status_snapshot()
            yield _sse_format("status", st)
            if st.get("active"):
                yield _sse_format("activity", {"freq": st["current_freq_str"], "index": st["index"]})
            heartbeat += 1
            if heartbeat % 8 == 0:
                # Comment event to nudge proxies/buffers
                yield ": keep-alive\n\n"
            time.sleep(0.25)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(stream()), mimetype="text/event-stream", headers=headers)


@app.post("/api/bookmark")
def api_bookmark():
    # Append current freq with timestamp to bookmarks.csv
    row = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "freq_hz": state.current_freq_hz,
        "freq_str": freq_to_str_hz(state.current_freq_hz),
        "index": state.current_index,
    }
    if request.is_json:
        note = request.json.get("note")
        if isinstance(note, str) and note.strip():
            row["note"] = note.strip()
    # Attach last known location if available (or accept from payload override)
    if request.is_json:
        loc = request.json.get("location")
        if isinstance(loc, dict) and "lat" in loc and "lon" in loc:
            state.last_location = {
                "lat": float(loc.get("lat")),
                "lon": float(loc.get("lon")),
                "accuracy": float(loc.get("accuracy", 0) or 0),
                "speed": float(loc.get("speed", 0) or 0),
                "heading": float(loc.get("heading", 0) or 0),
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            }
    if state.last_location:
        row.update({
            "lat": state.last_location.get("lat"),
            "lon": state.last_location.get("lon"),
            "grid_square": state.last_location.get("grid_square"),
            "accuracy": state.last_location.get("accuracy"),
            "speed": state.last_location.get("speed"),
            "heading": state.last_location.get("heading"),
            "gps_timestamp": state.last_location.get("timestamp"),
        })

    header = ["timestamp", "freq_hz", "freq_str", "index"]
    if "note" in row:
        header.append("note")
    if state.last_location:
        header.extend(["lat", "lon", "grid_square", "accuracy", "speed", "heading", "gps_timestamp"])
    with _io_lock:
        new_file = not _BOOKMARKS.exists()
        with _BOOKMARKS.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            if new_file:
                w.writeheader()
            w.writerow(row)
    return jsonify(ok=True, **row)


@app.get("/api/bookmarks")
def api_bookmarks():
    if not _BOOKMARKS.exists():
        return jsonify(items=[])
    with _io_lock, _BOOKMARKS.open("r", newline="") as f:
        r = csv.DictReader(f)
        items = list(r)
    # Ensure index is int-like if present
    for it in items:
        try:
            it["index"] = int(it["index"])  # type: ignore
            it["freq_hz"] = int(float(it["freq_hz"]))  # tolerate strings
        except Exception:
            pass
    return jsonify(items=items)


@app.post("/api/geo")
def api_geo_update():
    if not request.is_json:
        return jsonify(ok=False, error="Expected JSON"), 400

    data = request.json or {}
    validated_location = validate_gps_location(data)

    if not validated_location:
        return jsonify(ok=False, error="Invalid or inaccurate GPS data"), 400

    state.last_location = validated_location
    return jsonify(ok=True, location=state.last_location)


def cleanup_existing_processes():
    """Kill any existing scanner_frontend.py processes to prevent conflicts"""
    try:
        current_pid = os.getpid()
        result = subprocess.run(['pgrep', '-f', 'scanner_frontend.py'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid_str in pids:
                if pid_str and pid_str.isdigit():
                    pid = int(pid_str)
                    if pid != current_pid:  # Don't kill ourselves
                        try:
                            os.kill(pid, 15)  # SIGTERM
                            print(f"Terminated existing scanner process: {pid}")
                        except ProcessLookupError:
                            pass  # Process already gone
        time.sleep(1)  # Brief pause to let processes clean up
    except Exception as e:
        print(f"Warning: Could not cleanup existing processes: {e}")


if __name__ == "__main__":
    print("SnakeScan starting...")
    cleanup_existing_processes()
    print("Starting scanner on http://localhost:8080")
    # Start in stopped state; visit http://localhost:8080 to control
    try:
        app.run(host="0.0.0.0", port=8080, debug=False)
    except KeyboardInterrupt:
        print("\nShutting down scanner...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
