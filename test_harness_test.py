#!/usr/bin/env python3
"""Tests for test_harness.py — verifies correct payload shapes for each mode.

Uses unittest.mock to mock HTTP calls so no running server is needed.
"""

import base64
import json
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

import test_harness as th


# --- Helpers ---

def _mock_response(json_data=None, status_code=200, text=""):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"ok": True}
    resp.text = text or json.dumps(json_data or {"ok": True})
    return resp


def _capturing_session():
    """Return a mock session that records all post/get calls and returns OK."""
    session = MagicMock()
    session.post.return_value = _mock_response({"ok": True})
    session.get.return_value = _mock_response({
        "running": True, "current_freq_hz": 146520000,
        "current_freq_str": "146.520 MHz", "dwell_seconds": 0.5,
        "total_freqs": 160, "index": 10, "active": False,
        "rms": 0.0, "hold_seconds": 0.0, "hold_remaining": 0.0,
        "hit_count": 0, "unique_freq_count": 0, "sdr_available": None,
    })
    return session


# --- Payload shape tests ---

class TestMakeGpsPayload:
    def test_has_required_keys(self):
        payload = th.make_gps_payload()
        for key in ("lat", "lon", "accuracy", "altitude", "speed", "heading"):
            assert key in payload, f"Missing key: {key}"

    def test_lat_lon_near_kc(self):
        payload = th.make_gps_payload()
        assert abs(payload["lat"] - th.KC_LAT) < 0.01
        assert abs(payload["lon"] - th.KC_LON) < 0.01

    def test_accuracy_in_range(self):
        payload = th.make_gps_payload()
        assert 3 <= payload["accuracy"] <= 25


class TestMakeAprsPacket:
    def test_valid_tnc2_format(self):
        pkt = th.make_aprs_packet(39.0997, -94.5786)
        assert ">" in pkt
        assert ":" in pkt
        # Should contain position marker
        assert "!" in pkt

    def test_contains_callsign(self):
        pkt = th.make_aprs_packet(39.0997, -94.5786)
        source = pkt.split(">")[0]
        assert source in th.APRS_CALLSIGNS

    def test_contains_position_data(self):
        pkt = th.make_aprs_packet(39.0997, -94.5786)
        # KC is ~39N, ~094W — APRS format: 3905.98N/09434.72W
        assert "N" in pkt
        assert "W" in pkt


class TestMakeFftPayload:
    def test_has_required_keys(self):
        payload = th.make_fft_payload()
        assert "bins" in payload
        assert "power_db" in payload
        assert "timestamp" in payload

    def test_correct_bin_count(self):
        payload = th.make_fft_payload(n_bins=128)
        assert len(payload["bins"]) == 128
        assert len(payload["power_db"]) == 128

    def test_bins_are_floats(self):
        payload = th.make_fft_payload()
        assert all(isinstance(b, float) for b in payload["bins"])
        assert all(isinstance(p, float) for p in payload["power_db"])

    def test_frequency_range(self):
        payload = th.make_fft_payload()
        assert payload["bins"][0] == pytest.approx(144000000, rel=1e-3)
        assert payload["bins"][-1] == pytest.approx(148000000, rel=1e-3)


class TestMakeAiPayload:
    def test_has_openai_structure(self):
        jpeg = th.make_fake_spectrogram_jpeg()
        payload = th.make_ai_payload(jpeg)
        assert payload["model"] == "qwen3-vl-8b"
        assert "messages" in payload
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
        assert payload["max_tokens"] == 80

    def test_content_has_image_and_text(self):
        jpeg = th.make_fake_spectrogram_jpeg()
        payload = th.make_ai_payload(jpeg)
        content = payload["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "image_url"
        assert content[1]["type"] == "text"

    def test_image_is_valid_base64(self):
        jpeg = th.make_fake_spectrogram_jpeg()
        payload = th.make_ai_payload(jpeg)
        url = payload["messages"][0]["content"][0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        b64_part = url.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert len(decoded) > 0


class TestMakeSpectrogramJpeg:
    def test_returns_bytes(self):
        result = th.make_fake_spectrogram_jpeg()
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_starts_with_jpeg_magic(self):
        result = th.make_fake_spectrogram_jpeg()
        # JPEG files start with FF D8
        assert result[:2] == b"\xff\xd8"


# --- Mode runner tests (mocked HTTP) ---

class TestRunScan:
    def test_hits_expected_endpoints(self):
        session = _capturing_session()
        th.run_scan(session, "http://test:8080")

        post_urls = [c.args[0] for c in session.post.call_args_list]
        get_urls = [c.args[0] for c in session.get.call_args_list]

        assert "http://test:8080/api/start" in post_urls
        assert "http://test:8080/api/set_freq" in post_urls
        assert "http://test:8080/api/hold" in post_urls
        assert "http://test:8080/api/bookmark" in post_urls
        assert "http://test:8080/api/status" in get_urls
        assert "http://test:8080/api/bookmarks" in get_urls
        assert "http://test:8080/api/health" in get_urls

    def test_start_payload_shape(self):
        session = _capturing_session()
        th.run_scan(session, "http://test:8080")

        start_call = [c for c in session.post.call_args_list
                      if "start" in c.args[0]][0]
        payload = start_call.kwargs.get("json") or start_call[1].get("json")
        assert "dwell_seconds" in payload
        assert isinstance(payload["dwell_seconds"], (int, float))

    def test_hold_payload_shape(self):
        session = _capturing_session()
        th.run_scan(session, "http://test:8080")

        hold_call = [c for c in session.post.call_args_list
                     if "hold" in c.args[0]][0]
        payload = hold_call.kwargs.get("json") or hold_call[1].get("json")
        assert "seconds" in payload
        assert payload["seconds"] > 0

    def test_set_freq_payload_uses_known_frequency(self):
        session = _capturing_session()
        th.run_scan(session, "http://test:8080")

        freq_call = [c for c in session.post.call_args_list
                     if "set_freq" in c.args[0]][0]
        payload = freq_call.kwargs.get("json") or freq_call[1].get("json")
        assert "freq_hz" in payload
        assert payload["freq_hz"] in th.ACTIVE_FREQS_HZ


class TestRunGps:
    def test_posts_to_geo_endpoint(self):
        session = _capturing_session()
        th.run_gps(session, "http://test:8080")

        post_urls = [c.args[0] for c in session.post.call_args_list]
        assert "http://test:8080/api/geo" in post_urls

    def test_geo_payload_has_required_fields(self):
        session = _capturing_session()
        th.run_gps(session, "http://test:8080")

        geo_call = [c for c in session.post.call_args_list
                    if "geo" in c.args[0]][0]
        payload = geo_call.kwargs.get("json") or geo_call[1].get("json")
        for key in ("lat", "lon", "accuracy"):
            assert key in payload
        assert abs(payload["lat"] - th.KC_LAT) < 0.01
        assert abs(payload["lon"] - th.KC_LON) < 0.01


class TestRunAprs:
    def test_polls_aprs_endpoint(self):
        session = _capturing_session()
        th.run_aprs(session, "http://test:8080")

        get_urls = [c.args[0] for c in session.get.call_args_list]
        assert "http://test:8080/api/aprs" in get_urls


class TestRunFft:
    def test_attempts_post_and_get(self):
        session = _capturing_session()
        th.run_fft(session, "http://test:8080")

        post_urls = [c.args[0] for c in session.post.call_args_list]
        get_urls = [c.args[0] for c in session.get.call_args_list]
        assert "http://test:8080/api/fft" in post_urls
        assert "http://test:8080/api/fft" in get_urls

    def test_skips_post_on_404(self, capsys):
        session = _capturing_session()
        session.post.return_value = _mock_response(status_code=404)
        th.run_fft(session, "http://test:8080")

        captured = capsys.readouterr()
        assert "SKIP" in captured.out


class TestRunAi:
    def test_posts_to_ai_url(self):
        session = _capturing_session()
        ai_resp = _mock_response({
            "choices": [{"message": {"content": "FM voice signal"}}]
        })
        session.post.return_value = ai_resp

        th.run_ai(session, "http://test:8080",
                  "http://localhost:1234/v1/chat/completions")

        ai_calls = [c for c in session.post.call_args_list
                    if "1234" in c.args[0]]
        assert len(ai_calls) == 1
        payload = ai_calls[0].kwargs.get("json") or ai_calls[0][1].get("json")
        assert payload["model"] == "qwen3-vl-8b"
        assert len(payload["messages"]) == 1

    def test_handles_connection_refused(self, capsys):
        session = _capturing_session()
        session.post.side_effect = [
            ConnectionError("refused"),  # AI call
        ]
        # get still works for last_classification
        session.get.return_value = _mock_response({"ok": True, "classification": None})

        th.run_ai(session, "http://test:8080", "http://localhost:1234/v1/chat/completions")
        captured = capsys.readouterr()
        assert "SKIP" in captured.out or "FAIL" in captured.out

    def test_checks_last_classification(self):
        session = _capturing_session()
        session.post.return_value = _mock_response({
            "choices": [{"message": {"content": "noise"}}]
        })

        th.run_ai(session, "http://test:8080", "http://localhost:1234/v1/chat/completions")

        get_urls = [c.args[0] for c in session.get.call_args_list]
        assert "http://test:8080/api/last_classification" in get_urls


# --- CLI argument parsing ---

class TestCliArgs:
    def test_defaults(self):
        parser = th.main.__code__  # just verify main exists
        assert callable(th.main)

    def test_drift_coord_stays_near_base(self):
        for _ in range(100):
            val = th.drift_coord(39.0997, max_drift=0.005)
            assert abs(val - 39.0997) <= 0.005
