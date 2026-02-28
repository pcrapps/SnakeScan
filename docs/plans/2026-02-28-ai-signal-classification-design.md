# AI Signal Classification via Vision LLM

## Overview

When the scanner detects activity on a frequency, capture the audio, generate a
spectrogram image, send it to a local vision LLM (Qwen3-VL-8B via LM Studio),
and return a one-sentence classification of the signal type.

## Architecture

### New file: `ai_classifier.py`

- `classify_signal(freq_hz, audio_bytes, api_url, model) -> dict`
- Input: raw int16 PCM audio bytes (from rtl_fm at 22050 Hz sample rate)
- Pipeline: scipy spectrogram -> matplotlib render -> Pillow JPEG -> base64 -> LM Studio vision API
- Returns: `{'classification': str, 'freq_hz': int, 'latency_ms': int, 'error': str|None}`
- 5 second timeout; graceful fallback on any error
- Runs in a ThreadPoolExecutor (max_workers=1) so it never blocks the scanner loop

### Changes to `scanner_frontend.py`

- `_sample_freq()` returns `(rms: float, raw_bytes: bytes)` tuple instead of just `float`
- All callers updated for new return type
- Env vars: `AI_CLASSIFY_ENABLED`, `AI_VISION_API_URL`, `AI_VISION_MODEL`, `AI_CAPTURE_SECONDS`
- New ScannerState field: `last_classification: dict | None`
- On activity detection with AI enabled: submit background classification job
- New endpoint: `GET /api/last_classification`

### Dependencies

Add to requirements.txt: `matplotlib`, `scipy`, `Pillow`

## Data Flow

1. `_sample_freq()` captures rtl_fm audio, returns (rms, raw_bytes)
2. If rms > threshold and AI enabled: submit `classify_signal(freq, raw_bytes, ...)` to executor
3. When classification completes: store result in `state.last_classification`
4. UI can poll `GET /api/last_classification` to show result

## Error Handling

- API unreachable: return `{'error': 'API unreachable', 'classification': 'unknown'}`
- Timeout (5s): return `{'error': 'timeout', 'classification': 'unknown'}`
- Bad audio (too short): return `{'error': 'insufficient audio', 'classification': 'unknown'}`
- Any exception: caught and returned in error field; scanner loop never blocked
