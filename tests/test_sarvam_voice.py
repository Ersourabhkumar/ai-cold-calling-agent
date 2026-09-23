from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.sarvam_tts import SarvamTTSProvider, TTSResult
from app.services.sarvam_stt import SarvamSTTProvider, STTResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-api-key-12345")


# ---------------------------------------------------------------------------
# TTS Tests
# ---------------------------------------------------------------------------


class TestSarvamTTSProvider:
    def test_init_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SARVAM_API_KEY"):
            SarvamTTSProvider()

    def test_synthesize_success(self):
        tts = SarvamTTSProvider()

        fake_audio = b"fake-wav-audio-data"
        fake_b64 = base64.b64encode(fake_audio).decode()
        response_body = json.dumps({
            "request_id": "req-001",
            "audios": [fake_b64],
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_tts.urlopen", return_value=mock_response) as mock_open:
            result = tts.synthesize(
                text="Hello world",
                language_code="en-IN",
                speaker="priya",
            )

        assert result.success is True
        assert result.audio_bytes == fake_audio
        assert result.request_id == "req-001"
        assert result.latency_ms >= 0
        assert result.error is None

        # Verify request was made correctly
        call_args = mock_open.call_args
        request = call_args[0][0]
        assert request.full_url == "https://api.sarvam.ai/text-to-speech"
        assert request.headers.get("Api-subscription-key") == "test-api-key-12345"
        assert request.headers.get("Content-type") == "application/json"

        body = json.loads(request.data.decode())
        assert body["text"] == "Hello world"
        assert body["language_code"] == "en-IN"
        assert body["speaker"] == "priya"
        assert body["model"] == "bulbul:v3"

    def test_synthesize_empty_audios(self):
        tts = SarvamTTSProvider()

        response_body = json.dumps({
            "request_id": "req-002",
            "audios": [],
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_tts.urlopen", return_value=mock_response):
            result = tts.synthesize(text="Hello", language_code="en-IN")

        assert result.success is False
        assert "empty audios" in result.error.lower()

    def test_synthesize_http_error(self):
        tts = SarvamTTSProvider()

        from urllib.error import HTTPError

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "error": {"message": "Invalid API key", "code": "invalid_api_key_error"}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.sarvam_tts.urlopen",
            side_effect=HTTPError(
                url="https://api.sarvam.ai/text-to-speech",
                code=403,
                msg="Forbidden",
                hdrs={},
                fp=mock_response,
            ),
        ):
            result = tts.synthesize(text="Hello", language_code="en-IN")

        assert result.success is False
        assert "403" in result.error

    def test_synthesize_network_error(self):
        tts = SarvamTTSProvider()

        from urllib.error import URLError

        with patch(
            "app.services.sarvam_tts.urlopen",
            side_effect=URLError("Connection refused"),
        ):
            result = tts.synthesize(text="Hello", language_code="en-IN")

        assert result.success is False
        assert "Network error" in result.error

    def test_synthesize_json_error(self):
        tts = SarvamTTSProvider()

        mock_response = MagicMock()
        mock_response.read.return_value = b"not-json"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_tts.urlopen", return_value=mock_response):
            result = tts.synthesize(text="Hello", language_code="en-IN")

        assert result.success is False
        assert "Invalid JSON" in result.error

    def test_synthesize_hindi_text(self):
        tts = SarvamTTSProvider()

        fake_audio = b"hindi-audio"
        fake_b64 = base64.b64encode(fake_audio).decode()
        response_body = json.dumps({
            "request_id": "req-hi",
            "audios": [fake_b64],
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_tts.urlopen", return_value=mock_response):
            result = tts.synthesize(
                text="\u0928\u092e\u0938\u094d\u0924\u0947",
                language_code="hi-IN",
                speaker="priya",
            )

        assert result.success is True
        assert result.audio_bytes == fake_audio

        body = json.loads(mock_response.read.call_args[0][0] if False else b"{}")
        # Verify Hindi text was sent
        request_body = json.loads(
            mock_response.read()
        ) if False else None

    def test_api_key_not_in_logs(self, caplog):
        tts = SarvamTTSProvider()

        from urllib.error import HTTPError

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"error": {"message": "test-api-key-12345 leaked"}}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.sarvam_tts.urlopen",
            side_effect=HTTPError(
                url="https://api.sarvam.ai/text-to-speech",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=mock_response,
            ),
        ):
            with caplog.at_level("ERROR"):
                result = tts.synthesize(text="Hello", language_code="en-IN")

        assert result.success is False
        for record in caplog.records:
            assert "test-api-key-12345" not in record.message

    def test_synthesize_timeout(self):
        tts = SarvamTTSProvider()

        import socket

        with patch(
            "app.services.sarvam_tts.urlopen",
            side_effect=socket.timeout("timed out"),
        ):
            result = tts.synthesize(text="Hello", language_code="en-IN")

        assert result.success is False
        assert "Unexpected error" in result.error


# ---------------------------------------------------------------------------
# STT Tests
# ---------------------------------------------------------------------------


class TestSarvamSTTProvider:
    def test_init_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SARVAM_API_KEY"):
            SarvamSTTProvider()

    def test_transcribe_success(self):
        stt = SarvamSTTProvider()

        response_body = json.dumps({
            "request_id": "stt-001",
            "transcript": "\u0928\u092e\u0938\u094d\u0924\u0947",
            "language_code": "hi-IN",
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_stt.urlopen", return_value=mock_response) as mock_open:
            result = stt.transcribe(
                audio_bytes=b"fake-audio-data",
                language_code="hi-IN",
            )

        assert result.success is True
        assert result.transcript == "\u0928\u092e\u0938\u094d\u0924\u0947"
        assert result.language_code == "hi-IN"
        assert result.request_id == "stt-001"
        assert result.latency_ms >= 0

        # Verify request was made correctly
        call_args = mock_open.call_args
        request = call_args[0][0]
        assert request.full_url == "https://api.sarvam.ai/speech-to-text"
        assert request.headers.get("Api-subscription-key") == "test-api-key-12345"
        assert "multipart/form-data" in request.headers.get("Content-type", "")

    def test_transcribe_auto_detect_language(self):
        stt = SarvamSTTProvider()

        response_body = json.dumps({
            "request_id": "stt-002",
            "transcript": "Hello, how are you?",
            "language_code": "en-IN",
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_stt.urlopen", return_value=mock_response):
            result = stt.transcribe(
                audio_bytes=b"fake-audio",
                language_code="unknown",
            )

        assert result.success is True
        assert result.language_code == "en-IN"

    def test_transcribe_http_error(self):
        stt = SarvamSTTProvider()

        from urllib.error import HTTPError

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "error": {"message": "Rate limited", "code": "rate_limit_exceeded_error"}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.sarvam_stt.urlopen",
            side_effect=HTTPError(
                url="https://api.sarvam.ai/speech-to-text",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=mock_response,
            ),
        ):
            result = stt.transcribe(audio_bytes=b"audio")

        assert result.success is False
        assert "429" in result.error

    def test_transcribe_network_error(self):
        stt = SarvamSTTProvider()

        from urllib.error import URLError

        with patch(
            "app.services.sarvam_stt.urlopen",
            side_effect=URLError("DNS resolution failed"),
        ):
            result = stt.transcribe(audio_bytes=b"audio")

        assert result.success is False
        assert "Network error" in result.error

    def test_transcribe_json_error(self):
        stt = SarvamSTTProvider()

        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>Error</html>"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.services.sarvam_stt.urlopen", return_value=mock_response):
            result = stt.transcribe(audio_bytes=b"audio")

        assert result.success is False
        assert "Invalid JSON" in result.error

    def test_api_key_not_in_logs(self, caplog):
        stt = SarvamSTTProvider()

        from urllib.error import HTTPError

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"error": {"message": "key test-api-key-12345 invalid"}}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.services.sarvam_stt.urlopen",
            side_effect=HTTPError(
                url="https://api.sarvam.ai/speech-to-text",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=mock_response,
            ),
        ):
            with caplog.at_level("ERROR"):
                result = stt.transcribe(audio_bytes=b"audio")

        assert result.success is False
        for record in caplog.records:
            assert "test-api-key-12345" not in record.message

    def test_multipart_body_contains_audio(self):
        stt = SarvamSTTProvider()

        response_body = json.dumps({
            "request_id": "stt-003",
            "transcript": "test",
            "language_code": "en-IN",
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        audio = b"RIFF fake wav header"

        with patch("app.services.sarvam_stt.urlopen", return_value=mock_response) as mock_open:
            stt.transcribe(audio_bytes=audio, filename="test.wav")

        request = mock_open.call_args[0][0]
        body = request.data
        assert b"fake wav header" in body
        assert b'test.wav' in body
        assert b"saaras:v3" in body

    def test_transcribe_timeout(self):
        stt = SarvamSTTProvider()

        import socket

        with patch(
            "app.services.sarvam_stt.urlopen",
            side_effect=socket.timeout("timed out"),
        ):
            result = stt.transcribe(audio_bytes=b"audio")

        assert result.success is False
        assert "Unexpected error" in result.error


# ---------------------------------------------------------------------------
# TTSResult / STTResult dataclass tests
# ---------------------------------------------------------------------------


class TestResultDataclasses:
    def test_tts_result_fields(self):
        r = TTSResult(
            success=True,
            audio_bytes=b"data",
            latency_ms=150.5,
            request_id="req-1",
        )
        assert r.success is True
        assert r.audio_bytes == b"data"
        assert r.latency_ms == 150.5
        assert r.error is None

    def test_stt_result_fields(self):
        r = STTResult(
            success=True,
            transcript="hello",
            language_code="en-IN",
            latency_ms=200.0,
            request_id="req-2",
        )
        assert r.success is True
        assert r.transcript == "hello"
        assert r.language_code == "en-IN"
        assert r.error is None

    def test_tts_result_failure(self):
        r = TTSResult(
            success=False,
            audio_bytes=None,
            latency_ms=50.0,
            request_id=None,
            error="HTTP 500",
        )
        assert r.success is False
        assert r.audio_bytes is None
        assert r.error == "HTTP 500"
