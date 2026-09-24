#!/usr/bin/env python3
"""Standalone Sarvam voice quality test script.

Tests TTS and STT in isolation — no phone number, no telephony, no production mode.
Run: python scripts/test_sarvam_voice.py

Requires: SARVAM_API_KEY in environment.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("CALLING_MODE", "mock")

# Windows consoles often use cp1252, which cannot print Hindi text.
# Force UTF-8 with replacement so reporting never crashes the run.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.services.sarvam_tts import SarvamTTSProvider
from app.services.sarvam_stt import SarvamSTTProvider

OUTPUT_DIR = Path(__file__).resolve().parent / "voice_test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

TEST_CASES = [
    {
        "name": "English - Full greeting",
        "text": (
            "Hi, am I speaking with the property enquiry lead? "
            "I'm Priya calling regarding your property enquiry. "
            "Is this a good time to talk?"
        ),
        "language_code": "en-IN",
        "speaker": "priya",
        "filename": "greeting_en.wav",
    },
    {
        "name": "Hindi - Full greeting",
        "text": (
            "\u0928\u092e\u0938\u094d\u0924\u0947, "
            "\u0915\u094d\u092f\u093e \u092e\u0948\u0902 "
            "\u092a\u094d\u0930\u0949\u092a\u0930\u094d\u091f\u0940 "
            "\u0915\u0947 \u0932\u093f\u090f \u092a\u0942\u091b\u0924\u093e\u091b "
            "\u0915\u0930\u0928\u0947 \u0935\u093e\u0932\u0947 "
            "\u0935\u094d\u092f\u0915\u094d\u0924\u093f \u0938\u0947 "
            "\u092c\u093e\u0924 \u0915\u0930 \u0930\u0939\u0940 "
            "\u0939\u0942\u0901? "
            "\u092e\u0948\u0902 \u092a\u094d\u0930\u093f\u092f\u093e "
            "\u092c\u094b\u0932 \u0930\u0939\u0940 \u0939\u0942\u0901\u0964 "
            "\u0915\u094d\u092f\u093e \u0905\u092d\u0940 "
            "\u092c\u093e\u0924 \u0915\u0930\u0928\u0947 "
            "\u0915\u093e \u0938\u0939\u0940 "
            "\u0938\u092e\u092f \u0939\u0948?"
        ),
        "language_code": "hi-IN",
        "speaker": "priya",
        "filename": "greeting_hi.wav",
    },
    {
        "name": "Hinglish - Full greeting",
        "text": (
            "Namaste, main Priya bol rahi hoon. "
            "Aapne property ke regarding enquiry ki thi. "
            "Main aapki requirements samajhna chahti hoon. "
            "Kya abhi baat kar sakte hain?"
        ),
        "language_code": "hi-IN",
        "speaker": "priya",
        "filename": "greeting_hinglish.wav",
    },
    {
        "name": "English - Budget qualification",
        "text": (
            "Could you share your budget range for the property? "
            "This helps me find options that match your requirements."
        ),
        "language_code": "en-IN",
        "speaker": "priya",
        "filename": "budget_en.wav",
    },
    {
        "name": "Hindi - Budget qualification",
        "text": (
            "\u092a\u094d\u0930\u094b\u092a\u0930\u094d\u091f\u0940 "
            "\u0915\u0947 \u0932\u093f\u090f \u0906\u092a\u0915\u093e "
            "\u092c\u091c\u091f \u0915\u094d\u092f\u093e \u0939\u0948? "
            "\u0907\u0938\u0938\u0947 \u092e\u0947\u0930\u0947 "
            "\u0938\u0939\u0940 \u092e\u0947\u0932 \u092e\u093f\u0932 "
            "\u0938\u0915\u0924\u0947 \u0939\u0948\u0902\u0964"
        ),
        "language_code": "hi-IN",
        "speaker": "priya",
        "filename": "budget_hi.wav",
    },
    {
        "name": "English - Location qualification",
        "text": (
            "Which location or area are you looking at? "
            "Do you have a preferred neighborhood in mind?"
        ),
        "language_code": "en-IN",
        "speaker": "priya",
        "filename": "location_en.wav",
    },
    {
        "name": "English - Property type qualification",
        "text": (
            "Are you looking for an apartment, villa, or plot? "
            "And how many bedrooms would you need?"
        ),
        "language_code": "en-IN",
        "speaker": "priya",
        "filename": "property_type_en.wav",
    },
    {
        "name": "English - Timeline qualification",
        "text": (
            "When are you planning to make the purchase? "
            "Is it within the next three months, six months, or later?"
        ),
        "language_code": "en-IN",
        "speaker": "priya",
        "filename": "timeline_en.wav",
    },
    {
        "name": "English - Site visit",
        "text": (
            "Would you like to schedule a site visit? "
            "I can arrange a convenient time for you to see the property."
        ),
        "language_code": "en-IN",
        "speaker": "priya",
        "filename": "site_visit_en.wav",
    },
    {
        "name": "Hindi - Site visit",
        "text": (
            "\u0915\u094d\u092f\u093e \u0906\u092a "
            "\u0938\u093e\u0907\u091f \u0935\u093f\u091c\u093f\u091f "
            "\u0915\u093e \u0938\u092e\u092f \u0915\u0930\u0928\u093e "
            "\u091a\u093e\u0939\u0947\u0902\u0917\u0947? "
            "\u092e\u0948\u0902 \u0906\u092a\u0915\u0947 \u0932\u093f\u090f "
            "\u0938\u0941\u0935\u093f\u0927\u093e \u0938\u092e\u092f "
            "\u0915\u0930 \u0938\u0915\u0924\u0940 \u0939\u0942\u0902\u0964"
        ),
        "language_code": "hi-IN",
        "speaker": "priya",
        "filename": "site_visit_hi.wav",
    },
]


def run_test(
    tts: SarvamTTSProvider,
    stt: SarvamSTTProvider | None,
    case: dict,
) -> dict:
    """Run a single TTS test case, optionally followed by STT round-trip."""
    result = {
        "name": case["name"],
        "text": case["text"],
        "language_code": case["language_code"],
        "tts_success": False,
        "tts_latency_ms": 0.0,
        "tts_error": None,
        "audio_file": None,
        "stt_success": False,
        "stt_latency_ms": 0.0,
        "stt_transcript": None,
        "stt_language": None,
        "stt_error": None,
    }

    print(f"\n{'='*60}")
    print(f"TEST: {case['name']}")
    print(f"Text: {case['text'][:80]}...")
    print(f"Lang: {case['language_code']}, Speaker: {case['speaker']}")
    print(f"{'='*60}")

    # TTS
    print(f"\n  TTS: Synthesizing...", end=" ", flush=True)
    tts_result = tts.synthesize(
        text=case["text"],
        language_code=case["language_code"],
        speaker=case["speaker"],
    )
    result["tts_success"] = tts_result.success
    result["tts_latency_ms"] = tts_result.latency_ms
    result["tts_error"] = tts_result.error

    if tts_result.success and tts_result.audio_bytes:
        audio_path = OUTPUT_DIR / case["filename"]
        audio_path.write_bytes(tts_result.audio_bytes)
        result["audio_file"] = str(audio_path)
        print(f"OK ({len(tts_result.audio_bytes)} bytes, {tts_result.latency_ms:.0f}ms)")
        print(f"  TTS: Saved to {audio_path}")

        # STT round-trip
        if stt:
            print(f"  STT: Transcribing...", end=" ", flush=True)
            stt_result = stt.transcribe(
                audio_bytes=tts_result.audio_bytes,
                language_code=case["language_code"],
            )
            result["stt_success"] = stt_result.success
            result["stt_latency_ms"] = stt_result.latency_ms
            result["stt_transcript"] = stt_result.transcript
            result["stt_language"] = stt_result.language_code
            result["stt_error"] = stt_result.error

            if stt_result.success:
                print(f"OK ({stt_result.latency_ms:.0f}ms)")
                print(f"  STT: '{stt_result.transcript}'")
                print(f"  STT: Detected language: {stt_result.language_code}")
            else:
                print(f"FAIL: {stt_result.error}")
    else:
        print(f"FAIL: {tts_result.error}")

    return result


def main():
    print("=" * 60)
    print("SARVAM VOICE QUALITY TEST")
    print("=" * 60)

    if not os.getenv("SARVAM_API_KEY"):
        print("\nERROR: SARVAM_API_KEY not set in environment.")
        print("Set it with: export SARVAM_API_KEY=your_key_here")
        sys.exit(1)

    print("\nInitializing TTS provider...")
    try:
        tts = SarvamTTSProvider()
        print("  TTS provider: OK")
    except Exception as e:
        print(f"  TTS provider: FAIL - {e}")
        sys.exit(1)

    stt = None
    print("\nInitializing STT provider...")
    try:
        stt = SarvamSTTProvider()
        print("  STT provider: OK")
    except Exception as e:
        print(f"  STT provider: SKIP - {e}")
        print("  (STT round-trip tests will be skipped)")

    print(f"\nOutput directory: {OUTPUT_DIR}")
    print(f"Test cases: {len(TEST_CASES)}")

    results = []
    for case in TEST_CASES:
        r = run_test(tts, stt, case)
        results.append(r)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    tts_pass = sum(1 for r in results if r["tts_success"])
    stt_pass = sum(1 for r in results if r["stt_success"])
    total = len(results)

    print(f"\nTTS: {tts_pass}/{total} passed")
    print(f"STT: {stt_pass}/{total} passed")

    avg_tts = (
        sum(r["tts_latency_ms"] for r in results if r["tts_success"])
        / max(1, tts_pass)
    )
    avg_stt = (
        sum(r["stt_latency_ms"] for r in results if r["stt_success"])
        / max(1, stt_pass)
    )

    if tts_pass:
        print(f"Avg TTS latency: {avg_tts:.0f}ms")
    if stt_pass:
        print(f"Avg STT latency: {avg_stt:.0f}ms")

    print(f"\nAudio files saved to: {OUTPUT_DIR}")

    # Detailed results table
    print(f"\n{'Name':<35} {'TTS':>5} {'TTS ms':>8} {'STT':>5} {'STT ms':>8}")
    print("-" * 65)
    for r in results:
        tts_status = "OK" if r["tts_success"] else "FAIL"
        stt_status = "OK" if r["stt_success"] else ("SKIP" if not stt else "FAIL")
        print(
            f"{r['name']:<35} {tts_status:>5} {r['tts_latency_ms']:>8.0f} "
            f"{stt_status:>5} {r['stt_latency_ms']:>8.0f}"
        )

    # Errors
    errors = [r for r in results if r["tts_error"] or r["stt_error"]]
    if errors:
        print(f"\nErrors:")
        for r in errors:
            if r["tts_error"]:
                print(f"  {r['name']}: TTS - {r['tts_error']}")
            if r["stt_error"]:
                print(f"  {r['name']}: STT - {r['stt_error']}")

    # Exit code
    if tts_pass == total and (stt is None or stt_pass == total):
        print("\nRESULT: ALL PASS")
        sys.exit(0)
    else:
        print("\nRESULT: SOME FAILURES")
        sys.exit(1)


if __name__ == "__main__":
    main()
