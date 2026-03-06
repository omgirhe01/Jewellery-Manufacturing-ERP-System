from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from datetime import datetime
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import Job, JobStage, Department, Customer, User
from app.services.barcode_service import barcode_service, JobCodeGenerator
from app.services.helpers import paginate, log_activity
from pydantic import BaseModel
from datetime import date

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobCreate(BaseModel):
    design_name: str
    customer_id: int
    metal_type: str
    target_weight: float
    wastage_allowed: float = 2.50
    order_qty: int = 1
    priority: str = "Normal"
    expected_delivery: Optional[date] = None
    notes: Optional[str] = None


class JobUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
def list_jobs(page: int = Query(1, ge=1), per_page: int = Query(20, le=100),
              status: Optional[str] = None, stage: Optional[str] = None,
              metal_type: Optional[str] = None, q: Optional[str] = None,
              db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Job).options(joinedload(Job.customer))
    if status:  query = query.filter(Job.status == status)
    if stage:   query = query.filter(Job.current_stage == stage)
    if metal_type: query = query.filter(Job.metal_type == metal_type)
    if q:
        query = query.filter(or_(Job.job_code.ilike(f"%{q}%"),
                                  Job.design_name.ilike(f"%{q}%"),
                                  Job.barcode.ilike(f"%{q}%")))
    query = query.order_by(Job.created_at.desc())
    result = paginate(query, page, per_page)
    result["items"] = [_job_dict(j) for j in result["items"]]
    return result


@router.post("/")
def create_job(data: JobCreate, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    if not db.query(Customer).filter(Customer.id == data.customer_id).first():
        raise HTTPException(status_code=404, detail="Customer not found")

    job_code = JobCodeGenerator.generate(db)
    barcode_val, barcode_b64 = barcode_service.generate_job_barcode(job_code)

    job = Job(job_code=job_code, barcode=barcode_val, barcode_image_b64=barcode_b64,
              design_name=data.design_name, customer_id=data.customer_id,
              metal_type=data.metal_type, target_weight=data.target_weight,
              wastage_allowed=data.wastage_allowed, order_qty=data.order_qty,
              priority=data.priority, expected_delivery=data.expected_delivery,
              notes=data.notes, current_stage="Design", status="New",
              created_by=current_user.id)
    db.add(job)
    db.flush()

    # Auto-create all 11 stage records
    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    for i, dept in enumerate(depts):
        stage = JobStage(job_id=job.id, department_id=dept.id, stage_name=dept.name,
                         status="In Progress" if i == 0 else "Pending")
        db.add(stage)

    db.commit()
    db.refresh(job)
    log_activity(db, current_user.id, "Created", "Jobs", job.id)
    return _job_dict(job)


@router.get("/stats")
def job_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total = db.query(Job).count()
    by_status = {s: db.query(Job).filter(Job.status == s).count()
                 for s in ["New","Active","QC Pending","QC Rejected","Completed","Dispatched","On Hold"]}
    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    by_stage = {d.name: db.query(Job).filter(Job.current_stage == d.name).count() for d in depts}
    return {"total": total, "by_status": by_status, "by_stage": by_stage}


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    job = db.query(Job).options(joinedload(Job.customer), joinedload(Job.stages)).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job, include_stages=True)


@router.get("/barcode/{barcode}")
def get_by_barcode(barcode: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    job = db.query(Job).options(joinedload(Job.customer), joinedload(Job.stages)).filter(Job.barcode == barcode).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found for barcode")
    return _job_dict(job, include_stages=True)


@router.put("/{job_id}")
def update_job(job_id: int, data: JobUpdate, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if data.status:   job.status = data.status
    if data.priority: job.priority = data.priority
    if data.notes is not None: job.notes = data.notes
    db.commit()
    log_activity(db, current_user.id, "Updated", "Jobs", job.id)
    return _job_dict(job)


@router.post("/{job_id}/advance-stage")
def advance_stage(job_id: int, weight_out: float = 0, notes: str = "",
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(Job).options(joinedload(Job.stages)).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    stage_names = [d.name for d in depts]
    curr_idx = next((i for i, n in enumerate(stage_names) if n == job.current_stage), -1)

    if curr_idx == -1 or curr_idx >= len(stage_names) - 1:
        raise HTTPException(status_code=400, detail="Already at final stage")

    # Complete current stage
    curr_stage = db.query(JobStage).filter(JobStage.job_id == job_id,
                                            JobStage.stage_name == job.current_stage).first()
    if curr_stage:
        curr_stage.status = "Completed"
        curr_stage.weight_out = weight_out
        curr_stage.completed_at = datetime.utcnow()
        curr_stage.notes = notes
        if curr_stage.weight_in and weight_out:
            curr_stage.weight_variance = float(curr_stage.weight_in) - weight_out
            curr_stage.variance_pct = round((curr_stage.weight_variance / float(curr_stage.weight_in)) * 100, 3)

    # Activate next stage
    next_name = stage_names[curr_idx + 1]
    next_stage = db.query(JobStage).filter(JobStage.job_id == job_id,
                                            JobStage.stage_name == next_name).first()
    if next_stage:
        next_stage.status = "In Progress"
        next_stage.started_at = datetime.utcnow()

    job.current_stage = next_name
    job.current_weight = weight_out
    job.status = "QC Pending" if next_name == "QC" else "Active"
    db.commit()
    return {"message": f"Moved to {next_name}", "current_stage": next_name, "job_id": job.id}


def _job_dict(job: Job, include_stages: bool = False) -> dict:
    d = {
        "id": job.id, "job_code": job.job_code, "barcode": job.barcode,
        "barcode_image_b64": job.barcode_image_b64,
        "design_name": job.design_name,
        "customer_id": job.customer_id,
        "customer_name": job.customer.name if job.customer else "",
        "metal_type": job.metal_type,
        "target_weight": float(job.target_weight),
        "current_weight": float(job.current_weight or 0),
        "wastage_allowed": float(job.wastage_allowed),
        "order_qty": job.order_qty,
        "current_stage": job.current_stage,
        "status": job.status,
        "priority": job.priority,
        "expected_delivery": str(job.expected_delivery) if job.expected_delivery else None,
        "notes": job.notes,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
    if include_stages and job.stages:
        d["stages"] = [
            {"id": s.id, "stage_name": s.stage_name, "status": s.status,
             "weight_in": float(s.weight_in) if s.weight_in else None,
             "weight_out": float(s.weight_out) if s.weight_out else None,
             "variance_pct": float(s.variance_pct) if s.variance_pct else None,
             "started_at": s.started_at.isoformat() if s.started_at else None,
             "completed_at": s.completed_at.isoformat() if s.completed_at else None}
            for s in sorted(job.stages, key=lambda x: x.id)
        ]
    return d
