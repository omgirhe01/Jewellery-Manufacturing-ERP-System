from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import Job, JobStage, WeightLog, BarcodeScan, Department, User
from app.services.scale_service import scale_service
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/production", tags=["Production"])


class WeightLogCreate(BaseModel):
    job_id: int
    department_id: int
    gross_weight: float
    tare_weight: float = 0.0
    job_stage_id: Optional[int] = None
    is_manual: bool = False
    is_simulated: bool = False
    scale_id: Optional[str] = None


class ScanEvent(BaseModel):
    barcode: str
    department_id: int
    scan_type: str = "Check-In"


class SimulateWeightRequest(BaseModel):
    job_id: int
    department_id: int
    expected_weight: float = 10.0
    tare_weight: float = 0.0


@router.post("/weight/log")
def log_weight(data: WeightLogCreate, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """Log a weight reading for a job stage"""
    net = round(data.gross_weight - data.tare_weight, 4)
    log = WeightLog(job_id=data.job_id, job_stage_id=data.job_stage_id,
                    department_id=data.department_id, gross_weight=data.gross_weight,
                    tare_weight=data.tare_weight, net_weight=net, scale_id=data.scale_id,
                    operator_id=current_user.id, is_manual=data.is_manual,
                    is_simulated=data.is_simulated)
    db.add(log)

    # Update stage weight_in if not already set
    if data.job_stage_id:
        stage = db.query(JobStage).filter(JobStage.id == data.job_stage_id).first()
        if stage and not stage.weight_in:
            stage.weight_in = net

    db.commit()
    return {"net_weight": net, "log_id": log.id, "message": "Weight logged"}


@router.post("/weight/simulate")
async def simulate_weight(data: SimulateWeightRequest, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Simulate scale reading and auto-log it"""
    reading = await scale_service.read_weight(data.expected_weight)
    net = round(reading["weight"] - data.tare_weight, 4)

    log = WeightLog(job_id=data.job_id, department_id=data.department_id,
                    gross_weight=reading["weight"], tare_weight=data.tare_weight,
                    net_weight=net, operator_id=current_user.id,
                    is_manual=False, is_simulated=True, scale_id="SIM-01")
    db.add(log)
    db.commit()
    return {"simulated_weight": reading["weight"], "net_weight": net, "log_id": log.id,
            "stable": reading.get("stable", True)}


@router.get("/weight/history/{job_id}")
def weight_history(job_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Get all weight logs for a job"""
    logs = db.query(WeightLog).filter(WeightLog.job_id == job_id).order_by(WeightLog.captured_at.desc()).all()
    return [{"id": l.id, "gross": float(l.gross_weight), "tare": float(l.tare_weight),
             "net": float(l.net_weight), "simulated": l.is_simulated, "manual": l.is_manual,
             "at": l.captured_at.isoformat() if l.captured_at else None} for l in logs]


@router.post("/barcode/scan")
def scan_barcode(data: ScanEvent, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Process a barcode scan event"""
    job = db.query(Job).filter(Job.barcode == data.barcode).first()
    if not job:
        raise HTTPException(status_code=404, detail="No job found for this barcode")

    scan = BarcodeScan(barcode=data.barcode, job_id=job.id, scanned_by=current_user.id,
                       department_id=data.department_id, scan_type=data.scan_type)
    db.add(scan)
    db.commit()
    return {"job_id": job.id, "job_code": job.job_code, "design": job.design_name,
            "current_stage": job.current_stage, "status": job.status,
            "customer": job.customer.name if job.customer else ""}
