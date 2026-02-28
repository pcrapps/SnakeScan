#!/usr/bin/env python3
import threading
import time
from dataclasses import dataclass, field
from typing import List
import subprocess
import sys
import os
import shutil

from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
import numpy as np
import csv
import datetime as _dt
import pathlib

from ai_classifier import classify_signal

# ----- AI Classification Config (env vars) -----
AI_CLASSIFY_ENABLED = os.environ.get("AI_CLASSIFY_ENABLED", "false").lower() == "true"
AI_VISION_API_URL = os.environ.get("AI_VISION_API_URL", "http://localhost:1234/v1/chat/completions")
AI_VISION_MODEL = os.environ.get("AI_VISION_MODEL", "qwen3-vl-8b")
AI_CAPTURE_SECONDS = float(os.environ.get("AI_CAPTURE_SECONDS", "0.5"))


# ----- FFT Configuration -----
FFT_ENABLED = os.environ.get("FFT_ENABLED", "1").lower() not in ("0", "false", "no")
FFT_INTERVAL_SECONDS = float(os.environ.get("FFT_INTERVAL_SECONDS", "1.0"))
FFT_BINS = int(os.environ.get("FFT_BINS", "256"))


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


def _check_rtl_available() -> bool:
    """Check if rtl_fm binary is on PATH."""
    return shutil.which("rtl_fm") is not None


def _sample_freq(freq_hz: int, dwell: float, gain: int = 25,
                 squelch_db: int = 5, ppm: int = 0, sr: int = 22050) -> tuple[float, bytes]:
    """Capture audio from rtl_fm at freq_hz for dwell seconds.

    Returns (rms, raw_bytes). Returns (0.0, b'') on any error.
    """
    try:
        cmd = [
            "timeout", f"{dwell}s",
            "rtl_fm",
            "-f", str(freq_hz),
            "-M", "fm",
            "-s", str(sr),
            "-r", str(sr),
            "-g", str(gain),
            "-l", str(squelch_db),
            "-p", str(ppm),
            "-",
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                timeout=dwell + 5)
        raw = result.stdout
        if len(raw) < 2:
            return 0.0, b""
        data = np.frombuffer(raw, dtype=np.int16)
        rms = float(np.sqrt(np.mean((data / 32768.0) ** 2)))
        return rms, raw
    except Exception:
        return 0.0, b""


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
    _resume_event: threading.Event = field(default_factory=threading.Event)
    # Latest client-provided location (optional)
    last_location: dict | None = None
    # RTL-SDR config
    sdr_gain: int = 25
    sdr_squelch_db: int = 5
    sdr_ppm: int = 0
    sdr_sample_rate: int = 22050
    # Wardrive stats
    hit_count: int = 0
    unique_freqs: set[int] = field(default_factory=set)
    activity_log_path: pathlib.Path = field(
        default_factory=lambda: pathlib.Path(
            f"activity_{_dt.datetime.now():%Y%m%d_%H%M%S}.csv"
        )
    )
    _rtl_available: bool | None = None  # None = not yet probed
    # AI classification
    last_classification: dict | None = None
    _ai_executor: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)
    # Cached activity log file handle (opened lazily, closed on stop)
    _activity_file: object | None = field(default=None, init=False, repr=False)
    _activity_writer: object | None = field(default=None, init=False, repr=False)
    _activity_log_opened_for: pathlib.Path | None = field(default=None, init=False, repr=False)
    # FFT state
    last_fft: dict | None = None
    _fft_thread: threading.Thread | None = None
    _fft_stop: threading.Event = field(default_factory=threading.Event)

    def start(self):
        self._close_activity_log()
        with self._lock:
            if self.running:
                return
            self.running = True
            self._stop_event.clear()
            self._resume_event.set()
            # Fresh activity log for each session
            self.hit_count = 0
            self.unique_freqs = set()
            self.activity_log_path = pathlib.Path(
                f"activity_{_dt.datetime.now():%Y%m%d_%H%M%S}.csv"
            )
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()
            if FFT_ENABLED:
                self._fft_stop.clear()
                if self._fft_thread is None or not self._fft_thread.is_alive():
                    self._fft_thread = threading.Thread(target=self._fft_loop, daemon=True)
                    self._fft_thread.start()

    def stop(self):
        with self._lock:
            self.running = False
            self._stop_event.set()
            self._kick_event.set()
            self._resume_event.clear()
        self._fft_stop.set()
        self.last_fft = None
        self._close_activity_log()

    def _close_activity_log(self):
        """Close the session activity log file handle."""
        if self._activity_file is not None:
            try:
                self._activity_file.close()
            except Exception:
                pass
            self._activity_file = None
            self._activity_writer = None
            self._activity_log_opened_for = None

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def _run_loop(self):
        while True:
            if not self.running:
                # Block until start() signals resume (zero CPU while idle)
                self._resume_event.wait()
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

            # Activity detection (3 tiers):
            # 1. force_active_indices — deterministic test hook
            # 2. RTL-SDR hardware via rtl_fm — real RMS sampling
            # 3. Fallback: no activity
            _used_hardware = False
            _raw_audio = b""
            if self.force_active_indices:
                self.active = self.current_index in self.force_active_indices
                self.rms = 1.0 if self.active else 0.0
            else:
                if self._rtl_available is None:
                    self._rtl_available = _check_rtl_available()
                if self._rtl_available:
                    self.rms, _raw_audio = _sample_freq(
                        self.current_freq_hz, self.dwell_seconds,
                        self.sdr_gain, self.sdr_squelch_db,
                        self.sdr_ppm, self.sdr_sample_rate,
                    )
                    self.active = self.rms > self.rms_threshold
                    _used_hardware = True
                else:
                    self.rms = 0.0
                    self.active = False

            # Auto-log hit
            if self.active:
                self.hit_count += 1
                self.unique_freqs.add(self.current_freq_hz)
                _log_activity_hit(self)
                # Submit AI classification in background
                if AI_CLASSIFY_ENABLED and _raw_audio:
                    _submit_classification(self, self.current_freq_hz, _raw_audio)

            # If active, set hold window
            if self.active and self.hold_seconds > 0:
                self._hold_until_ts = time.time() + self.hold_seconds
                continue

            # Dwell: if hardware sampled, dwell was consumed by _sample_freq;
            # otherwise sleep-wait with interrupt support
            if not _used_hardware:
                self._kick_event.clear()
                woke_stop = self._stop_event.wait(self.dwell_seconds)
                woke_kick = self._kick_event.is_set()
                if woke_stop or woke_kick:
                    continue
            else:
                if self._stop_event.is_set() or self._kick_event.is_set():
                    self._kick_event.clear()
                    continue

            # Advance to next only if not stopped during dwell and not holding
            self.current_index = (self.current_index + 1) % len(self.freqs)

    def _fft_loop(self):
        """Background thread: compute FFT at configured interval."""
        while not self._fft_stop.is_set():
            if self.running:
                try:
                    self._compute_fft()
                except Exception:
                    pass
            self._fft_stop.wait(FFT_INTERVAL_SECONDS)

    def _compute_fft(self):
        """Compute FFT spectrum from simulated (or real) samples using numpy.fft.rfft."""
        n_samples = FFT_BINS * 2
        freq_start = self.freqs[0]
        freq_end = self.freqs[-1]
        bw = freq_end - freq_start

        # Synthetic baseband signal (noise floor)
        samples = np.random.normal(0, 0.01, n_samples)

        # Inject tones at active frequencies
        active_hz = set()
        if self.active and self.current_freq_hz:
            active_hz.add(self.current_freq_hz)
        for fi in self.force_active_indices:
            if 0 <= fi < len(self.freqs):
                active_hz.add(self.freqs[fi])

        if active_hz:
            t = np.arange(n_samples)
            for af in active_hz:
                norm = (af - freq_start) / bw * 0.5
                samples += 0.1 * np.sin(2 * np.pi * norm * t)

        # Compute real FFT
        spectrum = np.fft.rfft(samples)
        power = np.abs(spectrum[:FFT_BINS]) ** 2
        power_db = 10.0 * np.log10(power + 1e-12)

        bins = np.linspace(freq_start, freq_end, FFT_BINS)
        self.last_fft = {
            "bins": bins.tolist(),
            "power_db": power_db.tolist(),
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        }


def _submit_classification(st: ScannerState, freq_hz: int, audio_bytes: bytes) -> None:
    """Submit an AI classification job to the background executor."""
    if st._ai_executor is None:
        st._ai_executor = ThreadPoolExecutor(max_workers=1)

    def _do_classify():
        result = classify_signal(freq_hz, audio_bytes, AI_VISION_API_URL, AI_VISION_MODEL)
        st.last_classification = result

    st._ai_executor.submit(_do_classify)


# ----- Flask App -----
app = Flask(__name__, static_url_path="", static_folder="web")
state = ScannerState()
_io_lock = threading.Lock()
_BOOKMARKS = pathlib.Path("bookmarks.csv")

_ACTIVITY_LOG_HEADER = [
    "timestamp", "freq_hz", "freq_str", "rms", "index",
    "lat", "lon", "grid_square", "accuracy", "speed", "heading",
]


def _log_activity_hit(st: ScannerState) -> None:
    """Append one row to the activity log CSV. Thread-safe via _io_lock."""
    row = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "freq_hz": st.current_freq_hz,
        "freq_str": freq_to_str_hz(st.current_freq_hz),
        "rms": round(st.rms, 6),
        "index": st.current_index,
    }
    if st.last_location:
        row.update({
            "lat": st.last_location.get("lat"),
            "lon": st.last_location.get("lon"),
            "grid_square": st.last_location.get("grid_square"),
            "accuracy": st.last_location.get("accuracy"),
            "speed": st.last_location.get("speed"),
            "heading": st.last_location.get("heading"),
        })
    with _io_lock:
        # Lazily open (or reopen if path changed, e.g. test override)
        if st._activity_writer is None or st._activity_log_opened_for != st.activity_log_path:
            if st._activity_file is not None:
                try:
                    st._activity_file.close()
                except Exception:
                    pass
            new_file = not st.activity_log_path.exists()
            st._activity_file = st.activity_log_path.open("a", newline="")
            st._activity_writer = csv.DictWriter(
                st._activity_file, fieldnames=_ACTIVITY_LOG_HEADER,
                extrasaction="ignore")
            if new_file:
                st._activity_writer.writeheader()
            st._activity_log_opened_for = st.activity_log_path
        st._activity_writer.writerow(row)
        st._activity_file.flush()


@app.get("/")
def index():
    return send_from_directory("web", "index.html")


def _build_status_payload() -> dict:
    """Build the status dict used by both /api/status and SSE."""
    hold_remaining = max(0.0, state._hold_until_ts - time.time()) if state._hold_until_ts else 0.0
    payload = {
        "running": state.running,
        "current_freq_hz": state.current_freq_hz,
        "current_freq_str": freq_to_str_hz(state.current_freq_hz),
        "dwell_seconds": state.dwell_seconds,
        "total_freqs": len(state.freqs),
        "index": state.current_index,
        "active": state.active,
        "rms": round(state.rms, 6),
        "hold_seconds": state.hold_seconds,
        "hold_remaining": round(hold_remaining, 3),
        "hit_count": state.hit_count,
        "unique_freq_count": len(state.unique_freqs),
        "sdr_available": bool(state._rtl_available) if state._rtl_available is not None else None,
    }
    if state.last_location:
        payload["location"] = state.last_location
    return payload


@app.get("/api/status")
def api_status():
    return jsonify(_build_status_payload())


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
    def stream():
        # Emit periodic status updates; include heartbeat comments to avoid buffering
        heartbeat = 0
        while True:
            st = _build_status_payload()
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


@app.get("/api/last_classification")
def api_last_classification():
    if state.last_classification is None:
        return jsonify(ok=True, classification=None)
    return jsonify(ok=True, **state.last_classification)



@app.get("/api/fft")
def api_fft():
    if not FFT_ENABLED:
        return jsonify(ok=False, error="FFT disabled"), 404
    if state.last_fft is None:
        return jsonify(bins=[], power_db=[], timestamp=None)
    return jsonify(state.last_fft)


@app.post("/api/set_freq")
def api_set_freq():
    if not request.is_json:
        return jsonify(ok=False, error="Expected JSON"), 400
    freq_hz = request.json.get("freq_hz")
    if not isinstance(freq_hz, (int, float)):
        return jsonify(ok=False, error="freq_hz required"), 400
    freq_hz = int(freq_hz)
    nearest_idx = int(np.argmin(np.abs(np.array(state.freqs) - freq_hz)))
    state.current_index = nearest_idx
    state.current_freq_hz = state.freqs[nearest_idx]
    state._kick_event.set()
    return jsonify(ok=True, freq_hz=state.current_freq_hz,
                   freq_str=freq_to_str_hz(state.current_freq_hz),
                   index=nearest_idx)


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
