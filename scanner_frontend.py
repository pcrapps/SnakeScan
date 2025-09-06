#!/usr/bin/env python3
import threading
import time
from dataclasses import dataclass, field
from typing import List

from flask import Flask, jsonify, request, send_from_directory
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
    _thread: threading.Thread | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop_event: threading.Event = field(default_factory=threading.Event)

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

            # Set current frequency for this dwell period
            self.current_freq_hz = self.freqs[self.current_index]

            # Wait for dwell, but interrupt immediately if stop is requested
            if self._stop_event.wait(self.dwell_seconds):
                # Stop requested: do not advance index; loop will observe running=False
                continue

            # Advance to next only if not stopped during dwell
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
    return jsonify(
        running=state.running,
        current_freq_hz=state.current_freq_hz,
        current_freq_str=freq_to_str_hz(state.current_freq_hz),
        dwell_seconds=state.dwell_seconds,
        total_freqs=len(state.freqs),
        index=state.current_index,
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


@app.post("/api/bookmark")
def api_bookmark():
    # Append current freq with timestamp to bookmarks.csv
    row = {
        "timestamp": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "freq_hz": state.current_freq_hz,
        "freq_str": freq_to_str_hz(state.current_freq_hz),
        "index": state.current_index,
    }
    header = ["timestamp", "freq_hz", "freq_str", "index"]
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
