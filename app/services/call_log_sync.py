from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.enums import CallStatus
from app.services.calling import get_calling_provider
from app.services.calling.tabbly_provider import TabblyCallingProvider
from app.services.tabby_enrichment import apply_tabby_enrichment
from app.services.tabbly_webhook_service import process_tabbly_webhook

logger = logging.getLogger(__name__)


class CallLogSyncError(RuntimeError):
    """Raised when Tabbly call-log reconciliation cannot be initialised."""


def sync_tabby_call_logs(
    db: Session,
    *,
    limit: int = 50,
) -> dict:
    """Reconcile persisted calls against recent Tabbly call logs.

    This is the poll-based companion to the push webhook: when webhooks cannot
    be delivered to a public URL (no public host, no signature), a scheduler
    can run this at a fixed interval to converge terminal statuses, transcripts,
    qualification data and call outcomes.

    Requires provider tabbly with TABBLY_ORGANIZATION_ID configured.
    """
    provider = get_calling_provider()

    if not isinstance(provider, TabblyCallingProvider):
        raise CallLogSyncError(
            f"Call-log sync requires TELEPHONY_PROVIDER=tabbly; "
            f"got {type(provider).__name__}"
        )

    logs = provider.get_call_logs(limit=limit)

    applied = 0
    skipped = 0
    matched = 0
    enriched = 0

    for log in logs:
        payload = TabblyCallingProvider.webhook_payload(log)
        if payload is None:
            skipped += 1
            continue

        # Feeding provider call logs through the same flexible parser the
        # webhook uses keeps reconciliation consistent and idempotent.
        try:
            result = process_tabbly_webhook(db, payload)
        except Exception:
            logger.exception(
                "Call-log sync failed to process a Tabbly log row; skipping.",
            )
            skipped += 1
            continue

        if result.get("handled"):
            applied += 1
        elif result.get("call_id"):
            matched += 1

        # process_tabby_webhook resolves answered-with-conversation rows to
        # COMPLETED internally, so enrichment only depends on the final state.
        if result.get("call_id"):
            call = db.get(Call, int(result["call_id"]))
            if call is not None and call.status == CallStatus.COMPLETED:
                try:
                    enrichment = apply_tabby_enrichment(db, call, payload)
                    if enrichment.get("enriched"):
                        enriched += 1
                except Exception:
                    logger.exception(
                        "Call-log sync failed to enrich call %s; skipping.",
                        call.id,
                    )

    return {
        "total": len(logs),
        "applied": applied,
        "matched": matched,
        "enriched": enriched,
        "skipped": skipped,
    }