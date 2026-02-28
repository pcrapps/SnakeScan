#!/usr/bin/env python3
"""AI signal classification via vision LLM spectrogram analysis."""

import base64
import io
import time
import urllib.request
import json

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import spectrogram
from PIL import Image


def _generate_spectrogram_jpeg(audio_bytes: bytes, sample_rate: int = 22050) -> bytes:
    """Convert raw int16 PCM audio bytes to a spectrogram JPEG image."""
    data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    f, t, Sxx = spectrogram(data, fs=sample_rate, nperseg=256, noverlap=192)
    Sxx_db = 10 * np.log10(Sxx + 1e-12)

    fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
    ax.pcolormesh(t, f, Sxx_db, shading="gouraud", cmap="inferno")
    ax.set_ylabel("Freq (Hz)")
    ax.set_xlabel("Time (s)")
    ax.set_title("Spectrogram")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    # Compress via Pillow to keep payload small
    img = Image.open(buf)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=80)
    return out.getvalue()


def classify_signal(freq_hz: int, audio_bytes: bytes,
                    api_url: str = "http://localhost:1234/v1/chat/completions",
                    model: str = "qwen3-vl-8b") -> dict:
    """Classify a radio signal from raw int16 PCM audio via vision LLM.

    Returns dict with keys: classification, freq_hz, latency_ms, error.
    Never raises — all errors captured in the error field.
    """
    start = time.monotonic()
    freq_mhz = freq_hz / 1e6
    result = {
        "classification": "unknown",
        "freq_hz": freq_hz,
        "latency_ms": 0,
        "error": None,
    }

    try:
        if len(audio_bytes) < 512:
            result["error"] = "insufficient audio"
            result["latency_ms"] = int((time.monotonic() - start) * 1000)
            return result

        jpeg_bytes = _generate_spectrogram_jpeg(audio_bytes)
        b64_image = base64.b64encode(jpeg_bytes).decode("ascii")

        prompt = (
            f"This is a radio frequency spectrogram at {freq_mhz:.3f} MHz. "
            "Identify the signal type (FM voice, digital, repeater, APRS, "
            "noise, unknown). One sentence max."
        )

        payload = {
            "model": model,
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
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 80,
            "temperature": 0.2,
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        classification = (
            resp_data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "unknown")
        )
        result["classification"] = classification.strip()

    except Exception as e:
        result["error"] = str(e)

    result["latency_ms"] = int((time.monotonic() - start) * 1000)
    return result
