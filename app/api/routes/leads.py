from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.phone_validation import validate_phone
from app.database.connection import get_db
from app.schemas.lead import LeadCreate, LeadImportResponse, LeadResponse, LeadUpdate
from app.services.lead_service import (
    create_lead,
    delete_lead,
    get_lead,
    get_leads,
    update_lead,
)

router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
)


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lead_endpoint(
    data: LeadCreate,
    db: Session = Depends(get_db),
):
    return create_lead(db, data)


@router.get(
    "",
    response_model=list[LeadResponse],
)
def list_leads_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_leads(db, skip=skip, limit=limit)


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
)
def get_lead_endpoint(
    lead_id: int,
    db: Session = Depends(get_db),
):
    lead = get_lead(db, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    return lead


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
)
def update_lead_endpoint(
    lead_id: int,
    data: LeadUpdate,
    db: Session = Depends(get_db),
):
    lead = get_lead(db, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    return update_lead(db, lead, data)


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_lead_endpoint(
    lead_id: int,
    db: Session = Depends(get_db),
):
    lead = get_lead(db, lead_id)

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    delete_lead(db, lead)


@router.post(
    "/import",
    response_model=LeadImportResponse,
)
def import_leads_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Bulk-import leads from a CSV file.

    Columns: name, phone (required); email, city, source, requirement,
    budget, timeline (optional). Phone numbers are validated strictly;
    bad rows are reported, never created.
    """
    import csv
    import io

    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(
            status_code=400, detail="Only .csv files are accepted"
        )
    try:
        content = file.file.read().decode("utf-8-sig")
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not read CSV: {exc}"
        ) from exc

    created_ids: list[int] = []
    failed: list[dict] = []
    total = 0
    for idx, row in enumerate(csv.DictReader(io.StringIO(content)), start=2):
        total += 1
        name = (row.get("name") or "").strip()
        phone_raw = (row.get("phone") or "").strip()
        if len(name) < 2:
            failed.append(
                {"row": idx, "error": "name must be at least 2 characters"}
            )
            continue
        check = validate_phone(phone_raw)
        if not check.valid:
            failed.append({"row": idx, "error": check.reason or "invalid phone"})
            continue
        try:
            lead = create_lead(
                db,
                LeadCreate(
                    name=name,
                    phone=check.normalized or phone_raw,
                    email=(row.get("email") or "").strip() or None,
                    city=(row.get("city") or "").strip() or None,
                    source=(row.get("source") or "").strip() or "csv",
                    requirement=(row.get("requirement") or "").strip() or None,
                    budget=(row.get("budget") or "").strip() or None,
                    timeline=(row.get("timeline") or "").strip() or None,
                ),
            )
            created_ids.append(lead.id)
        except Exception as exc:
            db.rollback()
            failed.append({"row": idx, "error": str(exc)[:200]})
    return {
        "total": total,
        "created": len(created_ids),
        "created_ids": created_ids,
        "failed": failed,
    }