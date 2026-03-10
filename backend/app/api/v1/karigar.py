from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import date
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import Karigar, KarigarAssignment, User
from pydantic import BaseModel

router = APIRouter(prefix="/karigars", tags=["Karigar Management"])


class KarigarCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    skill_type: Optional[str] = None
    piece_rate: float = 0
    joined_date: Optional[date] = None
    address: Optional[str] = None


class AssignmentCreate(BaseModel):
    karigar_id: int
    job_id: int
    stage_log_id: Optional[int] = None
    pieces_assigned: int = 1
    metal_issued: float = 0.0


@router.get("/")
def list_karigars(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    result = []
    for k in karigars:
        pending = db.query(KarigarAssignment).filter(
            KarigarAssignment.karigar_id == k.id,
            KarigarAssignment.status.in_(["Assigned","In Progress"])
        ).count()
        result.append({"id": k.id, "code": k.karigar_code, "name": k.name,
                        "phone": k.phone, "skill": k.skill_type,
                        "piece_rate": float(k.piece_rate), "pending_jobs": pending})
    return result


@router.post("/")
def create_karigar(data: KarigarCreate, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    count = db.query(Karigar).count() + 1
    k = Karigar(karigar_code=f"KAR-{str(count).zfill(3)}", name=data.name,
                phone=data.phone, skill_type=data.skill_type,
                piece_rate=data.piece_rate, joined_date=data.joined_date, address=data.address)
    db.add(k)
    db.commit()
    db.refresh(k)
    return {"id": k.id, "code": k.karigar_code, "name": k.name}


@router.post("/assign")
def assign_work(data: AssignmentCreate, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    k = db.query(Karigar).filter(Karigar.id == data.karigar_id).first()
    if not k:
        raise HTTPException(status_code=404, detail="Karigar not found")
    labour_cost = float(k.piece_rate) * data.pieces_assigned
    assignment = KarigarAssignment(karigar_id=data.karigar_id, job_id=data.job_id,
                                    stage_log_id=data.stage_log_id,
                                    pieces_assigned=data.pieces_assigned,
                                    metal_issued=data.metal_issued, labour_cost=labour_cost)
    db.add(assignment)
    db.commit()
    return {"message": "Work assigned", "labour_cost": labour_cost}


@router.get("/report/wages")
def wage_report(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    report = []
    for k in karigars:
        total = db.query(func.sum(KarigarAssignment.labour_cost)).filter(
            KarigarAssignment.karigar_id == k.id).scalar() or 0
        pending = db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(
            KarigarAssignment.karigar_id == k.id,
            KarigarAssignment.status != "Completed").scalar() or 0
        report.append({"karigar": k.name, "code": k.karigar_code, "skill": k.skill_type,
                        "total_wages": float(total), "pending_pieces": int(pending or 0)})
    return report


@router.get("/performance")
def performance(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Karigar productivity report"""
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    result = []
    for k in karigars:
        total_assigned = db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(
            KarigarAssignment.karigar_id == k.id).scalar() or 0
        total_completed = db.query(func.sum(KarigarAssignment.pieces_completed)).filter(
            KarigarAssignment.karigar_id == k.id).scalar() or 0
        pct = round((int(total_completed) / int(total_assigned) * 100), 1) if total_assigned else 0
        result.append({"karigar": k.name, "code": k.karigar_code,
                        "assigned": int(total_assigned), "completed": int(total_completed),
                        "completion_pct": pct})
    return result