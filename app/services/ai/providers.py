from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re

from app.schemas.call import QualificationResponse


@dataclass(frozen=True)
class LLMReply:
    text: str
    qualification: QualificationResponse


class STTProvider(ABC):
    """Speech-to-text boundary."""

    @abstractmethod
    def transcribe(self, audio: bytes) -> str:
        raise NotImplementedError


class TTSProvider(ABC):
    """Text-to-speech boundary."""

    @abstractmethod
    def synthesize(self, text: str) -> bytes | None:
        raise NotImplementedError


class LLMProvider(ABC):

    @abstractmethod
    def respond(
        self,
        customer_text: str,
        lead_name: str,
        conversation_history: str | None = None,
        lead_context: str | None = None,
    ) -> LLMReply:
        raise NotImplementedError


class MockSTTProvider(STTProvider):

    def transcribe(self, audio: bytes) -> str:
        return audio.decode("utf-8", errors="replace")


class MockTTSProvider(TTSProvider):

    def synthesize(self, text: str) -> bytes | None:
        return None


class TestLLMProvider(LLMProvider):
    """
    Deterministic local qualification engine.

    Used for free/local testing without an OpenAI API key.
    """

    def respond(
        self,
        customer_text: str,
        lead_name: str,
        conversation_history: str | None = None,
        lead_context: str | None = None,
    ) -> LLMReply:

        # =========================================================
        # 0. BUILD COMPLETE CUSTOMER CONTEXT
        # =========================================================

        current_text = customer_text.strip()

        history_text = conversation_history or ""
        lead_context_text = lead_context or ""

        # Use conversation history + current customer message
        # for qualification so previous requirements are preserved.
        analysis_text = " ".join(
            part
            for part in (
                history_text,
                lead_context_text,
                current_text,
            )
            if part
        )

        normalized = analysis_text.lower().strip()
        current_normalized = current_text.lower().strip()

        # =========================================================
        # 1. INTENT DETECTION
        # =========================================================

        rejected = any(
            phrase in current_normalized
            for phrase in (
                "not interested",
                "don't call",
                "do not call",
                "stop calling",
                "remove my number",
                "never call",
            )
        )

        callback_requested = any(
            phrase in current_normalized
            for phrase in (
                "call me",
                "call back",
                "callback",
                "call later",
                "later",
                "tomorrow",
                "another time",
            )
        )

        appointment_requested = any(
            phrase in current_normalized
            for phrase in (
                "appointment",
                "meeting",
                "schedule a demo",
                "book a demo",
                "schedule",
                "property visit",
                "visit properties",
                "visit some properties",
                "site visit",
                "house visit",
            )
        )

        explicit_interest = any(
            phrase in normalized
            for phrase in (
                "interested",
                "i am interested",
                "i'm interested",
                "tell me more",
                "sounds good",
                "need this",
                "yes",
                "i want",
                "i would like",
                "looking for",
                "searching for",
            )
        )

        # =========================================================
        # 2. REQUIREMENT EXTRACTION
        # =========================================================

        requirement = None

        bhk_match = re.search(
            r"\b([1-5])\s*bhk\b",
            normalized,
        )

        if bhk_match:
            requirement = f"{bhk_match.group(1)} BHK residential property"

        elif any(
            phrase in normalized
            for phrase in (
                "property",
                "flat",
                "apartment",
                "house",
                "villa",
                "residential",
            )
        ):
            # Try to keep the useful customer requirement,
            # rather than caller text.
            customer_requirement_match = re.search(
                r"(?:looking for|want|need|searching for)\s+(.+?)(?:\.|$)",
                normalized,
            )

            if customer_requirement_match:
                requirement = customer_requirement_match.group(1).strip()
            else:
                requirement = current_text

        # =========================================================
        # 3. BUDGET EXTRACTION
        # =========================================================

        budget = None

        lakh_match = re.search(
            r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*"
            r"(?:lakh|lac|lakhs|lacs)\b",
            normalized,
        )

        crore_match = re.search(
            r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*"
            r"(?:crore|crores|cr)\b",
            normalized,
        )

        if lakh_match:
            lakh_value = float(lakh_match.group(1))
            budget = str(int(lakh_value * 100000))

        elif crore_match:
            crore_value = float(crore_match.group(1))
            budget = str(int(crore_value * 10000000))

        # Support plain numbers such as 5000000
        if budget is None:

            number_match = re.search(
                r"(?:budget|around|approximately|approx|price)"
                r"\D{0,20}(\d{6,9})",
                normalized,
            )

            if number_match:
                budget = number_match.group(1)

        # =========================================================
        # 4. TIMELINE EXTRACTION
        # =========================================================

        timeline = None

        timeline_patterns = [
            r"within\s+(?:the\s+next\s+)?"
            r"(\d+)\s*(day|days|week|weeks|month|months|year|years)",

            r"in\s+"
            r"(\d+)\s*(day|days|week|weeks|month|months|year|years)",
        ]

        for pattern in timeline_patterns:

            match = re.search(pattern, normalized)

            if match:
                timeline = f"{match.group(1)} {match.group(2)}"
                break

        if timeline is None:

            if "this week" in normalized:
                timeline = "this week"

            elif "next week" in normalized:
                timeline = "next week"

            elif "this month" in normalized:
                timeline = "this month"

            elif "next month" in normalized:
                timeline = "next month"

            elif "tomorrow" in normalized:
                timeline = "tomorrow"

        # =========================================================
        # 5. INTEREST / QUALIFICATION
        # =========================================================

        has_requirement = requirement is not None
        has_budget = budget is not None
        has_timeline = timeline is not None

        interested = (
            not rejected
            and (
                explicit_interest
                or has_requirement
                or appointment_requested
            )
        )

        if rejected:

            qualification_status = "DO_NOT_CONTACT"

        elif appointment_requested:

            qualification_status = "QUALIFIED"

        elif interested and (
            has_requirement
            or has_budget
            or has_timeline
        ):

            qualification_status = "QUALIFIED"

        else:

            qualification_status = "UNKNOWN"

        # =========================================================
        # 6. SCORE
        # =========================================================

        score = 0

        if has_requirement:
            score += 25

        if has_budget:
            score += 20

        if has_timeline:
            score += 20

        if interested:
            score += 10

        if appointment_requested:
            score += 15

        if callback_requested:
            score += 5

        if rejected:
            score = 0

        score = min(score, 100)

        # =========================================================
        # 7. QUALIFICATION RESPONSE
        # =========================================================

        qualification = QualificationResponse(
            interested=interested,
            budget=budget,
            timeline=timeline,
            requirement=requirement,
            decision_maker=None,
            callback_requested=callback_requested,
            appointment_requested=appointment_requested,
            qualification_score=score,
            qualification_status=qualification_status,
        )

        # =========================================================
        # 8. AI RESPONSE
        # =========================================================

        if rejected:

            reply = (
                "Understood. I will not contact you again. "
                "Thank you for your time."
            )

        elif appointment_requested:

            reply = (
                "Great. I have noted your property visit request. "
                "Our team will confirm the suitable properties and timing."
            )

        elif callback_requested:

            reply = (
                "Certainly. I will arrange a follow-up at a suitable time. "
                "Thank you."
            )

        elif (
            interested
            and has_requirement
            and has_budget
            and has_timeline
        ):

            reply = (
                "Thank you for sharing your requirements. "
                "I have noted your property type, budget, and timeline. "
                "Would you like to schedule a property visit?"
            )

        elif interested:

            missing = []

            if not has_requirement:
                missing.append("property type")

            if not has_budget:
                missing.append("budget")

            if not has_timeline:
                missing.append("preferred timeline")

            if missing:

                reply = (
                    "Thanks for your interest. "
                    f"Could you share your {', '.join(missing)}?"
                )

            else:

                reply = (
                    "Thanks for your interest. "
                    "How would you like to proceed?"
                )

        else:

            reply = (
                "Thank you for sharing. "
                "To make sure I provide relevant information, "
                "what type of property are you looking for?"
            )

        # =========================================================
        # 9. RETURN
        # =========================================================

        return LLMReply(
            text=reply,
            qualification=qualification,
        )


def get_llm_provider() -> LLMProvider:

    import os

    mode = os.getenv("LLM_MODE", "test").lower()

    if mode in {"test", "mock", "local"}:
        return TestLLMProvider()

    raise ValueError(
        f"Unsupported LLM_MODE: {mode}. "
        "Configure a production provider first."
    )
