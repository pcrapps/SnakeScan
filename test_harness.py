#!/usr/bin/env python3
"""SnakeScan Test Harness — standalone CLI that exercises SnakeScan HTTP endpoints
with realistic fake data. No RTL-SDR hardware required.

Usage:
    python test_harness.py --mode all --host http://localhost:5000 --duration 60 --rate 2
"""

import argparse
import base64
import io
import json
import random
import sys
import time

import numpy as np
import requests


# --- Kansas City coordinates with drift ---
KC_LAT = 39.0997
KC_LON = -94.5786

# Popular 2m frequencies (Hz)
ACTIVE_FREQS_HZ = [146520000, 147000000, 146940000, 146880000, 147120000, 145500000]

# Valid APRS callsigns and paths for KC area
APRS_CALLSIGNS = ["W0KC-5", "K0KCA-9", "N0MO-1", "WA0TJT-7", "KC0PIR-3"]
APRS_PATHS = ["WIDE1-1,WIDE2-1", "WIDE1-1", "WIDE2-2"]


def drift_coord(base: float, max_drift: float = 0.005) -> float:
    """Add small random drift to a coordinate."""
    return round(base + random.uniform(-max_drift, max_drift), 6)


def make_aprs_packet(lat: float, lon: float) -> str:
    """Generate a valid TNC2-format APRS position packet with KC-area coords."""
    call = random.choice(APRS_CALLSIGNS)
    path = random.choice(APRS_PATHS)
    lat_deg = int(abs(lat))
    lat_min = (abs(lat) - lat_deg) * 60
    lat_dir = "N" if lat >= 0 else "S"
    lon_deg = int(abs(lon))
    lon_min = (abs(lon) - lon_deg) * 60
    lon_dir = "E" if lon >= 0 else "W"
    pos = f"!{lat_deg:02d}{lat_min:05.2f}{lat_dir}/{lon_deg:03d}{lon_min:05.2f}{lon_dir}>"
    comment = random.choice(["Mobile", "En route", "QTH KC", f"{random.randint(5, 75)} MPH"])
    return f"{call}>APRS,{path}:{pos}{comment}"


def make_fake_spectrogram_jpeg() -> bytes:
    """Generate a small fake spectrogram JPEG image."""
    width, height = 128, 96
    img_array = np.random.randint(0, 60, (height, width), dtype=np.uint8)
    # Add a fake signal band
    band_y = random.randint(20, 70)
    img_array[band_y:band_y + 5, :] = np.random.randint(150, 255, (5, width), dtype=np.uint8)
    try:
        from PIL import Image
        img = Image.fromarray(img_array, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except ImportError:
        # Minimal 1x1 JPEG fallback
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
            b"\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05"
            b"\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd2\x8a(\x03\xff\xd9"
        )


def make_gps_payload() -> dict:
    """Build a GPS payload with KC coords + slight drift."""
    return {
        "lat": drift_coord(KC_LAT),
        "lon": drift_coord(KC_LON),
        "accuracy": round(random.uniform(3, 25), 1),
        "altitude": round(random.uniform(240, 260), 1),
        "speed": round(random.uniform(0, 30), 1),
        "heading": round(random.uniform(0, 360), 1),
    }


def make_fft_payload(n_bins: int = 256) -> dict:
    """Build a fake FFT spectrum payload."""
    bins = np.linspace(144000000, 148000000, n_bins).tolist()
    power_db = np.random.normal(-80, 10, n_bins).tolist()
    spike_bin = random.randint(1, n_bins - 2)
    power_db[spike_bin] = random.uniform(-20, -5)
    return {
        "bins": bins,
        "power_db": power_db,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def make_ai_payload(jpeg_bytes: bytes) -> dict:
    """Build an OpenAI-compatible vision API payload with spectrogram image."""
    b64_image = base64.b64encode(jpeg_bytes).decode("ascii")
    freq_mhz = random.choice(ACTIVE_FREQS_HZ) / 1e6
    return {
        "model": "qwen3-vl-8b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This is a radio frequency spectrogram at {freq_mhz:.3f} MHz. "
                            "Identify the signal type (FM voice, digital, repeater, APRS, "
                            "noise, unknown). One sentence max."
                        ),
                    },
                ],
            }
        ],
        "max_tokens": 80,
        "temperature": 0.2,
    }


# --- HTTP helpers ---

def _post(session, url, json_data=None, label=""):
    """POST to endpoint, print result, return JSON or None on 404/error."""
    try:
        resp = session.post(url, json=json_data, timeout=5)
        if resp.status_code in (404, 405):
            print(f"  SKIP {label or url} ({resp.status_code})")
            return None
        data = resp.json()
        print(f"  OK   {label or url} -> {json.dumps(data, separators=(',', ':'))[:120]}")
        return data
    except requests.ConnectionError:
        print(f"  FAIL {label or url} (connection refused)")
        return None
    except Exception as e:
        print(f"  FAIL {label or url} ({e})")
        return None


def _get(session, url, label=""):
    """GET from endpoint, print result, return JSON or None on 404/error."""
    try:
        resp = session.get(url, timeout=5)
        if resp.status_code == 404:
            print(f"  SKIP {label or url} (404)")
            return None
        data = resp.json()
        print(f"  OK   {label or url} -> {json.dumps(data, separators=(',', ':'))[:120]}")
        return data
    except requests.ConnectionError:
        print(f"  FAIL {label or url} (connection refused)")
        return None
    except Exception as e:
        print(f"  FAIL {label or url} ({e})")
        return None


# --- Mode runners ---

def run_scan(session, host):
    """Send fake scanner interactions: start, tune, hold, bookmark."""
    print("[scan] Exercising scanner endpoints...")
    _post(session, f"{host}/api/start", {"dwell_seconds": 0.1}, "POST /api/start")
    _get(session, f"{host}/api/status", "GET /api/status")

    freq = random.choice(ACTIVE_FREQS_HZ)
    _post(session, f"{host}/api/set_freq", {"freq_hz": freq},
          f"POST /api/set_freq ({freq / 1e6:.3f} MHz)")
    _post(session, f"{host}/api/hold", {"seconds": 2}, "POST /api/hold (2s)")
    _post(session, f"{host}/api/bookmark",
          {"note": f"Test harness hit on {freq / 1e6:.3f} MHz"},
          "POST /api/bookmark")
    _get(session, f"{host}/api/bookmarks", "GET /api/bookmarks")
    _get(session, f"{host}/api/health", "GET /api/health")
    _get(session, f"{host}/api/status", "GET /api/status (final)")


def run_aprs(session, host):
    """Generate and display fake APRS packets, poll APRS endpoint."""
    print("[aprs] Generating fake APRS packets (KC area)...")
    for i in range(3):
        lat = drift_coord(KC_LAT)
        lon = drift_coord(KC_LON)
        pkt = make_aprs_packet(lat, lon)
        print(f"  APRS #{i + 1}: {pkt}")
    _get(session, f"{host}/api/aprs", "GET /api/aprs")


def run_gps(session, host):
    """Send drifting GPS coordinates (Kansas City)."""
    print("[gps] Posting KC GPS coordinates with drift...")
    payload = make_gps_payload()
    print(f"  GPS: {payload['lat']:.6f}, {payload['lon']:.6f} "
          f"(accuracy: {payload['accuracy']}m)")
    _post(session, f"{host}/api/geo", payload, "POST /api/geo")
    _get(session, f"{host}/api/status", "GET /api/status (check location)")


def run_fft(session, host):
    """Post fake FFT data (if accepted) or poll FFT endpoint."""
    print("[fft] Checking FFT endpoint...")
    fft_payload = make_fft_payload()
    _post(session, f"{host}/api/fft", fft_payload, "POST /api/fft")
    _get(session, f"{host}/api/fft", "GET /api/fft")
    n_bins = len(fft_payload["bins"])
    peak_idx = int(np.argmax(fft_payload["power_db"]))
    print(f"  Generated {n_bins} FFT bins, peak at bin {peak_idx} "
          f"({fft_payload['power_db'][peak_idx]:.1f} dB)")


def run_ai(session, host, ai_url="http://localhost:1234/v1/chat/completions"):
    """Send a fake spectrogram to the AI classifier endpoint on Mac Mini."""
    print(f"[ai] Sending fake spectrogram to AI endpoint ({ai_url})...")
    jpeg_bytes = make_fake_spectrogram_jpeg()
    payload = make_ai_payload(jpeg_bytes)
    b64_len = len(base64.b64encode(jpeg_bytes))
    freq_text = payload["messages"][0]["content"][1]["text"]
    print(f"  Image: {len(jpeg_bytes)} bytes | Base64: {b64_len} chars")

    try:
        resp = session.post(ai_url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            classification = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "unknown")
            )
            print(f"  AI Classification: {classification}")
        else:
            print(f"  AI responded with status {resp.status_code}: {resp.text[:200]}")
    except requests.ConnectionError:
        print(f"  SKIP AI (connection refused at {ai_url} "
              "— is SSH tunnel / LM Studio running?)")
    except Exception as e:
        print(f"  FAIL AI ({e})")

    _get(session, f"{host}/api/last_classification", "GET /api/last_classification")


MODE_RUNNERS = {
    "scan": run_scan,
    "aprs": run_aprs,
    "gps": run_gps,
    "fft": run_fft,
}


def main():
    parser = argparse.ArgumentParser(
        description="SnakeScan Test Harness — exercise endpoints with fake data"
    )
    parser.add_argument("--mode", default="all",
                        choices=["all", "scan", "aprs", "gps", "fft", "ai"],
                        help="Test mode (default: all)")
    parser.add_argument("--host", default="http://localhost:5000",
                        help="SnakeScan base URL (default: http://localhost:5000)")
    parser.add_argument("--duration", type=int, default=60,
                        help="Duration in seconds, 0=forever (default: 60)")
    parser.add_argument("--rate", type=float, default=2,
                        help="Events per second (default: 2)")
    parser.add_argument("--ai-url",
                        default="http://localhost:1234/v1/chat/completions",
                        help="AI vision API URL (default: http://localhost:1234/v1/chat/completions)")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    interval = 1.0 / args.rate if args.rate > 0 else 0.5

    print("SnakeScan Test Harness")
    print(f"  Host:     {host}")
    print(f"  Mode:     {args.mode}")
    print(f"  Duration: {args.duration}s {'(forever)' if args.duration == 0 else ''}")
    print(f"  Rate:     {args.rate} events/sec")
    print()

    session = requests.Session()

    if args.mode == "all":
        modes = ["scan", "gps", "aprs", "fft", "ai"]
    else:
        modes = [args.mode]

    start_time = time.time()
    tick = 0

    try:
        while True:
            elapsed = time.time() - start_time
            if args.duration > 0 and elapsed >= args.duration:
                break

            tick += 1
            print(f"--- tick {tick} ({elapsed:.1f}s elapsed) ---")

            for mode in modes:
                if mode == "ai":
                    run_ai(session, host, args.ai_url)
                elif mode in MODE_RUNNERS:
                    MODE_RUNNERS[mode](session, host)

            print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    print(f"Test harness finished. {tick} ticks in {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
