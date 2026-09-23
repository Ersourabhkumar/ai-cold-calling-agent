# Test Plan

**Date:** 2026-09-21

---

## Layer 1: Unit Tests

### Sarvam Provider
- test_sarvam_provider_makes_correct_api_call
- test_sarvam_provider_returns_attempt_id
- test_sarvam_provider_handles_api_error
- test_sarvam_provider_handles_network_timeout
- test_sarvam_provider_passes_lead_context_as_agent_variables
- test_sarvam_provider_sets_webhook_config
- test_sarvam_provider_supports_language_override

### Sarvam Webhook
- test_sarvam_webhook_connected_status
- test_sarvam_webhook_no_answer_status
- test_sarvam_webhook_busy_status
- test_sarvam_webhook_failed_status
- test_sarvam_webhook_extracts_transcript
- test_sarvam_webhook_extracts_agent_variables
- test_sarvam_webhook_handles_duplicate_events
- test_sarvam_webhook_handles_unknown_call
- test_sarvam_webhook_metadata_passthrough

### Sarvam Enrichment
- test_sarvam_enrichment_populates_qualification
- test_sarvam_enrichment_updates_lead_fields
- test_sarvam_enrichment_infers_outcome
- test_sarvam_enrichment_creates_call_messages
- test_sarvam_enrichment_is_idempotent
- test_sarvam_enrichment_skips_non_completed

### Config Validation
- test_config_requires_sarvam_api_key
- test_config_requires_sarvam_org_id
- test_config_requires_sarvam_workspace_id
- test_config_requires_sarvam_app_id
- test_config_requires_sarvam_connection_id

---

## Layer 2: Integration Tests

### Call Flow
- test_lead_creation
- test_campaign_creation
- test_lead_assignment_to_campaign
- test_call_creation
- test_call_dispatch_to_sarvam
- test_call_lifecycle_transitions
- test_webhook_updates_call_status
- test_enrichment_after_completion
- test_followup_created_for_callback
- test_retry_created_for_no_answer

### Webhook Processing
- test_webhook_idempotency
- test_webhook_out_of_order_handling
- test_webhook_metadata_correlation

---

## Layer 3: Mock End-to-End Tests

### Full Flow (Mock Mode)
- test_complete_flow_with_mock_sarvam
- test_lead_to_call_to_enrichment
- test_multiple_calls_same_lead
- test_campaign_with_multiple_leads
- test_retry_after_failure
- test_callback_scheduling

---

## Layer 4: Real Call Tests (After Explicit GO)

### First Real Call
- test_single_lead_real_call
- test_transcript_received
- test_recording_received
- test_qualification_extracted
- test_lead_updated
- test_call_summary_created

---

## Test Commands

```bash
# Run all tests
uv run pytest -q

# Run specific test file
uv run pytest tests/test_sarvam_provider.py -v

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run only Sarvam tests
uv run pytest -k sarvam -v
```
