from __future__ import annotations

import io
import json
import logging
import os
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_STT_URL = "https://api.sarvam.ai/speech-to-text"


def _redact_secrets(text: str) -> str:
    api_key = os.getenv("SARVAM_API_KEY") or ""
    if api_key:
        return text.replace(api_key, "[REDACTED]")
    return text


@dataclass(frozen=True)
class STTResult:
    success: bool
    transcript: str | None
    language_code: str | None
    latency_ms: float
    request_id: str | None
    error: str | None = None


class SarvamSTTProvider:
    """Standalone STT diagnostic service using Sarvam Saaras v3.

    This is NOT coupled to the calling/telephony architecture.
    It is for standalone voice quality testing only.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured")

    def transcribe(
        self,
        audio_bytes: bytes,
        language_code: str = "hi-IN",
        model: str = "saaras:v3",
        mode: str = "transcribe",
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
    ) -> STTResult:
        """Transcribe audio using Sarvam STT API.

        Args:
            audio_bytes: Raw audio file bytes.
            language_code: BCP-47 language code, or "unknown" for auto-detect.
            model: Model version (saaras:v3 or saaras:v4).
            mode: Transcription mode (transcribe, translate, verbatim, translit, codemix).
            filename: Filename for multipart upload.
            content_type: MIME type of the audio file.

        Returns:
            STTResult with transcript, language, latency, and metadata.
        """
        boundary = "----SarvamSTTBoundary"

        parts = []

        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(audio_bytes)
        parts.append(b"\r\n")

        parts.append(f"--{boundary}\r\n".encode())
        parts.append(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        parts.append(model.encode())
        parts.append(b"\r\n")

        parts.append(f"--{boundary}\r\n".encode())
        parts.append(b'Content-Disposition: form-data; name="language_code"\r\n\r\n')
        parts.append(language_code.encode())
        parts.append(b"\r\n")

        parts.append(f"--{boundary}\r\n".encode())
        parts.append(b'Content-Disposition: form-data; name="mode"\r\n\r\n')
        parts.append(mode.encode())
        parts.append(b"\r\n")

        parts.append(f"--{boundary}--\r\n".encode())

        body = b"".join(parts)

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "api-subscription-key": self.api_key,
        }

        request = Request(_STT_URL, data=body, method="POST", headers=headers)

        start = time.perf_counter()
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                latency_ms = (time.perf_counter() - start) * 1000
                data = json.loads(raw)

                request_id = data.get("request_id")
                transcript = data.get("transcript")
                detected_lang = data.get("language_code")

                logger.info(
                    "Sarvam STT success: '%s' (lang=%s), %.0fms, request_id=%s",
                    (transcript or "")[:80],
                    detected_lang,
                    latency_ms,
                    request_id,
                )

                return STTResult(
                    success=True,
                    transcript=transcript,
                    language_code=detected_lang,
                    latency_ms=latency_ms,
                    request_id=request_id,
                )

        except HTTPError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "Sarvam STT HTTP %d: %s",
                exc.code,
                _redact_secrets(error_body),
            )
            return STTResult(
                success=False,
                transcript=None,
                language_code=None,
                latency_ms=latency_ms,
                request_id=None,
                error=f"HTTP {exc.code}: {_redact_secrets(error_body)}",
            )

        except URLError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Sarvam STT network error: %s", exc.reason)
            return STTResult(
                success=False,
                transcript=None,
                language_code=None,
                latency_ms=latency_ms,
                request_id=None,
                error=f"Network error: {exc.reason}",
            )

        except json.JSONDecodeError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Sarvam STT invalid JSON response")
            return STTResult(
                success=False,
                transcript=None,
                language_code=None,
                latency_ms=latency_ms,
                request_id=None,
                error="Invalid JSON response from Sarvam STT",
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Sarvam STT unexpected error: %s", exc)
            return STTResult(
                success=False,
                transcript=None,
                language_code=None,
                latency_ms=latency_ms,
                request_id=None,
                error=f"Unexpected error: {exc}",
            )
