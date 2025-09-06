#!/usr/bin/env python3
import threading
import time
from dataclasses import dataclass, field
from typing import List

from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
import csv
import datetime as _dt
import pathlib


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
    return jsonify(
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
        "timestamp": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "freq_hz": state.current_freq_hz,
        "freq_str": freq_to_str_hz(state.current_freq_hz),
        "index": state.current_index,
    }
    if request.is_json:
        note = request.json.get("note")
        if isinstance(note, str) and note.strip():
            row["note"] = note.strip()
    header = ["timestamp", "freq_hz", "freq_str", "index"]
    if "note" in row:
        header.append("note")
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


if __name__ == "__main__":
    # Start in stopped state; visit http://localhost:8080 to control
    app.run(host="0.0.0.0", port=8080, debug=False)
