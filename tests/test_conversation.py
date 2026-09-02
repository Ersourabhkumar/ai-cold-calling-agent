from app.services.ai.providers import TestLLMProvider


def test_test_llm_detects_do_not_call_without_inventing_details():
    reply = TestLLMProvider().respond("Please do not call me again.", "Asha")

    assert reply.qualification.qualification_status == "DO_NOT_CONTACT"
    assert reply.qualification.interested is False
    assert reply.qualification.budget is None
    assert "thank you" in reply.text.lower()


def test_test_llm_returns_structured_appointment_qualification():
    reply = TestLLMProvider().respond("I am interested; can we schedule a demo appointment?", "Asha")

    assert reply.qualification.interested is True
    assert reply.qualification.appointment_requested is True
    assert reply.qualification.qualification_status == "QUALIFIED"
    assert 0 <= reply.qualification.qualification_score <= 100
