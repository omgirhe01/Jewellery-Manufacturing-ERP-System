from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import Job, JobStageLog, WeightLog, BarcodeScan, Department, User
from app.services.scale_service import scale_service
from app.services.helpers import log_activity
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


class StageWeightUpdate(BaseModel):
    job_id: int
    stage_log_id: int
    weight: float
    is_weight_in: bool = True   # True = weight_in, False = weight_out
    is_manual: bool = False


@router.post("/weight/log")
def log_weight(data: WeightLogCreate, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """Log a weight reading for a job stage"""
    net = round(data.gross_weight - data.tare_weight, 4)
    log = WeightLog(
        job_id=data.job_id, stage_log_id=data.job_stage_id,
        department_id=data.department_id,
        gross_weight=data.gross_weight, tare_weight=data.tare_weight, net_weight=net,
        scale_type="Manual" if data.is_manual else ("Simulation" if data.is_simulated else "USB"),
        is_manual_override=data.is_manual,
        operator_id=current_user.id
    )
    db.add(log)

    # Update stage weight_in if not already set
    if data.job_stage_id:
        stage = db.query(JobStageLog).filter(JobStageLog.id == data.job_stage_id).first()
        if stage and not stage.weight_in:
            stage.weight_in = net
            stage.operator_id = current_user.id

    db.commit()
    return {"net_weight": net, "log_id": log.id, "message": "Weight logged"}


@router.post("/weight/stage-update")
def update_stage_weight(data: StageWeightUpdate, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Set weight_in or weight_out for a specific stage log and calculate variance"""
    stage = db.query(JobStageLog).options(joinedload(JobStageLog.job)).filter(
        JobStageLog.id == data.stage_log_id,
        JobStageLog.job_id == data.job_id
    ).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage log not found")

    # Log the weight reading
    log = WeightLog(
        job_id=data.job_id, stage_log_id=data.stage_log_id,
        department_id=stage.department_id,
        gross_weight=data.weight, tare_weight=0, net_weight=data.weight,
        scale_type="Manual" if data.is_manual else "USB",
        is_manual_override=data.is_manual,
        operator_id=current_user.id
    )
    db.add(log)

    if data.is_weight_in:
        stage.weight_in = data.weight
        stage.operator_id = current_user.id
        if not stage.started_at:
            stage.started_at = datetime.utcnow()
    else:
        stage.weight_out = data.weight
        # Calculate variance if weight_in exists
        if stage.weight_in:
            w_in = float(stage.weight_in)
            variance = round(w_in - data.weight, 4)
            stage.weight_variance = variance
            stage.variance_pct = round((variance / w_in) * 100, 3) if w_in > 0 else 0

    # Also update job current_weight if this is weight_out
    if not data.is_weight_in:
        job = db.query(Job).filter(Job.id == data.job_id).first()
        if job:
            job.current_weight = data.weight

    db.commit()
    db.refresh(stage)
    return {
        "stage_log_id": stage.id,
        "weight_in": float(stage.weight_in) if stage.weight_in else None,
        "weight_out": float(stage.weight_out) if stage.weight_out else None,
        "variance": float(stage.weight_variance) if stage.weight_variance else None,
        "variance_pct": float(stage.variance_pct) if stage.variance_pct else None,
        "message": "Weight updated"
    }


@router.post("/weight/simulate")
async def simulate_weight(data: SimulateWeightRequest, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Simulate scale reading and auto-log it"""
    reading = await scale_service.read_weight(data.expected_weight)
    net = round(reading["weight"] - data.tare_weight, 4)
    log = WeightLog(
        job_id=data.job_id, department_id=data.department_id,
        gross_weight=reading["weight"], tare_weight=data.tare_weight, net_weight=net,
        operator_id=current_user.id, scale_type="Simulation", is_manual_override=False
    )
    db.add(log)
    db.commit()
    return {"simulated_weight": reading["weight"], "net_weight": net,
            "log_id": log.id, "stable": reading.get("stable", True)}


@router.get("/weight/history/{job_id}")
def weight_history(job_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Get all weight logs for a job"""
    logs = db.query(WeightLog).filter(WeightLog.job_id == job_id).order_by(WeightLog.captured_at.desc()).all()
    return [{"id": l.id, "gross": float(l.gross_weight), "tare": float(l.tare_weight),
             "net": float(l.net_weight), "scale_type": l.scale_type, "manual": l.is_manual_override,
             "at": l.captured_at.isoformat() if l.captured_at else None} for l in logs]


@router.post("/barcode/scan")
def scan_barcode(data: ScanEvent, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """
    Process a barcode scan event.
    Returns full job details + current stage info + weight status.
    If department_id matches the job's current stage department, returns active stage log.
    """
    job = db.query(Job).options(
        joinedload(Job.customer),
        joinedload(Job.stage_logs)
    ).filter(Job.barcode == data.barcode).first()

    if not job:
        raise HTTPException(status_code=404, detail="No job found for this barcode")

    # Record the scan
    dept = db.query(Department).filter(Department.id == data.department_id).first()
    scan = BarcodeScan(
        barcode=data.barcode, job_id=job.id,
        scanned_by=current_user.id, department_id=data.department_id,
        scan_type=data.scan_type
    )
    db.add(scan)
    db.commit()

    # Find current active stage log
    active_stage = next(
        (s for s in job.stage_logs if s.status == "In Progress"),
        None
    )

    # Check if this department matches the current stage
    dept_matches = (
        dept is not None and
        active_stage is not None and
        active_stage.department_id == data.department_id
    )

    # Stage weight status
    stage_info = None
    if active_stage:
        stage_info = {
            "stage_log_id": active_stage.id,
            "stage_name": active_stage.stage_name,
            "status": active_stage.status,
            "weight_in": float(active_stage.weight_in) if active_stage.weight_in else None,
            "weight_out": float(active_stage.weight_out) if active_stage.weight_out else None,
            "variance_pct": float(active_stage.variance_pct) if active_stage.variance_pct else None,
            "requires_weight": dept.requires_weight if dept_matches and dept else False,
            "requires_approval": dept.requires_approval if dept_matches and dept else False,
            "dept_matches": dept_matches
        }

    log_activity(db, current_user.id, "Scanned", "Jobs", job.id)

    return {
        "job_id": job.id,
        "job_code": job.job_code,
        "barcode": job.barcode,
        "design_name": job.design_name,
        "metal_type": job.metal_type,
        "target_weight": float(job.target_weight),
        "current_weight": float(job.current_weight or 0),
        "wastage_allowed": float(job.wastage_allowed),
        "current_stage": job.current_stage,
        "status": job.status,
        "priority": job.priority,
        "customer": job.customer.name if job.customer else "",
        "scanned_at_dept": dept.name if dept else "",
        "dept_matches_stage": dept_matches,
        "active_stage": stage_info,
        "scan_warning": None if dept_matches else f"Job is at '{job.current_stage}' stage, not at this department"
    }


@router.get("/stage-logs/{job_id}")
def get_stage_logs(job_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Get all stage logs for a job with weight variance details"""
    logs = db.query(JobStageLog).filter(
        JobStageLog.job_id == job_id
    ).order_by(JobStageLog.id).all()

    return [{
        "id": s.id,
        "stage_name": s.stage_name,
        "department_id": s.department_id,
        "status": s.status,
        "weight_in": float(s.weight_in) if s.weight_in else None,
        "weight_out": float(s.weight_out) if s.weight_out else None,
        "weight_variance": float(s.weight_variance) if s.weight_variance else None,
        "variance_pct": float(s.variance_pct) if s.variance_pct else None,
        "operator_id": s.operator_id,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "approved_by": s.approved_by,
        "notes": s.notes
    } for s in logs]


@router.post("/stage-logs/{stage_log_id}/approve")
def approve_stage(stage_log_id: int, notes: str = "",
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Approve a completed stage"""
    stage = db.query(JobStageLog).filter(JobStageLog.id == stage_log_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage log not found")
    if stage.status != "Completed":
        raise HTTPException(status_code=400, detail="Stage must be Completed before approval")
    stage.approved_by = current_user.id
    stage.approved_at = datetime.utcnow()
    if notes:
        stage.notes = notes
    db.commit()
    log_activity(db, current_user.id, "Approved", "Stage", stage.id)
    return {"message": "Stage approved", "stage_log_id": stage.id}