from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def _redact_secrets(text: str) -> str:
    api_key = os.getenv("SARVAM_API_KEY") or ""
    if api_key:
        return text.replace(api_key, "[REDACTED]")
    return text


@dataclass(frozen=True)
class TTSResult:
    success: bool
    audio_bytes: bytes | None
    latency_ms: float
    request_id: str | None
    error: str | None = None


class SarvamTTSProvider:
    """Standalone TTS diagnostic service using Sarvam Bulbul v3.

    This is NOT coupled to the calling/telephony architecture.
    It is for standalone voice quality testing only.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured")

    def synthesize(
        self,
        text: str,
        language_code: str = "hi-IN",
        speaker: str = "priya",
        model: str = "bulbul:v3",
        output_codec: str = "wav",
        sample_rate: int = 24000,
        pace: float = 1.0,
    ) -> TTSResult:
        """Convert text to speech using Sarvam TTS API.

        Args:
            text: The text to synthesize.
            language_code: BCP-47 language code (hi-IN, en-IN, etc.).
            speaker: Voice speaker name (priya, shubh, etc.).
            model: Model version (bulbul:v3 or bulbul:v2).
            output_codec: Audio codec (wav, mp3, opus, etc.).
            sample_rate: Output sample rate in Hz.
            pace: Speech speed (0.5-2.0 for v3).

        Returns:
            TTSResult with audio bytes, latency, and metadata.
        """
        payload = {
            "text": text,
            "language_code": language_code,
            "speaker": speaker,
            "model": model,
            "output_audio_codec": output_codec,
            "speech_sample_rate": sample_rate,
            "pace": pace,
        }

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api-subscription-key": self.api_key,
        }

        request = Request(_TTS_URL, data=body, method="POST", headers=headers)

        start = time.perf_counter()
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                latency_ms = (time.perf_counter() - start) * 1000
                data = json.loads(raw)

                request_id = data.get("request_id")
                audios = data.get("audios", [])
                if not audios:
                    return TTSResult(
                        success=False,
                        audio_bytes=None,
                        latency_ms=latency_ms,
                        request_id=request_id,
                        error="Sarvam TTS returned empty audios array",
                    )

                audio_b64 = audios[0]
                audio_bytes = base64.b64decode(audio_b64)

                logger.info(
                    "Sarvam TTS success: %d bytes, %.0fms, request_id=%s",
                    len(audio_bytes),
                    latency_ms,
                    request_id,
                )

                return TTSResult(
                    success=True,
                    audio_bytes=audio_bytes,
                    latency_ms=latency_ms,
                    request_id=request_id,
                )

        except HTTPError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "Sarvam TTS HTTP %d: %s",
                exc.code,
                _redact_secrets(error_body),
            )
            return TTSResult(
                success=False,
                audio_bytes=None,
                latency_ms=latency_ms,
                request_id=None,
                error=f"HTTP {exc.code}: {_redact_secrets(error_body)}",
            )

        except URLError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Sarvam TTS network error: %s", exc.reason)
            return TTSResult(
                success=False,
                audio_bytes=None,
                latency_ms=latency_ms,
                request_id=None,
                error=f"Network error: {exc.reason}",
            )

        except json.JSONDecodeError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Sarvam TTS invalid JSON response")
            return TTSResult(
                success=False,
                audio_bytes=None,
                latency_ms=latency_ms,
                request_id=None,
                error="Invalid JSON response from Sarvam TTS",
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Sarvam TTS unexpected error: %s", exc)
            return TTSResult(
                success=False,
                audio_bytes=None,
                latency_ms=latency_ms,
                request_id=None,
                error=f"Unexpected error: {exc}",
            )
