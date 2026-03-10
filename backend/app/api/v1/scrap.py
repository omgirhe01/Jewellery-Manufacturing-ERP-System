from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import ScrapEntry
from app.services.helpers import generate_batch_id
from pydantic import BaseModel

router = APIRouter(prefix="/scrap", tags=["Scrap Management"])


class ScrapCreate(BaseModel):
    source_department_id: int
    scrap_type: str
    gross_weight: float
    estimated_purity: float
    notes: Optional[str] = None


@router.get("/")
def list_scrap(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = db.query(ScrapEntry).order_by(ScrapEntry.collected_at.desc())
    if status:
        query = query.filter(ScrapEntry.status == status)
    entries = query.all()
    return [
        {
            "id": s.id,
            "batch_id": s.batch_id,
            "scrap_type": s.scrap_type,
            "gross_weight": float(s.gross_weight),
            "estimated_purity": float(s.estimated_purity) * 100 if s.estimated_purity else None,
            "estimated_fine": float(s.estimated_fine_weight) if s.estimated_fine_weight else None,
            "status": s.status,
            "collected_at": s.collected_at.isoformat() if s.collected_at else None,
            "notes": s.notes,
        }
        for s in entries
    ]


@router.post("/")
def create_scrap(
    data: ScrapCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    fine = round(data.gross_weight * data.estimated_purity / 100, 4)
    entry = ScrapEntry(
        batch_id=generate_batch_id("SCRAP"),
        source_department_id=data.source_department_id,
        scrap_type=data.scrap_type,
        gross_weight=data.gross_weight,
        estimated_purity=data.estimated_purity / 100,
        estimated_fine_weight=fine,
        status="Collected",
        collected_by=current_user.id,
        notes=data.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "id": entry.id,
        "batch_id": entry.batch_id,
        "estimated_fine_weight": fine,
        "status": entry.status,
    }


@router.get("/summary")
def scrap_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    total      = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
    total_fine = db.query(func.sum(ScrapEntry.estimated_fine_weight)).scalar() or 0

    by_type = db.query(
        ScrapEntry.scrap_type,
        func.sum(ScrapEntry.gross_weight),
        func.count(ScrapEntry.id)
    ).group_by(ScrapEntry.scrap_type).all()

    by_status = db.query(
        ScrapEntry.status,
        func.count(ScrapEntry.id),
        func.sum(ScrapEntry.gross_weight)
    ).group_by(ScrapEntry.status).all()

    return {
        "total_scrap_weight": float(total),
        "total_fine_weight":  float(total_fine),
        "by_type":   {t: {"weight": float(w), "count": int(c)} for t, w, c in by_type},
        "by_status": {s: {"count": int(c), "weight": float(w or 0)} for s, c, w in by_status},
    }


@router.put("/{scrap_id}/status")
def update_status(
    scrap_id: int,
    status: str = Query(...),
    notes: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    valid = ["Collected", "In Stock", "Sent to Refinery", "Settled"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")
    entry = db.query(ScrapEntry).filter(ScrapEntry.id == scrap_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Scrap entry not found")
    old_status   = entry.status
    entry.status = status
    if notes:
        entry.notes = (entry.notes + "\n" + notes) if entry.notes else notes
    db.commit()
    return {"id": entry.id, "batch_id": entry.batch_id, "old_status": old_status, "new_status": entry.status}


@router.get("/{scrap_id}")
def get_scrap(
    scrap_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    entry = db.query(ScrapEntry).filter(ScrapEntry.id == scrap_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Scrap entry not found")
    return {
        "id": entry.id, "batch_id": entry.batch_id, "scrap_type": entry.scrap_type,
        "gross_weight": float(entry.gross_weight),
        "estimated_purity": float(entry.estimated_purity) * 100 if entry.estimated_purity else None,
        "estimated_fine": float(entry.estimated_fine_weight) if entry.estimated_fine_weight else None,
        "status": entry.status,
        "collected_at": entry.collected_at.isoformat() if entry.collected_at else None,
        "notes": entry.notes,
    }