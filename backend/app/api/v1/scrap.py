from fastapi import APIRouter, Depends
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
def list_scrap(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    entries = db.query(ScrapEntry).order_by(ScrapEntry.collected_at.desc()).all()
    return [{"id": s.id, "batch_id": s.batch_id, "scrap_type": s.scrap_type,
              "gross_weight": float(s.gross_weight),
              "estimated_purity": float(s.estimated_purity) if s.estimated_purity else None,
              "estimated_fine": float(s.estimated_fine_weight) if s.estimated_fine_weight else None,
              "status": s.status,
              "collected_at": s.collected_at.isoformat() if s.collected_at else None} for s in entries]


@router.post("/")
def create_scrap(data: ScrapCreate, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    fine = round(data.gross_weight * data.estimated_purity / 100, 4)
    entry = ScrapEntry(batch_id=generate_batch_id("SCRAP"),
                        source_department_id=data.source_department_id,
                        scrap_type=data.scrap_type, gross_weight=data.gross_weight,
                        estimated_purity=data.estimated_purity / 100,
                        estimated_fine_weight=fine, status="Collected",
                        collected_by=current_user.id, notes=data.notes)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "batch_id": entry.batch_id, "fine_weight": fine}


@router.get("/summary")
def scrap_summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    total = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
    by_type = db.query(ScrapEntry.scrap_type, func.sum(ScrapEntry.gross_weight)).group_by(ScrapEntry.scrap_type).all()
    return {"total_weight": float(total), "by_type": {t: float(w) for t, w in by_type}}
