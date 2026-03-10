from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel
import base64
import os
import io
from datetime import date as date_type

from app.core.database import get_db
from app.core.security import (
    get_current_user, hash_password, verify_password,
    create_access_token, require_roles
)
from app.models.all_models import (
    User, Role, Customer, Job, Department, JobStageLog,
    WeightLog, BarcodeScans, Karigar, KarigarAssignment,
    MetalStock, MetalLedger, ScrapEntry, RefineryDispatch,
    RefinerySettlement, InventoryItem, InventoryTransaction,
    FinishedGood, JobCost, ActivityLog, Notification, SystemSetting,
    Design
)
from app.services.helpers import (
    generate_job_code, generate_barcode_value, generate_batch_id,
    generate_dispatch_no, generate_karigar_code, paginate,
    log_activity, get_setting, fmt_weight
)
from app.services.scale_service import scale_service
from app.services.barcode_service import barcode_service


# ============================================================
# AUTH ROUTER
# ============================================================
auth_router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


@auth_router.post("/login")
def login(response: Response, data: LoginRequest, db: Session = Depends(get_db)):
    """Login with username/password - sets session cookie and returns JWT"""
    user = db.query(User).filter(
        User.username == data.username, User.is_active == True
    ).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Update last login timestamp
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token({"sub": user.username, "role": user.role.name})

    # Set httpOnly cookie for browser sessions
    response.set_cookie(
        key="session_token", value=token,
        httponly=True, max_age=86400, samesite="lax"
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id, "name": user.name,
            "username": user.username, "role": user.role.name
        }
    }


@auth_router.post("/logout")
def logout(response: Response):
    """Clear session cookie"""
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}


@auth_router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {
        "id": current_user.id, "name": current_user.name,
        "email": current_user.email, "username": current_user.username,
        "role": current_user.role.name if current_user.role else None,
        "is_active": current_user.is_active
    }


# ============================================================
# JOBS ROUTER
# ============================================================
jobs_router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])


class JobCreateRequest(BaseModel):
    design_name: str
    customer_id: int
    metal_type: str
    target_weight: float
    wastage_allowed: float = 2.50
    order_qty: int = 1
    priority: str = "Normal"
    expected_delivery: Optional[date] = None
    notes: Optional[str] = None


class JobUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    expected_delivery: Optional[date] = None


@jobs_router.get("/")
def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    status: Optional[str] = None,
    stage: Optional[str] = None,
    customer_id: Optional[int] = None,
    metal_type: Optional[str] = None,
    priority: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant", "QC Officer"))
):
    """List all jobs with filtering and pagination"""
    query = db.query(Job).options(joinedload(Job.customer))

    if status:
        query = query.filter(Job.status == status)
    if stage:
        query = query.filter(Job.current_stage == stage)
    if customer_id:
        query = query.filter(Job.customer_id == customer_id)
    if metal_type:
        query = query.filter(Job.metal_type == metal_type)
    if priority:
        query = query.filter(Job.priority == priority)
    if q:
        query = query.filter(or_(
            Job.job_code.ilike(f"%{q}%"),
            Job.design_name.ilike(f"%{q}%"),
            Job.barcode.ilike(f"%{q}%")
        ))

    query = query.order_by(Job.created_at.desc())
    result = paginate(query, page, per_page)
    result["items"] = [_job_dict(j) for j in result["items"]]
    return result


@jobs_router.post("/")
def create_job(
    data: JobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Create new job - auto-generates job code, barcode, and all 11 stage records"""
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    job_code = generate_job_code(db)
    barcode_val = generate_barcode_value(job_code, data.metal_type, data.order_qty)
    _, barcode_img = barcode_service.generate_job_barcode(job_code)

    job = Job(
        job_code=job_code,
        barcode=barcode_val,
        barcode_image_b64=barcode_img,
        design_name=data.design_name,
        customer_id=data.customer_id,
        metal_type=data.metal_type,
        target_weight=data.target_weight,
        wastage_allowed=data.wastage_allowed,
        order_qty=data.order_qty,
        priority=data.priority,
        expected_delivery=data.expected_delivery,
        notes=data.notes,
        current_stage="Design",
        status="New",
        created_by=current_user.id
    )
    db.add(job)
    db.flush()  # Get job.id before creating stage logs

    # Auto-create all 11 stage log records
    departments = db.query(Department).filter(
        Department.is_active == True
    ).order_by(Department.stage_order).all()

    for dept in departments:
        stage = JobStageLog(
            job_id=job.id,
            department_id=dept.id,
            stage_name=dept.name,
            status="In Progress" if dept.stage_order == 1 else "Pending"
        )
        db.add(stage)

    db.commit()
    db.refresh(job)

    log_activity(db, current_user.id, "Created", "Jobs", job.id,
                 new_val={"job_code": job_code, "metal": data.metal_type})
    db.commit()

    return _job_dict(job)


@jobs_router.get("/stats")
def job_stats(db: Session = Depends(get_db), current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant", "QC Officer"))):
    """Job overview statistics for dashboard"""
    total = db.query(Job).count()
    by_status = {
        s: db.query(Job).filter(Job.status == s).count()
        for s in ["New", "Active", "QC Pending", "QC Rejected", "Completed", "Dispatched", "On Hold"]
    }
    departments = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    pipeline = [
        {"name": d.name, "count": db.query(Job).filter(Job.current_stage == d.name).count()}
        for d in departments
    ]
    return {"total": total, "by_status": by_status, "pipeline": pipeline}


@jobs_router.get("/barcode/{barcode}")
def get_job_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator", "QC Officer"))
):
    """Lookup job by barcode - used by scanner"""
    job = db.query(Job).options(
        joinedload(Job.customer), joinedload(Job.stage_logs)
    ).filter(Job.barcode == barcode).first()

    if not job:
        raise HTTPException(status_code=404, detail="No job found for this barcode")

    # Log the scan event
    scan = BarcodeScans(
        barcode=barcode, job_id=job.id,
        scanned_by=current_user.id, scan_source="Manual"
    )
    db.add(scan)
    db.commit()

    return _job_dict(job, include_stages=True)


@jobs_router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant", "QC Officer"))
):
    """Get single job with full stage history"""
    job = db.query(Job).options(
        joinedload(Job.customer), joinedload(Job.stage_logs)
    ).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job, include_stages=True, include_barcode=True)


@jobs_router.put("/{job_id}")
def update_job(
    job_id: int,
    data: JobUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Update job status, priority, or notes"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if data.status:
        job.status = data.status
    if data.priority:
        job.priority = data.priority
    if data.notes is not None:
        job.notes = data.notes
    if data.expected_delivery:
        job.expected_delivery = data.expected_delivery

    job.updated_by = current_user.id
    db.commit()
    return _job_dict(job)


@jobs_router.post("/{job_id}/advance-stage")
def advance_stage(
    job_id: int,
    weight_out: float = 0,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator", "QC Officer"))
):
    """Advance job to next production stage"""
    job = db.query(Job).options(joinedload(Job.stage_logs)).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get ordered list of department names
    departments = db.query(Department).filter(
        Department.is_active == True
    ).order_by(Department.stage_order).all()
    dept_names = [d.name for d in departments]

    current_idx = next((i for i, n in enumerate(dept_names) if n == job.current_stage), -1)
    if current_idx == -1 or current_idx >= len(dept_names) - 1:
        raise HTTPException(status_code=400, detail="Job is already at final stage")

    # Complete current stage log
    current_stage_log = db.query(JobStageLog).filter(
        JobStageLog.job_id == job_id,
        JobStageLog.stage_name == job.current_stage
    ).first()

    if current_stage_log:
        current_stage_log.status = "Completed"
        current_stage_log.weight_out = weight_out
        current_stage_log.completed_at = datetime.utcnow()
        current_stage_log.notes = notes

        # Calculate variance from weight_in
        if current_stage_log.weight_in and weight_out:
            variance = float(current_stage_log.weight_in) - weight_out
            current_stage_log.weight_variance = round(variance, 4)
            if float(current_stage_log.weight_in) > 0:
                current_stage_log.variance_pct = round(
                    variance / float(current_stage_log.weight_in) * 100, 3
                )

    # Activate next stage
    next_stage_name = dept_names[current_idx + 1]
    next_stage_log = db.query(JobStageLog).filter(
        JobStageLog.job_id == job_id,
        JobStageLog.stage_name == next_stage_name
    ).first()

    if next_stage_log:
        next_stage_log.status = "In Progress"
        next_stage_log.started_at = datetime.utcnow()
        next_stage_log.weight_in = weight_out  # Output of previous = input of next

    # Update job's current stage and status
    job.current_stage = next_stage_name
    job.current_weight = weight_out
    job.updated_by = current_user.id

    if next_stage_name == "Quality Control":
        job.status = "QC Pending"
    elif next_stage_name == "Dispatch":
        job.status = "Completed"
    else:
        job.status = "Active"

    db.commit()

    log_activity(db, current_user.id, f"Advanced to {next_stage_name}", "Jobs", job_id)
    db.commit()

    return {
        "message": f"Job advanced to {next_stage_name}",
        "current_stage": next_stage_name,
        "status": job.status
    }


@jobs_router.post("/{job_id}/approve-stage")
def approve_stage(
    job_id: int,
    stage_log_id: int = None,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "QC Officer"))
):
    """Approve current stage - required before advancing (for stages with requires_approval=True)"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Find the stage log to approve
    if stage_log_id:
        stage_log = db.query(JobStageLog).filter(
            JobStageLog.id == stage_log_id,
            JobStageLog.job_id == job_id
        ).first()
    else:
        stage_log = db.query(JobStageLog).filter(
            JobStageLog.job_id == job_id,
            JobStageLog.stage_name == job.current_stage
        ).first()

    if not stage_log:
        raise HTTPException(status_code=404, detail="Stage log not found")

    if stage_log.status == "Completed":
        raise HTTPException(status_code=400, detail="Stage already completed")

    stage_log.approved_by = current_user.id
    stage_log.approved_at = datetime.utcnow()
    if notes:
        stage_log.notes = notes

    db.commit()
    log_activity(db, current_user.id, f"Approved stage {stage_log.stage_name}", "Jobs", job_id)
    db.commit()

    return {
        "message": f"Stage '{stage_log.stage_name}' approved",
        "approved_by": current_user.name,
        "approved_at": stage_log.approved_at.isoformat()
    }


@jobs_router.post("/{job_id}/reject-stage")
def reject_stage(
    job_id: int,
    reason: str,
    stage_log_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "QC Officer"))
):
    """Reject current stage - sends job back with reason"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if stage_log_id:
        stage_log = db.query(JobStageLog).filter(
            JobStageLog.id == stage_log_id,
            JobStageLog.job_id == job_id
        ).first()
    else:
        stage_log = db.query(JobStageLog).filter(
            JobStageLog.job_id == job_id,
            JobStageLog.stage_name == job.current_stage
        ).first()

    if not stage_log:
        raise HTTPException(status_code=404, detail="Stage log not found")

    stage_log.status = "Rejected"
    stage_log.rejection_reason = reason
    stage_log.approved_by = current_user.id
    stage_log.approved_at = datetime.utcnow()

    job.status = "QC Rejected" if job.current_stage == "Quality Control" else "On Hold"
    job.updated_by = current_user.id

    db.commit()
    log_activity(db, current_user.id, f"Rejected stage {stage_log.stage_name}: {reason}", "Jobs", job_id)
    db.commit()

    return {
        "message": f"Stage '{stage_log.stage_name}' rejected",
        "reason": reason,
        "job_status": job.status
    }


def _job_dict(job: Job, include_stages=False, include_barcode=False) -> dict:
    """Convert Job ORM object to API response dictionary"""
    d = {
        "id": job.id,
        "job_code": job.job_code,
        "barcode": job.barcode,
        "design_name": job.design_name,
        "customer_id": job.customer_id,
        "customer_name": job.customer.name if job.customer else "",
        "metal_type": job.metal_type,
        "target_weight": float(job.target_weight),
        "current_weight": float(job.current_weight) if job.current_weight else 0.0,
        "wastage_allowed": float(job.wastage_allowed),
        "order_qty": job.order_qty,
        "current_stage": job.current_stage,
        "status": job.status,
        "priority": job.priority,
        "expected_delivery": str(job.expected_delivery) if job.expected_delivery else None,
        "notes": job.notes,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
    if include_barcode:
        d["barcode_image"] = job.barcode_image_b64
    if include_stages and job.stage_logs:
        d["stages"] = [
            {
                "id": s.id, "stage_name": s.stage_name, "status": s.status,
                "weight_in": float(s.weight_in) if s.weight_in else None,
                "weight_out": float(s.weight_out) if s.weight_out else None,
                "weight_variance": float(s.weight_variance) if s.weight_variance else None,
                "variance_pct": float(s.variance_pct) if s.variance_pct else None,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "notes": s.notes
            }
            for s in sorted(job.stage_logs, key=lambda x: x.id)
        ]
    return d


# ============================================================
# SCALE ROUTER — Production Ready (RS232 + Simulation)
# ============================================================
scale_router = APIRouter(prefix="/api/v1/scale", tags=["Weighing Scale"])


@scale_router.get("/status")
async def scale_status(current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))):
    """Get scale connection status, mode, tare, last reading"""
    return await scale_service.get_status()


@scale_router.post("/read-weight")
async def read_weight(
    expected_weight: float = Query(10.0, description="Expected weight (used in simulation)"),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))
):
    """
    Read weight from scale.
    - Waits for STABLE reading (critical for gold accuracy)
    - Returns gross, net, tare, stable flag, attempts count
    """
    result = await scale_service.read_weight(expected_weight)
    return result


@scale_router.post("/tare")
async def set_tare(
    tare_value: Optional[float] = Query(None, description="Tare value in grams. If not given, reads scale now."),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))
):
    """
    Set tare weight.
    - Pass tare_value to set directly
    - Pass nothing to read scale now and use as tare
    """
    if tare_value is not None:
        scale_service.set_tare(tare_value)
        return {"message": f"Tare set to {tare_value}g", "tare": tare_value}
    else:
        reading = await scale_service.read_weight()
        tare = reading.get("gross_weight", 0.0)
        scale_service.set_tare(tare)
        return {"message": f"Tare set from scale: {tare}g", "tare": tare}


@scale_router.post("/clear-tare")
async def clear_tare(current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))):
    """Clear tare weight back to zero"""
    scale_service.clear_tare()
    return {"message": "Tare cleared", "tare": 0.0}


@scale_router.get("/detect-port")
async def detect_port(current_user: User = Depends(require_roles("Admin"))):
    """
    List all available COM/serial ports on server PC.
    Useful to find which port the RS232 scale is connected to.
    """
    return await scale_service.detect_port()


@scale_router.post("/log-weight")
async def log_weight(
    job_id: int,
    department_id: int,
    gross_weight: float,
    tare_weight: float = 0.0,
    is_manual: bool = False,
    stage_log_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))
):
    """
    Log a confirmed weight reading against a job + department.
    Only STABLE readings should be passed here from frontend.
    """
    net_weight = round(gross_weight - tare_weight, 4)

    # Check admin setting: block manual weight entry if disabled
    if is_manual:
        setting = db.query(SystemSetting).filter(
            SystemSetting.setting_key == "allow_manual_weight"
        ).first()
        if setting and setting.setting_value == "false":
            raise HTTPException(
                status_code=403,
                detail="Manual weight entry is disabled by admin. Use scale to capture weight."
            )

    scale_mode = "Manual" if is_manual else (
        "Simulation" if scale_service.simulation_mode else "RS232"
    )

    log = WeightLog(
        job_id=job_id,
        stage_log_id=stage_log_id,
        department_id=department_id,
        gross_weight=gross_weight,
        tare_weight=tare_weight,
        net_weight=net_weight,
        scale_type=scale_mode,
        is_manual_override=is_manual,
        operator_id=current_user.id
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "message": "Weight logged successfully",
        "log_id": log.id,
        "gross_weight": gross_weight,
        "tare_weight": tare_weight,
        "net_weight": net_weight,
        "scale_type": scale_mode,
    }


@scale_router.get("/settings")
def get_scale_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))
):
    """Get scale-related system settings"""
    setting = db.query(SystemSetting).filter(
        SystemSetting.setting_key == "allow_manual_weight"
    ).first()
    return {
        "allow_manual_weight": setting.setting_value != "false" if setting else True
    }


@scale_router.post("/settings/manual-override")
def set_manual_override(
    allow: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Admin: Enable or disable manual weight entry (Admin only)"""
    setting = db.query(SystemSetting).filter(
        SystemSetting.setting_key == "allow_manual_weight"
    ).first()
    if not setting:
        setting = SystemSetting(
            setting_key="allow_manual_weight",
            setting_value=str(allow).lower(),
            setting_type="boolean",
            description="Allow operators to manually enter weight instead of using scale"
        )
        db.add(setting)
    else:
        setting.setting_value = str(allow).lower()
    db.commit()
    log_activity(db, current_user.id, f"Manual weight override set to: {allow}", "Settings", 0)
    db.commit()
    return {
        "message": f"Manual weight entry {'enabled' if allow else 'disabled'}",
        "allow_manual_weight": allow
    }


@scale_router.get("/history/{job_id}")
def weight_history(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator", "QC Officer"))
):
    """All weight logs for a job, newest first — includes operator name"""
    logs = db.query(WeightLog).filter(
        WeightLog.job_id == job_id
    ).order_by(WeightLog.captured_at.desc()).all()

    # Build operator name lookup
    operator_ids = [l.operator_id for l in logs if l.operator_id]
    operators = {u.id: u.name for u in db.query(User).filter(User.id.in_(operator_ids)).all()} if operator_ids else {}

    return [
        {
            "id": l.id,
            "gross_weight": float(l.gross_weight),
            "tare_weight": float(l.tare_weight),
            "net_weight": float(l.net_weight),
            "scale_type": l.scale_type,
            "is_manual": l.is_manual_override,
            "operator_id": l.operator_id,
            "operator_name": operators.get(l.operator_id, "Unknown"),
            "captured_at": l.captured_at.isoformat() if l.captured_at else None,
        }
        for l in logs
    ]


# ============================================================
# METAL ROUTER
# ============================================================
metal_router = APIRouter(prefix="/api/v1/metal", tags=["Metal Accounting"])


class MetalIssueRequest(BaseModel):
    metal_type: str
    weight: float
    purity_pct: float
    issue_rate: float
    issued_to_type: str
    issued_to_id: int
    issued_to_name: str
    job_id: Optional[int] = None
    notes: Optional[str] = None


class MetalReturnRequest(BaseModel):
    metal_type: str
    weight: float
    purity_pct: float
    from_type: str
    from_id: int
    from_name: str
    job_id: Optional[int] = None
    notes: Optional[str] = None


@metal_router.get("/stock")
def get_metal_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Current metal stock levels"""
    stocks = db.query(MetalStock).all()
    return [
        {
            "id": s.id, "metal_type": s.metal_type, "stock_type": s.stock_type,
            "quantity": float(s.quantity), "purity_pct": float(s.purity_pct) if s.purity_pct else None,
            "last_rate": float(s.last_rate) if s.last_rate else 0,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None
        }
        for s in stocks
    ]


@metal_router.post("/issue")
def issue_metal(
    data: MetalIssueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Issue metal to department or karigar - ACID transaction"""
    fine_weight = round(data.weight * data.purity_pct / 100, 4)
    total_value = round(data.weight * data.issue_rate, 2)

    # Get current stock balance
    stock = db.query(MetalStock).filter(
        MetalStock.metal_type == data.metal_type
    ).first()
    current_balance = fmt_weight(stock.quantity) if stock else 0.0

    if current_balance < data.weight:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock. Available: {current_balance}g, Requested: {data.weight}g"
        )

    new_balance = round(current_balance - data.weight, 4)

    # Create ledger entry
    ledger = MetalLedger(
        transaction_type="Issue",
        metal_type=data.metal_type,
        weight=data.weight,
        purity_pct=data.purity_pct,
        fine_weight=fine_weight,
        issue_rate=data.issue_rate,
        total_value=total_value,
        balance_after=new_balance,
        issued_to_type=data.issued_to_type,
        issued_to_id=data.issued_to_id,
        issued_to_name=data.issued_to_name,
        job_id=data.job_id,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(ledger)

    # Deduct from stock
    if stock:
        stock.quantity = new_balance
        stock.last_rate = data.issue_rate
    db.commit()

    log_activity(db, current_user.id, f"Metal Issued {data.weight}g {data.metal_type} to {data.issued_to_name}", "Metal", ledger.id)
    db.commit()

    return {
        "message": "Metal issued successfully",
        "transaction_id": ledger.id,
        "fine_weight": fine_weight,
        "total_value": total_value,
        "new_balance": new_balance
    }


@metal_router.post("/return")
def return_metal(
    data: MetalReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Return metal from karigar/department"""
    fine_weight = round(data.weight * data.purity_pct / 100, 4)

    stock = db.query(MetalStock).filter(
        MetalStock.metal_type == data.metal_type
    ).first()
    new_balance = round(fmt_weight(stock.quantity if stock else 0) + data.weight, 4)

    ledger = MetalLedger(
        transaction_type="Return",
        metal_type=data.metal_type,
        weight=data.weight,
        purity_pct=data.purity_pct,
        fine_weight=fine_weight,
        balance_after=new_balance,
        issued_to_type=data.from_type,
        issued_to_id=data.from_id,
        issued_to_name=data.from_name,
        job_id=data.job_id,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(ledger)

    if stock:
        stock.quantity = new_balance
    db.commit()

    log_activity(db, current_user.id, f"Metal Returned {data.weight}g {data.metal_type} from {data.from_name}", "Metal", ledger.id)
    db.commit()

    return {"message": "Metal returned", "transaction_id": ledger.id, "new_balance": new_balance}


@metal_router.get("/ledger")
def get_metal_ledger(
    metal_type: Optional[str] = None,
    transaction_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant"))
):
    """Metal transaction ledger with filtering"""
    query = db.query(MetalLedger).order_by(MetalLedger.created_at.desc())
    if metal_type:
        query = query.filter(MetalLedger.metal_type == metal_type)
    if transaction_type:
        query = query.filter(MetalLedger.transaction_type == transaction_type)

    result = paginate(query, page, per_page)
    result["items"] = [
        {
            "id": t.id, "type": t.transaction_type, "metal": t.metal_type,
            "weight": float(t.weight), "purity": float(t.purity_pct) if t.purity_pct else None,
            "fine_weight": float(t.fine_weight) if t.fine_weight else None,
            "rate": float(t.issue_rate) if t.issue_rate else None,
            "value": float(t.total_value) if t.total_value else None,
            "balance_after": float(t.balance_after) if t.balance_after else None,
            "to_name": t.issued_to_name,
            "job_id": t.job_id,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in result["items"]
    ]
    return result


@metal_router.get("/reconciliation")
def metal_reconciliation(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant"))
):
    """Daily metal reconciliation - issued vs returned vs outstanding"""
    issued = db.query(func.sum(MetalLedger.weight)).filter(
        MetalLedger.transaction_type == "Issue"
    ).scalar() or 0

    returned = db.query(func.sum(MetalLedger.weight)).filter(
        MetalLedger.transaction_type == "Return"
    ).scalar() or 0

    stocks = db.query(MetalStock).all()

    return {
        "total_issued": float(issued),
        "total_returned": float(returned),
        "net_outstanding": float(issued) - float(returned),
        "current_stock": [
            {"metal": s.metal_type, "type": s.stock_type, "qty": float(s.quantity)}
            for s in stocks
        ]
    }


@metal_router.get("/balance/department")
def department_metal_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Department-wise metal balance — issued vs returned vs outstanding"""
    departments = db.query(Department).filter(Department.is_active == True).all()
    result = []
    for dept in departments:
        issued = db.query(func.sum(MetalLedger.weight)).filter(
            MetalLedger.transaction_type == "Issue",
            MetalLedger.issued_to_type == "Department",
            MetalLedger.issued_to_id == dept.id
        ).scalar() or 0

        returned = db.query(func.sum(MetalLedger.weight)).filter(
            MetalLedger.transaction_type == "Return",
            MetalLedger.issued_to_type == "Department",
            MetalLedger.issued_to_id == dept.id
        ).scalar() or 0

        result.append({
            "department_id": dept.id,
            "department_name": dept.name,
            "total_issued": round(float(issued), 4),
            "total_returned": round(float(returned), 4),
            "outstanding": round(float(issued) - float(returned), 4)
        })
    return result


@metal_router.get("/balance/karigar")
def karigar_metal_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Karigar-wise metal balance — issued vs returned vs outstanding"""
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    result = []
    for k in karigars:
        issued = db.query(func.sum(MetalLedger.weight)).filter(
            MetalLedger.transaction_type == "Issue",
            MetalLedger.issued_to_type == "Karigar",
            MetalLedger.issued_to_id == k.id
        ).scalar() or 0

        returned = db.query(func.sum(MetalLedger.weight)).filter(
            MetalLedger.transaction_type == "Return",
            MetalLedger.issued_to_type == "Karigar",
            MetalLedger.issued_to_id == k.id
        ).scalar() or 0

        result.append({
            "karigar_id": k.id,
            "karigar_code": k.karigar_code,
            "karigar_name": k.name,
            "skill_type": k.skill_type,
            "total_issued": round(float(issued), 4),
            "total_returned": round(float(returned), 4),
            "outstanding": round(float(issued) - float(returned), 4)
        })
    return result


# ============================================================
# KARIGAR ROUTER
# ============================================================
karigar_router = APIRouter(prefix="/api/v1/karigar", tags=["Karigar Management"])


class KarigarCreateRequest(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    skill_type: Optional[str] = None
    experience_years: int = 0
    piece_rate: float = 0
    daily_rate: float = 0
    joined_date: Optional[date] = None


class AssignmentRequest(BaseModel):
    karigar_id: int
    job_id: int
    stage_log_id: Optional[int] = None
    pieces_assigned: int = 1
    metal_issued: float = 0


@karigar_router.get("/")
def list_karigars(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """List all active karigars with pending job count"""
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    result = []
    for k in karigars:
        pending = db.query(KarigarAssignment).filter(
            KarigarAssignment.karigar_id == k.id,
            KarigarAssignment.status.in_(["Assigned", "In Progress"])
        ).count()
        result.append({
            "id": k.id, "karigar_code": k.karigar_code, "name": k.name,
            "phone": k.phone, "skill_type": k.skill_type,
            "experience_years": k.experience_years,
            "piece_rate": float(k.piece_rate), "daily_rate": float(k.daily_rate),
            "pending_jobs": pending,
            "joined_date": str(k.joined_date) if k.joined_date else None
        })
    return result


@karigar_router.post("/")
def create_karigar(
    data: KarigarCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Add new karigar"""
    k = Karigar(
        karigar_code=generate_karigar_code(db),
        name=data.name, phone=data.phone, address=data.address,
        skill_type=data.skill_type, experience_years=data.experience_years,
        piece_rate=data.piece_rate, daily_rate=data.daily_rate,
        joined_date=data.joined_date
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    log_activity(db, current_user.id, f"Created Karigar {k.name}", "Karigar", k.id)
    db.commit()
    return {"id": k.id, "karigar_code": k.karigar_code, "name": k.name}


@karigar_router.put("/{karigar_id}")
def update_karigar(
    karigar_id: int,
    data: KarigarCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Update karigar details"""
    k = db.query(Karigar).filter(Karigar.id == karigar_id).first()
    if not k:
        raise HTTPException(status_code=404, detail="Karigar not found")
    if data.name: k.name = data.name
    if data.phone is not None: k.phone = data.phone
    if data.address is not None: k.address = data.address
    if data.skill_type is not None: k.skill_type = data.skill_type
    if data.experience_years: k.experience_years = data.experience_years
    if data.piece_rate is not None: k.piece_rate = data.piece_rate
    if data.daily_rate is not None: k.daily_rate = data.daily_rate
    if data.joined_date: k.joined_date = data.joined_date
    db.commit()
    log_activity(db, current_user.id, f"Updated karigar {k.name}", "Karigar", k.id)
    db.commit()
    return {"id": k.id, "karigar_code": k.karigar_code, "name": k.name, "message": "Updated"}


@karigar_router.delete("/{karigar_id}")
def deactivate_karigar(
    karigar_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Deactivate karigar (soft delete)"""
    k = db.query(Karigar).filter(Karigar.id == karigar_id).first()
    if not k:
        raise HTTPException(status_code=404, detail="Karigar not found")
    # Check for pending assignments
    pending = db.query(KarigarAssignment).filter(
        KarigarAssignment.karigar_id == karigar_id,
        KarigarAssignment.status.in_(["Assigned", "In Progress"])
    ).count()
    if pending > 0:
        raise HTTPException(status_code=400, detail=f"Cannot deactivate — {pending} pending assignment(s) exist")
    k.is_active = False
    db.commit()
    log_activity(db, current_user.id, f"Deactivated karigar {k.name}", "Karigar", k.id)
    db.commit()
    return {"message": f"Karigar '{k.name}' deactivated"}


@karigar_router.get("/{karigar_id}")
def get_karigar(
    karigar_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Get single karigar details"""
    k = db.query(Karigar).filter(Karigar.id == karigar_id).first()
    if not k:
        raise HTTPException(status_code=404, detail="Karigar not found")
    pending = db.query(KarigarAssignment).filter(
        KarigarAssignment.karigar_id == karigar_id,
        KarigarAssignment.status.in_(["Assigned", "In Progress"])
    ).count()
    return {
        "id": k.id, "karigar_code": k.karigar_code, "name": k.name,
        "phone": k.phone, "address": k.address, "skill_type": k.skill_type,
        "experience_years": k.experience_years, "piece_rate": float(k.piece_rate),
        "daily_rate": float(k.daily_rate), "is_active": k.is_active,
        "joined_date": str(k.joined_date) if k.joined_date else None,
        "pending_jobs": pending
    }


@karigar_router.post("/assign")
def assign_job(
    data: AssignmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Assign job pieces to a karigar"""
    karigar = db.query(Karigar).filter(Karigar.id == data.karigar_id).first()
    if not karigar:
        raise HTTPException(status_code=404, detail="Karigar not found")

    labour_cost = float(karigar.piece_rate) * data.pieces_assigned

    assignment = KarigarAssignment(
        karigar_id=data.karigar_id, job_id=data.job_id,
        stage_log_id=data.stage_log_id,
        pieces_assigned=data.pieces_assigned,
        metal_issued=data.metal_issued,
        labour_cost=labour_cost, status="Assigned"
    )
    db.add(assignment)
    db.commit()
    log_activity(db, current_user.id, f"Assigned job {data.job_id} to karigar {karigar.name}", "Karigar", karigar.id)
    db.commit()
    return {"message": "Assigned", "labour_cost": labour_cost, "id": assignment.id}


@karigar_router.put("/assignment/{assignment_id}/complete")
def complete_assignment(
    assignment_id: int,
    pieces_completed: int,
    metal_returned: float = 0.0,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Mark karigar assignment as completed — update pieces done and metal returned"""
    assignment = db.query(KarigarAssignment).filter(KarigarAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    karigar = db.query(Karigar).filter(Karigar.id == assignment.karigar_id).first()

    assignment.pieces_completed = pieces_completed
    assignment.metal_returned = metal_returned

    # Recalculate labour cost based on actual pieces completed
    if karigar:
        assignment.labour_cost = round(float(karigar.piece_rate) * pieces_completed, 2)

    # Set status
    if pieces_completed >= assignment.pieces_assigned:
        assignment.status = "Completed"
        assignment.completed_at = datetime.utcnow()
    else:
        assignment.status = "Partial"

    db.commit()
    log_activity(db, current_user.id, f"Assignment {assignment_id} completed ({pieces_completed} pieces)", "Karigar", assignment.karigar_id)
    db.commit()

    return {
        "message": "Assignment updated",
        "assignment_id": assignment_id,
        "pieces_completed": pieces_completed,
        "pieces_assigned": assignment.pieces_assigned,
        "metal_returned": metal_returned,
        "labour_cost": float(assignment.labour_cost),
        "status": assignment.status
    }


@karigar_router.get("/assignments/{karigar_id}")
def get_karigar_assignments(
    karigar_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Get all assignments for a karigar"""
    query = db.query(KarigarAssignment).filter(KarigarAssignment.karigar_id == karigar_id)
    if status:
        query = query.filter(KarigarAssignment.status == status)
    assignments = query.order_by(KarigarAssignment.assigned_at.desc()).all()
    return [
        {
            "id": a.id, "job_id": a.job_id,
            "pieces_assigned": a.pieces_assigned,
            "pieces_completed": a.pieces_completed,
            "metal_issued": float(a.metal_issued),
            "metal_returned": float(a.metal_returned),
            "labour_cost": float(a.labour_cost),
            "status": a.status,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None
        }
        for a in assignments
    ]


@karigar_router.get("/wage-report")
def wage_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant"))
):
    """Weekly wage calculation report per karigar"""
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    report = []
    for k in karigars:
        total_wages = db.query(func.sum(KarigarAssignment.labour_cost)).filter(
            KarigarAssignment.karigar_id == k.id
        ).scalar() or 0
        pending_pieces = db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(
            KarigarAssignment.karigar_id == k.id,
            KarigarAssignment.status != "Completed"
        ).scalar() or 0
        completed_pieces = db.query(func.sum(KarigarAssignment.pieces_completed)).filter(
            KarigarAssignment.karigar_id == k.id
        ).scalar() or 0
        report.append({
            "karigar_id": k.id, "name": k.name,
            "karigar_code": k.karigar_code, "skill": k.skill_type,
            "piece_rate": float(k.piece_rate),
            "total_wages": float(total_wages),
            "pending_pieces": int(pending_pieces),
            "completed_pieces": int(completed_pieces)
        })
    return report


@karigar_router.get("/performance")
def karigar_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Karigar productivity tracking"""
    return wage_report(db, current_user)


@karigar_router.get("/wage-report/pdf")
def wage_report_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant"))
):
    """Export karigar wage report as PDF"""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab not installed. Run: pip install reportlab")

    # Fetch data
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    report_data = []
    for k in karigars:
        total_wages = db.query(func.sum(KarigarAssignment.labour_cost)).filter(
            KarigarAssignment.karigar_id == k.id
        ).scalar() or 0
        pending_pieces = db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(
            KarigarAssignment.karigar_id == k.id,
            KarigarAssignment.status != "Completed"
        ).scalar() or 0
        completed_pieces = db.query(func.sum(KarigarAssignment.pieces_completed)).filter(
            KarigarAssignment.karigar_id == k.id
        ).scalar() or 0
        total_assigned = (db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(
            KarigarAssignment.karigar_id == k.id
        ).scalar() or 0)
        efficiency = round((int(completed_pieces) / int(total_assigned) * 100), 1) if total_assigned else 0
        report_data.append({
            "code": k.karigar_code, "name": k.name, "skill": k.skill_type or "—",
            "piece_rate": float(k.piece_rate), "completed": int(completed_pieces),
            "pending": int(pending_pieces), "total_wages": float(total_wages),
            "efficiency": efficiency
        })

    # Build PDF in memory
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm
    )

    styles = getSampleStyleSheet()
    gold   = colors.HexColor("#C9A84C")
    dark   = colors.HexColor("#1a1710")
    white  = colors.white
    gray   = colors.HexColor("#2a2318")
    light  = colors.HexColor("#f5f0e8")

    title_style = ParagraphStyle("title", fontSize=18, textColor=gold,
                                  fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4)
    sub_style   = ParagraphStyle("sub", fontSize=9, textColor=colors.HexColor("#888888"),
                                  fontName="Helvetica", alignment=TA_CENTER, spaceAfter=2)

    story = []
    story.append(Paragraph("Karigar Wage Report", title_style))
    story.append(Paragraph(f"Generated on {date_type.today().strftime('%d %B %Y')}  |  Total Artisans: {len(report_data)}", sub_style))
    story.append(Spacer(1, 8*mm))

    # Summary row
    total_wages_all = sum(r["total_wages"] for r in report_data)
    total_completed = sum(r["completed"] for r in report_data)
    total_pending   = sum(r["pending"] for r in report_data)

    summary_data = [
        ["Total Artisans", "Total Completed Pieces", "Total Pending", "Total Wages Payable"],
        [str(len(report_data)), str(total_completed), str(total_pending),
         f"Rs. {total_wages_all:,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[60*mm, 65*mm, 55*mm, 70*mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), dark),
        ("TEXTCOLOR",  (0, 0), (-1, 0), gold),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#13110e")),
        ("TEXTCOLOR",  (0, 1), (-1, 1), white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME",   (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.HexColor("#13110e")]),
        ("BOX",        (0, 0), (-1, -1), 1, gray),
        ("GRID",       (0, 0), (-1, -1), 0.5, gray),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8*mm))

    # Main table
    headers = ["#", "Code", "Name", "Skill", "Piece Rate (Rs.)", "Completed", "Pending", "Efficiency %", "Total Wages (Rs.)"]
    table_data = [headers]
    for i, r in enumerate(report_data, 1):
        eff_str = f"{r['efficiency']}%"
        table_data.append([
            str(i), r["code"], r["name"], r["skill"],
            f"{r['piece_rate']:,.2f}",
            str(r["completed"]), str(r["pending"]),
            eff_str,
            f"{r['total_wages']:,.2f}"
        ])
    # Totals row
    table_data.append([
        "", "", "TOTAL", "", "", str(total_completed),
        str(total_pending), "", f"{total_wages_all:,.2f}"
    ])

    col_widths = [10*mm, 22*mm, 52*mm, 32*mm, 32*mm, 24*mm, 22*mm, 28*mm, 38*mm]
    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    row_count = len(table_data)
    main_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0), dark),
        ("TEXTCOLOR",    (0, 0), (-1, 0), gold),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 9),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        # Data rows alternating
        ("ROWBACKGROUNDS", (0, 1), (-1, row_count - 2),
         [colors.HexColor("#1c1810"), colors.HexColor("#151209")]),
        ("TEXTCOLOR",    (0, 1), (-1, row_count - 2), colors.HexColor("#e0d8c0")),
        ("FONTNAME",     (0, 1), (-1, row_count - 2), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, row_count - 2), 8.5),
        # Totals row
        ("BACKGROUND",   (0, row_count - 1), (-1, row_count - 1), colors.HexColor("#2a1f00")),
        ("TEXTCOLOR",    (0, row_count - 1), (-1, row_count - 1), gold),
        ("FONTNAME",     (0, row_count - 1), (-1, row_count - 1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, row_count - 1), (-1, row_count - 1), 9),
        # Alignment
        ("ALIGN",  (0, 1), (1, -1), "CENTER"),
        ("ALIGN",  (4, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Grid
        ("BOX",  (0, 0), (-1, -1), 1, gray),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#333025")),
        ("LINEABOVE", (0, row_count - 1), (-1, row_count - 1), 1, gold),
        # Padding
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    story.append(main_table)

    # Footer note
    story.append(Spacer(1, 6*mm))
    footer_style = ParagraphStyle("footer", fontSize=7, textColor=colors.HexColor("#666666"),
                                   fontName="Helvetica", alignment=TA_CENTER)
    story.append(Paragraph("This report is system-generated from Jewellery Manufacturing ERP. For internal use only.", footer_style))

    doc.build(story)
    buf.seek(0)

    filename = f"wage_report_{date_type.today().isoformat()}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================
# SCRAP ROUTER
# ============================================================
scrap_router = APIRouter(prefix="/api/v1/scrap", tags=["Scrap Management"])


class ScrapCreateRequest(BaseModel):
    source_department_id: int
    scrap_type: str
    gross_weight: float
    estimated_purity: float
    notes: Optional[str] = None


@scrap_router.get("/")
def list_scrap(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """List all scrap batches"""
    entries = db.query(ScrapEntry).order_by(ScrapEntry.collected_at.desc()).all()
    return [
        {
            "id": s.id, "batch_id": s.batch_id, "scrap_type": s.scrap_type,
            "gross_weight": float(s.gross_weight),
            "estimated_purity": float(s.estimated_purity) if s.estimated_purity else None,
            "estimated_fine": float(s.estimated_fine_weight) if s.estimated_fine_weight else None,
            "status": s.status,
            "collected_at": s.collected_at.isoformat() if s.collected_at else None
        }
        for s in entries
    ]


@scrap_router.post("/")
def create_scrap(
    data: ScrapCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Record new scrap batch"""
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
        notes=data.notes
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log_activity(db, current_user.id, f"Scrap recorded {data.gross_weight}g {data.scrap_type}", "Scrap", entry.id)
    db.commit()
    return {"id": entry.id, "batch_id": entry.batch_id, "estimated_fine_weight": fine}


@scrap_router.get("/summary")
def scrap_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Scrap totals by type and status"""
    total = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
    by_type = db.query(
        ScrapEntry.scrap_type, func.sum(ScrapEntry.gross_weight)
    ).group_by(ScrapEntry.scrap_type).all()
    by_status = db.query(
        ScrapEntry.status, func.count(ScrapEntry.id)
    ).group_by(ScrapEntry.status).all()
    return {
        "total_gross_weight": float(total),
        "by_type": {t: float(w) for t, w in by_type},
        "by_status": {s: int(c) for s, c in by_status}
    }


@scrap_router.put("/{scrap_id}/status")
def update_scrap_status(
    scrap_id: int,
    status: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Metal Store Manager"))
):
    """Update scrap batch status: Collected → In Stock → Sent to Refinery → Settled"""
    valid_statuses = ["Collected", "In Stock", "Sent to Refinery", "Settled"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    entry = db.query(ScrapEntry).filter(ScrapEntry.id == scrap_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Scrap batch not found")

    old_status = entry.status
    entry.status = status
    if notes:
        entry.notes = notes
    db.commit()
    log_activity(db, current_user.id, f"Scrap {entry.batch_id} status: {old_status} → {status}", "Scrap", scrap_id)
    db.commit()
    return {
        "message": "Status updated",
        "batch_id": entry.batch_id,
        "old_status": old_status,
        "new_status": status
    }


# ============================================================
# REFINERY ROUTER
# ============================================================
refinery_router = APIRouter(prefix="/api/v1/refinery", tags=["Refinery Management"])


class DispatchCreateRequest(BaseModel):
    refinery_name: str
    dispatch_date: date
    total_gross_weight: float
    estimated_purity: float
    scrap_batch_ids: List[int] = []
    notes: Optional[str] = None


class SettlementCreateRequest(BaseModel):
    dispatch_id: int
    settlement_date: date
    fine_gold_received: float
    refining_charges: float = 0
    notes: Optional[str] = None


@refinery_router.get("/")
def list_dispatches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """List all refinery dispatches"""
    dispatches = db.query(RefineryDispatch).order_by(RefineryDispatch.dispatch_date.desc()).all()
    return [
        {
            "id": d.id, "dispatch_no": d.dispatch_no, "refinery_name": d.refinery_name,
            "dispatch_date": str(d.dispatch_date),
            "total_gross_weight": float(d.total_gross_weight),
            "expected_fine_gold": float(d.expected_fine_gold) if d.expected_fine_gold else None,
            "status": d.status
        }
        for d in dispatches
    ]


@refinery_router.post("/dispatch")
def create_dispatch(
    data: DispatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Create new refinery dispatch"""
    expected_fine = round(data.total_gross_weight * data.estimated_purity / 100, 4)
    dispatch = RefineryDispatch(
        dispatch_no=generate_dispatch_no(),
        refinery_name=data.refinery_name,
        dispatch_date=data.dispatch_date,
        total_gross_weight=data.total_gross_weight,
        estimated_purity=data.estimated_purity,
        expected_fine_gold=expected_fine,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(dispatch)
    db.flush()

    # Update scrap batch statuses
    for batch_id in data.scrap_batch_ids:
        batch = db.query(ScrapEntry).filter(ScrapEntry.id == batch_id).first()
        if batch:
            batch.status = "Sent to Refinery"

    db.commit()
    log_activity(db, current_user.id, f"Refinery dispatch {dispatch.dispatch_no} to {data.refinery_name}", "Refinery", dispatch.id)
    db.commit()
    return {"dispatch_no": dispatch.dispatch_no, "expected_fine_gold": expected_fine}


@refinery_router.post("/settle")
def settle_dispatch(
    data: SettlementCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Metal Store Manager"))
):
    """Record refinery settlement and update metal ledger"""
    dispatch = db.query(RefineryDispatch).filter(RefineryDispatch.id == data.dispatch_id).first()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")

    recovery_pct = round(
        (data.fine_gold_received / float(dispatch.total_gross_weight)) * 100, 3
    ) if dispatch.total_gross_weight else 0

    variance_pct = round(
        recovery_pct - (float(dispatch.estimated_purity) if dispatch.estimated_purity else 0), 3
    )

    settlement = RefinerySettlement(
        dispatch_id=data.dispatch_id,
        settlement_date=data.settlement_date,
        fine_gold_received=data.fine_gold_received,
        recovery_pct=recovery_pct,
        refining_charges=data.refining_charges,
        variance_pct=variance_pct,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(settlement)
    dispatch.status = "Settled"

    # Add fine gold back to 24K pure stock
    pure_stock = db.query(MetalStock).filter(
        MetalStock.metal_type == "24K", MetalStock.stock_type == "Pure"
    ).first()
    if pure_stock:
        pure_stock.quantity = round(float(pure_stock.quantity) + data.fine_gold_received, 4)

    # Add refinery-in ledger entry
    ledger = MetalLedger(
        transaction_type="Refinery In",
        metal_type="24K",
        weight=data.fine_gold_received,
        purity_pct=99.9,
        fine_weight=data.fine_gold_received,
        balance_after=float(pure_stock.quantity) if pure_stock else data.fine_gold_received,
        notes=f"Settlement for {dispatch.dispatch_no}",
        created_by=current_user.id
    )
    db.add(ledger)
    db.commit()

    log_activity(db, current_user.id, f"Refinery settled {dispatch.dispatch_no}, received {data.fine_gold_received}g", "Refinery", dispatch.id)
    db.commit()

    return {
        "message": "Settlement recorded",
        "recovery_pct": recovery_pct,
        "variance_pct": variance_pct
    }


# ============================================================
# INVENTORY ROUTER
# ============================================================
inventory_router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])


class ItemCreateRequest(BaseModel):
    name: str
    category: str
    unit: str
    reorder_level: float = 0
    unit_cost: float = 0


class StockAdjustRequest(BaseModel):
    item_id: int
    transaction_type: str
    quantity: float
    unit_cost: Optional[float] = None
    notes: Optional[str] = None


@inventory_router.get("/")
def list_items(
    category: Optional[str] = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """List inventory items"""
    query = db.query(InventoryItem).filter(
        (InventoryItem.is_active == True) | (InventoryItem.is_active == None)
    )
    if category:
        query = query.filter(InventoryItem.category == category)
    if low_stock_only:
        query = query.filter(InventoryItem.current_stock <= InventoryItem.reorder_level)

    items = query.all()
    return [
        {
            "id": i.id, "item_code": i.item_code, "name": i.name,
            "category": i.category, "unit": i.unit,
            "current_stock": float(i.current_stock),
            "reorder_level": float(i.reorder_level),
            "unit_cost": float(i.unit_cost),
            "low_stock": float(i.current_stock) <= float(i.reorder_level)
        }
        for i in items
    ]


@inventory_router.post("/")
def create_item(
    data: ItemCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Create new inventory item"""
    count = db.query(InventoryItem).count() + 1
    item = InventoryItem(
        item_code=f"ITEM-{str(count).zfill(4)}",
        name=data.name,
        category=data.category,
        unit=data.unit,
        reorder_level=data.reorder_level,
        unit_cost=data.unit_cost,
        is_active=True
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "item_code": item.item_code, "name": item.name}


@inventory_router.post("/adjust")
def adjust_stock(
    data: StockAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Adjust inventory stock (in/out/adjust)"""
    item = db.query(InventoryItem).filter(InventoryItem.id == data.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if data.transaction_type == "Issue" or data.transaction_type == "Scrap":
        if float(item.current_stock) < data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        item.current_stock = round(float(item.current_stock) - data.quantity, 4)
    elif data.transaction_type in ["Purchase", "Return"]:
        item.current_stock = round(float(item.current_stock) + data.quantity, 4)
    else:  # Adjust - set absolute value
        item.current_stock = round(data.quantity, 4)

    total_cost = round(data.quantity * (data.unit_cost or float(item.unit_cost)), 2)

    txn = InventoryTransaction(
        item_id=data.item_id,
        transaction_type=data.transaction_type,
        quantity=data.quantity,
        unit_cost=data.unit_cost or float(item.unit_cost),
        total_cost=total_cost,
        balance_after=item.current_stock,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(txn)
    db.commit()
    log_activity(db, current_user.id, f"Inventory {data.transaction_type} {data.quantity} {item.name}", "Inventory", item.id)
    db.commit()
    return {"message": "Stock updated", "new_balance": float(item.current_stock)}


# ============================================================
# FINISHED GOODS ROUTER
# ============================================================
finished_goods_router = APIRouter(prefix="/api/v1/finished-goods", tags=["Finished Goods"])


class QCPassRequest(BaseModel):
    job_id: int
    final_weight: float
    pieces_count: int = 1
    hallmark_no: Optional[str] = None
    qc_notes: Optional[str] = None


class DispatchRequest(BaseModel):
    job_id: int
    dispatch_ref: str
    dispatch_date: Optional[date] = None


@finished_goods_router.get("/")
def list_finished_goods(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "QC Officer", "Accountant", "Metal Store Manager"))
):
    """List all finished goods"""
    try:
        from sqlalchemy import text as sa_text
        if status:
            sql = sa_text("""
                SELECT fg.id, fg.job_id, fg.item_code, fg.final_weight, fg.pieces_count,
                       fg.hallmark_no, fg.qc_passed, fg.qc_officer_id, fg.qc_date,
                       fg.qc_notes, fg.dispatch_date, fg.dispatch_ref, fg.status,
                       u.name as qc_officer_name
                FROM finished_goods fg
                LEFT JOIN users u ON u.id = fg.qc_officer_id
                WHERE fg.status = :status
                ORDER BY fg.id DESC
            """)
            result = db.execute(sql, {"status": status})
        else:
            sql = sa_text("""
                SELECT fg.id, fg.job_id, fg.item_code, fg.final_weight, fg.pieces_count,
                       fg.hallmark_no, fg.qc_passed, fg.qc_officer_id, fg.qc_date,
                       fg.qc_notes, fg.dispatch_date, fg.dispatch_ref, fg.status,
                       u.name as qc_officer_name
                FROM finished_goods fg
                LEFT JOIN users u ON u.id = fg.qc_officer_id
                ORDER BY fg.id DESC
            """)
            result = db.execute(sql)

        output = []
        for r in result:
            row = dict(r._mapping)
            output.append({
                "id":             row.get("id"),
                "job_id":         row.get("job_id"),
                "item_code":      row.get("item_code") or "—",
                "final_weight":   float(row["final_weight"]) if row.get("final_weight") else None,
                "pieces_count":   row.get("pieces_count") or 1,
                "hallmark_no":    row.get("hallmark_no"),
                "qc_passed":      bool(row.get("qc_passed")),
                "qc_officer_name": row.get("qc_officer_name") or "—",
                "qc_date":        row["qc_date"].isoformat() if row.get("qc_date") else None,
                "qc_notes":       row.get("qc_notes"),
                "dispatch_date":  row["dispatch_date"].isoformat() if row.get("dispatch_date") else None,
                "dispatch_ref":   row.get("dispatch_ref"),
                "status":         row.get("status") or "Ready"
            })
        return output

    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Finished goods error: {str(e)}")


@finished_goods_router.post("/qc-pass")
def qc_pass(
    data: QCPassRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "QC Officer"))
):
    """Mark job as QC passed and create finished good record"""
    job = db.query(Job).filter(Job.id == data.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if finished good already exists
    fg = db.query(FinishedGood).filter(FinishedGood.job_id == data.job_id).first()
    if not fg:
        count = db.query(FinishedGood).count() + 1
        fg = FinishedGood(
            job_id=data.job_id,
            item_code=f"FG-{str(count).zfill(4)}"
        )
        db.add(fg)

    fg.final_weight = data.final_weight
    fg.pieces_count = data.pieces_count
    fg.hallmark_no = data.hallmark_no
    fg.qc_passed = True
    fg.qc_officer_id = current_user.id
    fg.qc_date = datetime.utcnow()
    fg.qc_notes = data.qc_notes
    fg.status = "Ready"

    job.status = "Completed"
    job.updated_by = current_user.id

    db.commit()
    db.refresh(fg)
    log_activity(db, current_user.id, "QC Passed", "FinishedGoods", data.job_id)
    db.commit()

    return {"message": "QC passed", "item_code": fg.item_code, "job_id": data.job_id}


@finished_goods_router.post("/qc-fail")
def qc_fail(
    job_id: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "QC Officer"))
):
    """Mark job as QC failed"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "QC Rejected"
    job.updated_by = current_user.id

    # Update stage log
    stage_log = db.query(JobStageLog).filter(
        JobStageLog.job_id == job_id,
        JobStageLog.stage_name == "Quality Control"
    ).first()
    if stage_log:
        stage_log.status = "Rejected"
        stage_log.rejection_reason = reason

    db.commit()
    log_activity(db, current_user.id, f"QC Failed: {reason}", "FinishedGoods", job_id)
    db.commit()

    return {"message": "QC failed", "job_id": job_id, "reason": reason}


@finished_goods_router.post("/dispatch")
def dispatch_finished_good(
    data: DispatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Mark finished good as dispatched"""
    fg = db.query(FinishedGood).filter(FinishedGood.job_id == data.job_id).first()
    if not fg:
        raise HTTPException(status_code=404, detail="Finished good not found. Run QC pass first.")
    if not fg.qc_passed:
        raise HTTPException(status_code=400, detail="Cannot dispatch — QC not passed yet")

    fg.dispatch_ref = data.dispatch_ref
    fg.dispatch_date = datetime.utcnow() if not data.dispatch_date else data.dispatch_date
    fg.status = "Dispatched"

    job = db.query(Job).filter(Job.id == data.job_id).first()
    if job:
        job.status = "Dispatched"
        job.current_stage = "Dispatch"
        job.updated_by = current_user.id

    db.commit()
    log_activity(db, current_user.id, f"Dispatched ref:{data.dispatch_ref}", "FinishedGoods", data.job_id)
    db.commit()

    return {"message": "Dispatched successfully", "dispatch_ref": data.dispatch_ref, "job_id": data.job_id}


# ============================================================
# COSTING ROUTER
# ============================================================
costing_router = APIRouter(prefix="/api/v1/costing", tags=["Costing"])


class CostUpdateRequest(BaseModel):
    job_id: int
    gold_weight_used: float = 0
    gold_rate: float = 0
    labour_cost: float = 0
    stone_cost: float = 0
    wastage_cost: float = 0
    refinery_adjustment: float = 0
    overhead_cost: float = 0
    sale_price: float = 0


@costing_router.get("/job/{job_id}")
def get_job_cost(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Accountant", "Production Manager"))
):
    """Get cost breakdown for a job"""
    cost = db.query(JobCost).filter(JobCost.job_id == job_id).first()
    if not cost:
        raise HTTPException(status_code=404, detail="No cost data found")
    return _cost_dict(cost)


@costing_router.post("/calculate")
def calculate_cost(
    data: CostUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Accountant", "Production Manager"))
):
    """Calculate and save job cost"""
    gold_cost = round(data.gold_weight_used * data.gold_rate, 2)
    total_cost = round(
        gold_cost + data.labour_cost + data.stone_cost +
        data.wastage_cost + data.refinery_adjustment + data.overhead_cost, 2
    )
    profit_loss = round(data.sale_price - total_cost, 2)
    margin_pct = round((profit_loss / data.sale_price * 100), 2) if data.sale_price > 0 else 0

    cost = db.query(JobCost).filter(JobCost.job_id == data.job_id).first()
    if not cost:
        cost = JobCost(job_id=data.job_id)
        db.add(cost)

    cost.gold_weight_used = data.gold_weight_used
    cost.gold_rate = data.gold_rate
    cost.gold_cost = gold_cost
    cost.labour_cost = data.labour_cost
    cost.stone_cost = data.stone_cost
    cost.wastage_cost = data.wastage_cost
    cost.refinery_adjustment = data.refinery_adjustment
    cost.overhead_cost = data.overhead_cost
    cost.total_cost = total_cost
    cost.sale_price = data.sale_price
    cost.profit_loss = profit_loss
    cost.margin_pct = margin_pct

    db.commit()
    log_activity(db, current_user.id, f"Cost calculated for job {data.job_id}, total={total_cost}", "Costing", data.job_id)
    db.commit()
    return _cost_dict(cost)


@costing_router.get("/profitability")
def profitability_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Accountant"))
):
    """Job-wise profitability analysis"""
    costs = db.query(JobCost).join(Job).all()
    return [
        {
            "job_id": c.job_id,
            "total_cost": float(c.total_cost),
            "sale_price": float(c.sale_price),
            "profit_loss": float(c.profit_loss),
            "margin_pct": float(c.margin_pct)
        }
        for c in costs
    ]


def _cost_dict(cost: JobCost) -> dict:
    return {
        "job_id": cost.job_id,
        "gold_weight_used": float(cost.gold_weight_used),
        "gold_rate": float(cost.gold_rate),
        "gold_cost": float(cost.gold_cost),
        "labour_cost": float(cost.labour_cost),
        "stone_cost": float(cost.stone_cost),
        "wastage_cost": float(cost.wastage_cost),
        "refinery_adjustment": float(cost.refinery_adjustment),
        "overhead_cost": float(cost.overhead_cost),
        "total_cost": float(cost.total_cost),
        "sale_price": float(cost.sale_price),
        "profit_loss": float(cost.profit_loss),
        "margin_pct": float(cost.margin_pct)
    }


# ============================================================
# REPORTS ROUTER
# ============================================================
reports_router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@reports_router.get("/master-summary")
def master_summary_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant", "QC Officer"))
):
    """Master summary — all key metrics in one call for management view"""
    try:

        # Jobs
        total_jobs = db.query(Job).count()
        active_jobs = db.query(Job).filter(Job.status == "Active").count()
        completed_jobs = db.query(Job).filter(Job.status.in_(["Completed", "Dispatched"])).count()
        overdue_jobs = db.query(Job).filter(
            Job.expected_delivery < datetime.utcnow().date(),
            Job.status.notin_(["Completed", "Dispatched"])
        ).count()

        # Metal
        issued = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
        returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
        metal_stocks = db.query(MetalStock).all()

        # Scrap
        total_scrap = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
        pending_scrap = db.query(func.count(ScrapEntry.id)).filter(
            ScrapEntry.status.in_(["Collected", "In Stock"])
        ).scalar() or 0

        # Karigars
        active_karigars = db.query(Karigar).filter(Karigar.is_active == True).count()
        pending_assignments = db.query(KarigarAssignment).filter(
            KarigarAssignment.status.in_(["Assigned", "In Progress"])
        ).count()

        # Financials
        total_revenue = db.query(func.sum(JobCost.sale_price)).scalar() or 0
        total_cost_val = db.query(func.sum(JobCost.total_cost)).scalar() or 0

        # Inventory alerts
        low_stock = db.query(InventoryItem).filter(
            InventoryItem.is_active == True,
            InventoryItem.current_stock <= InventoryItem.reorder_level
        ).count()

        # Refinery
        pending_refinery = db.query(RefineryDispatch).filter(RefineryDispatch.status == "Dispatched").count()

        return {
            "jobs": {
                "total": total_jobs, "active": active_jobs,
                "completed": completed_jobs, "overdue": overdue_jobs
            },
            "metal": {
                "total_issued": round(float(issued), 4),
                "total_returned": round(float(returned), 4),
                "outstanding": round(float(issued) - float(returned), 4),
                "stocks": [{"type": s.metal_type, "stock_type": s.stock_type, "qty": float(s.quantity)} for s in metal_stocks]
            },
            "scrap": {
                "total_weight": round(float(total_scrap), 4),
                "pending_batches": int(pending_scrap)
            },
            "karigars": {
                "active": active_karigars,
                "pending_assignments": pending_assignments
            },
            "financials": {
                "total_revenue": round(float(total_revenue), 2),
                "total_cost": round(float(total_cost_val), 2),
                "gross_profit": round(float(total_revenue) - float(total_cost_val), 2)
            },
            "alerts": {
                "low_stock_items": low_stock,
                "pending_refinery_settlements": pending_refinery,
                "overdue_jobs": overdue_jobs
            }
        }


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/dashboard")
def dashboard_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant", "QC Officer"))
):
    """Main dashboard KPIs"""
    try:
        total_jobs = db.query(Job).count()
        active_jobs = db.query(Job).filter(Job.status == "Active").count()
        qc_pending = db.query(Job).filter(Job.status == "QC Pending").count()
        completed = db.query(Job).filter(Job.status.in_(["Completed","Dispatched"])).count()
        scrap_pending = db.query(ScrapEntry).filter(
            ScrapEntry.status.in_(["Collected","In Stock"])
        ).count()
        active_karigars = db.query(Karigar).filter(Karigar.is_active == True).count()
        low_stock = db.query(InventoryItem).filter(
            InventoryItem.is_active == True,
            InventoryItem.current_stock <= InventoryItem.reorder_level
        ).count()

        departments = db.query(Department).filter(
            Department.is_active == True
        ).order_by(Department.stage_order).all()
        pipeline = [
            {"name": d.name, "count": db.query(Job).filter(Job.current_stage == d.name).count()}
            for d in departments
        ]

        metal_stocks = db.query(MetalStock).all()

        return {
            "jobs": {
                "total": total_jobs, "active": active_jobs,
                "qc_pending": qc_pending, "completed": completed
            },
            "metal_stock": [
                {"type": s.metal_type, "stock_type": s.stock_type, "qty": float(s.quantity)}
                for s in metal_stocks
            ],
            "scrap_pending_batches": scrap_pending,
            "active_karigars": active_karigars,
            "low_stock_alerts": low_stock,
            "pipeline": pipeline
        }


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/weight-variance")
def weight_variance_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "QC Officer"))
):
    """Stage-wise weight variance analysis"""
    try:
        stages = db.query(JobStageLog).filter(
            JobStageLog.weight_in != None,
            JobStageLog.weight_out != None
        ).all()
        return [
            {
                "job_id": s.job_id, "stage": s.stage_name,
                "weight_in": float(s.weight_in),
                "weight_out": float(s.weight_out),
                "variance": float(s.weight_variance) if s.weight_variance else 0,
                "variance_pct": float(s.variance_pct) if s.variance_pct else 0
            }
            for s in stages
        ]


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/metal-reconciliation")
def metal_recon_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant"))
):
    """Full metal reconciliation report"""
    try:
        return _metal_recon_helper(db, current_user)
    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")


@reports_router.get("/daily-metal-reconciliation")
def daily_metal_reconciliation(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    metal_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant"))
):
    """Day-wise metal reconciliation — issued, returned, net per day"""
    from sqlalchemy import cast, Date as SADate
    try:
        query = db.query(
            cast(MetalLedger.created_at, SADate).label("day"),
            MetalLedger.metal_type,
            MetalLedger.transaction_type,
            func.sum(MetalLedger.weight).label("total_weight"),
            func.sum(MetalLedger.fine_weight).label("total_fine"),
            func.sum(MetalLedger.total_value).label("total_value"),
            func.count(MetalLedger.id).label("tx_count"),
        ).group_by(
            cast(MetalLedger.created_at, SADate),
            MetalLedger.metal_type,
            MetalLedger.transaction_type
        ).order_by(cast(MetalLedger.created_at, SADate).desc(), MetalLedger.metal_type)

        if from_date:
            query = query.filter(MetalLedger.created_at >= from_date)
        if to_date:
            query = query.filter(MetalLedger.created_at <= to_date + " 23:59:59")
        if metal_type:
            query = query.filter(MetalLedger.metal_type == metal_type)

        rows = query.all()

        # Pivot: group by day+metal, then show issued/returned/net
        from collections import defaultdict
        pivot = defaultdict(lambda: {
            "issued": 0.0, "returned": 0.0, "adjusted": 0.0,
            "fine_issued": 0.0, "fine_returned": 0.0,
            "value_issued": 0.0, "tx_count": 0
        })

        for row in rows:
            key = (str(row.day), row.metal_type)
            p = pivot[key]
            p["tx_count"] += row.tx_count
            if row.transaction_type == "Issue":
                p["issued"]       += float(row.total_weight or 0)
                p["fine_issued"]  += float(row.total_fine or 0)
                p["value_issued"] += float(row.total_value or 0)
            elif row.transaction_type == "Return":
                p["returned"]      += float(row.total_weight or 0)
                p["fine_returned"] += float(row.total_fine or 0)
            elif row.transaction_type in ("Adjustment", "Refinery In", "Refinery Out"):
                p["adjusted"] += float(row.total_weight or 0)

        result = [
            {
                "date": day,
                "metal_type": metal,
                "issued":        round(p["issued"], 4),
                "returned":      round(p["returned"], 4),
                "net_outstanding": round(p["issued"] - p["returned"], 4),
                "fine_issued":   round(p["fine_issued"], 4),
                "fine_returned": round(p["fine_returned"], 4),
                "value_issued":  round(p["value_issued"], 2),
                "adjustments":   round(p["adjusted"], 4),
                "tx_count":      p["tx_count"],
            }
            for (day, metal), p in sorted(pivot.items(), key=lambda x: x[0][0], reverse=True)
        ]

        # Summary totals
        total_issued    = round(sum(r["issued"] for r in result), 4)
        total_returned  = round(sum(r["returned"] for r in result), 4)
        total_value     = round(sum(r["value_issued"] for r in result), 2)

        return {
            "rows": result,
            "summary": {
                "total_issued": total_issued,
                "total_returned": total_returned,
                "net_outstanding": round(total_issued - total_returned, 4),
                "total_value_issued": total_value,
                "days_count": len(set(r["date"] for r in result)),
                "tx_count": sum(r["tx_count"] for r in result),
            }
        }
    except Exception as e:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Daily recon error: {str(e)}")


@reports_router.get("/karigar-productivity")
def karigar_productivity_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Karigar performance and productivity"""
    try:
        return _wage_report_helper(db, current_user)


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/audit-trail")
def audit_trail(
    page: int = 1,
    module: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """System audit trail"""
    try:
        query = db.query(ActivityLog).order_by(ActivityLog.created_at.desc())
        if module:
            query = query.filter(ActivityLog.module == module)
        result = paginate(query, page, 50)
        result["items"] = [
            {
                "id": l.id, "user_id": l.user_id, "action": l.action,
                "module": l.module, "record_id": l.record_id,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in result["items"]
        ]
        return result


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/department-loss")
def department_loss_analysis(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Department-wise weight loss analysis — weight in vs weight out per stage"""
    try:
        departments = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
        report = []

        for dept in departments:
            logs = db.query(JobStageLog).filter(
                JobStageLog.stage_name == dept.name,
                JobStageLog.status == "Completed"
            ).all()

            total_weight_in = sum(float(l.weight_in or 0) for l in logs)
            total_weight_out = sum(float(l.weight_out or 0) for l in logs)
            total_variance = sum(float(l.weight_variance or 0) for l in logs)
            avg_variance_pct = (
                sum(float(l.variance_pct or 0) for l in logs) / len(logs)
                if logs else 0
            )

            report.append({
                "department": dept.name,
                "stage_order": dept.stage_order,
                "jobs_processed": len(logs),
                "total_weight_in": round(total_weight_in, 4),
                "total_weight_out": round(total_weight_out, 4),
                "total_loss": round(total_variance, 4),
                "avg_loss_pct": round(avg_variance_pct, 3),
            })

        return {
            "departments": report,
            "overall_loss": round(sum(r["total_loss"] for r in report), 4)
        }


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/cost-comparison")
def cost_comparison_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Accountant"))
):
    """Job cost comparison — target vs actual cost, profit analysis"""
    try:
        costs = db.query(JobCost).all()
        job_ids = [c.job_id for c in costs]
        jobs = {j.id: j for j in db.query(Job).filter(Job.id.in_(job_ids)).all()} if job_ids else {}

        items = []
        total_revenue = 0
        total_cost = 0

        for c in costs:
            job = jobs.get(c.job_id)
            sale = float(c.sale_price or 0)
            total = float(c.total_cost or 0)
            profit = round(sale - total, 2)
            margin = round(profit / sale * 100, 2) if sale > 0 else 0
            total_revenue += sale
            total_cost += total

            items.append({
                "job_id": c.job_id,
                "job_code": job.job_code if job else "",
                "design_name": job.design_name if job else "",
                "metal_type": job.metal_type if job else "",
                "total_cost": total,
                "sale_price": sale,
                "profit": profit,
                "margin_pct": margin,
            })

        items.sort(key=lambda x: x["profit"], reverse=True)

        return {
            "summary": {
                "total_jobs": len(items),
                "total_revenue": round(total_revenue, 2),
                "total_cost": round(total_cost, 2),
                "total_profit": round(total_revenue - total_cost, 2),
                "avg_margin_pct": round((total_revenue - total_cost) / total_revenue * 100, 2) if total_revenue > 0 else 0
            },
            "jobs": items
        }
    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/refinery-recovery")
def refinery_recovery_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager", "Accountant"))
):
    """Refinery recovery efficiency report — expected vs actual fine gold"""
    try:
        dispatches = db.query(RefineryDispatch).order_by(RefineryDispatch.dispatch_date.desc()).all()
        report = []
        total_expected = 0
        total_received = 0
        for d in dispatches:
            s = d.settlement
            expected = float(d.expected_fine_gold) if d.expected_fine_gold else 0
            received = float(s.fine_gold_received) if s else None
            charges = float(s.refining_charges) if s else 0
            recovery = float(s.recovery_pct) if s else None
            variance = float(s.variance_pct) if s else None
            total_expected += expected
            if received: total_received += received
            report.append({
                "dispatch_no": d.dispatch_no,
                "refinery_name": d.refinery_name,
                "dispatch_date": str(d.dispatch_date),
                "gross_weight": float(d.total_gross_weight),
                "expected_fine_gold": expected,
                "fine_gold_received": received,
                "recovery_pct": recovery,
                "variance_pct": variance,
                "refining_charges": charges,
                "status": d.status
            })
        return {
            "summary": {
                "total_dispatches": len(dispatches),
                "settled": sum(1 for d in dispatches if d.status == "Settled"),
                "pending": sum(1 for d in dispatches if d.status == "Dispatched"),
                "total_expected_fine": round(total_expected, 4),
                "total_received_fine": round(total_received, 4),
                "overall_variance": round(total_received - total_expected, 4)
            },
            "dispatches": report
        }


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/scrap-generation")
def scrap_generation_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Metal Store Manager"))
):
    """Scrap generation report by department and type"""
    try:
        by_dept = db.query(
            Department.name,
            func.sum(ScrapEntry.gross_weight),
            func.count(ScrapEntry.id)
        ).join(ScrapEntry, ScrapEntry.source_department_id == Department.id
        ).group_by(Department.name).all()

        by_type = db.query(
            ScrapEntry.scrap_type,
            func.sum(ScrapEntry.gross_weight),
            func.count(ScrapEntry.id)
        ).group_by(ScrapEntry.scrap_type).all()

        total = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0

        return {
            "total_scrap_weight": round(float(total), 4),
            "by_department": [
                {"department": name, "total_weight": round(float(w), 4), "batches": int(c)}
                for name, w, c in by_dept
            ],
            "by_type": [
                {"type": t, "total_weight": round(float(w), 4), "batches": int(c)}
                for t, w, c in by_type
            ]
        }


    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

@reports_router.get("/job-history")
def job_history_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant", "QC Officer"))
):
    """Job history report with date-range and customer/status filters"""
    try:
        query = db.query(Job).options(joinedload(Job.customer))

        if date_from:
            query = query.filter(Job.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.filter(Job.created_at <= datetime.combine(date_to, datetime.max.time()))
        if customer_id:
            query = query.filter(Job.customer_id == customer_id)
        if status:
            query = query.filter(Job.status == status)

        query = query.order_by(Job.created_at.desc())
        result = paginate(query, page, per_page)

        result["items"] = [
            {
                "id": j.id, "job_code": j.job_code,
                "customer_name": j.customer.name if j.customer else "",
                "design_name": j.design_name,
                "metal_type": j.metal_type,
                "target_weight": float(j.target_weight),
                "current_weight": float(j.current_weight) if j.current_weight else 0.0,
                "status": j.status,
                "priority": j.priority,
                "current_stage": j.current_stage,
                "expected_delivery": str(j.expected_delivery) if j.expected_delivery else None,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in result["items"]
        ]

        # Summary stats
        all_filtered = query.all()
        result["summary"] = {
            "total": len(all_filtered),
            "completed": sum(1 for j in all_filtered if j.status == "Completed"),
            "active": sum(1 for j in all_filtered if j.status == "Active"),
            "on_hold": sum(1 for j in all_filtered if j.status == "On Hold"),
        }
        return result


    # ============================================================
    # USERS & CUSTOMERS ROUTER
    # ============================================================
    except Exception as _report_err:
        raise __import__("fastapi").HTTPException(status_code=500, detail=f"Report error: {str(_report_err)}")

users_router = APIRouter(prefix="/api/v1/users", tags=["Users"])
customers_router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])
departments_router = APIRouter(prefix="/api/v1/departments", tags=["Departments"])


class UserCreateRequest(BaseModel):
    name: str
    email: str
    username: str
    password: str
    role_id: int


class CustomerCreateRequest(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None


@users_router.get("/")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """List all users (Admin only)"""
    users = db.query(User).all()
    return [
        {
            "id": u.id, "name": u.name, "email": u.email,
            "username": u.username, "role": u.role.name if u.role else None,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None
        }
        for u in users
    ]


@users_router.post("/")
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Create new user (Admin only)"""
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        name=data.name, email=data.email, username=data.username,
        password_hash=hash_password(data.password), role_id=data.role_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_activity(db, current_user.id, f"Created user {user.username}", "Users", user.id)
    db.commit()
    return {"id": user.id, "username": user.username}


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None


@users_router.put("/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Update user details or role (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.name: user.name = data.name
    if data.email: user.email = data.email
    if data.role_id: user.role_id = data.role_id
    if data.is_active is not None: user.is_active = data.is_active
    db.commit()
    log_activity(db, current_user.id, f"Updated user {user.username}", "Users", user.id)
    db.commit()
    return {"id": user.id, "username": user.username, "message": "Updated"}


@users_router.delete("/{user_id}")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Deactivate user account (Admin only, soft delete)"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    log_activity(db, current_user.id, f"Deactivated user {user.username}", "Users", user.id)
    db.commit()
    return {"message": f"User '{user.username}' deactivated"}


@users_router.get("/roles")
def list_roles(db: Session = Depends(get_db), current_user: User = Depends(require_roles("Admin"))):
    """List all roles"""
    roles = db.query(Role).all()
    return [{"id": r.id, "name": r.name} for r in roles]


@customers_router.get("/")
def list_customers(db: Session = Depends(get_db), current_user: User = Depends(require_roles("Admin"))):
    """List all active customers"""
    customers = db.query(Customer).filter(Customer.is_active == True).all()
    return [
        {"id": c.id, "name": c.name, "contact_person": c.contact_person,
         "phone": c.phone, "email": c.email, "gst_number": c.gst_number}
        for c in customers
    ]


@customers_router.post("/")
def create_customer(
    data: CustomerCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant"))
):
    """Add new customer"""
    # Duplicate checks
    if data.phone:
        existing = db.query(Customer).filter(Customer.phone == data.phone, Customer.is_active == True).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Phone already registered with customer '{existing.name}'")
    if data.gst_number:
        existing = db.query(Customer).filter(Customer.gst_number == data.gst_number.upper(), Customer.is_active == True).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"GST number already registered with customer '{existing.name}'")
    if data.gst_number:
        data.gst_number = data.gst_number.upper()
    c = Customer(**data.dict())
    db.add(c)
    db.commit()
    db.refresh(c)
    log_activity(db, current_user.id, f"Created customer {c.name}", "Customers", c.id)
    db.commit()
    return {"id": c.id, "name": c.name}


@customers_router.put("/{customer_id}")
def update_customer(
    customer_id: int,
    data: CustomerCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Update customer details"""
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Duplicate checks (exclude self)
    if data.phone:
        existing = db.query(Customer).filter(Customer.phone == data.phone, Customer.is_active == True, Customer.id != customer_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Phone already registered with customer '{existing.name}'")
    if data.gst_number:
        existing = db.query(Customer).filter(Customer.gst_number == data.gst_number.upper(), Customer.is_active == True, Customer.id != customer_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"GST number already registered with customer '{existing.name}'")
    if data.gst_number:
        data.gst_number = data.gst_number.upper()
    for field, value in data.dict(exclude_none=True).items():
        setattr(c, field, value)
    db.commit()
    log_activity(db, current_user.id, f"Updated customer {c.name}", "Customers", c.id)
    db.commit()
    return {"id": c.id, "name": c.name, "message": "Updated"}


@customers_router.delete("/{customer_id}")
def deactivate_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Deactivate customer (soft delete)"""
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    c.is_active = False
    db.commit()
    log_activity(db, current_user.id, f"Deactivated customer {c.name}", "Customers", c.id)
    db.commit()
    return {"message": f"Customer '{c.name}' deactivated"}


@customers_router.get("/{customer_id}")
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager", "Accountant"))
):
    """Get single customer details with order stats"""
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Calculate total order value from JobCost
    total_value = db.query(func.sum(JobCost.total_cost)).join(Job, Job.id == JobCost.job_id).filter(Job.customer_id == customer_id).scalar() or 0
    job_counts = db.query(Job.status, func.count(Job.id)).filter(Job.customer_id == customer_id).group_by(Job.status).all()
    active_jobs = sum(cnt for status, cnt in job_counts if status not in ["Completed", "Dispatched", "Cancelled"])
    total_jobs = sum(cnt for _, cnt in job_counts)
    return {
        "id": c.id, "name": c.name, "contact_person": c.contact_person,
        "phone": c.phone, "email": c.email, "address": c.address,
        "gst_number": c.gst_number, "is_active": c.is_active,
        "total_order_value": float(total_value),
        "total_jobs": total_jobs,
        "active_jobs": active_jobs
    }


@departments_router.get("/")
def list_departments(db: Session = Depends(get_db), current_user: User = Depends(require_roles("Admin", "Production Manager", "Department Operator"))):
    """List all production departments in order with active job count"""
    depts = db.query(Department).filter(
        Department.is_active == True
    ).order_by(Department.stage_order).all()
    result = []
    for d in depts:
        active_jobs = db.query(Job).filter(Job.current_stage == d.name, Job.status.notin_(["Completed", "Dispatched", "Cancelled"])).count()
        result.append({
            "id": d.id, "name": d.name, "stage_order": d.stage_order,
            "requires_weight": d.requires_weight, "requires_approval": d.requires_approval,
            "description": getattr(d, "description", None),
            "active_jobs": active_jobs
        })
    return result


class DepartmentCreateRequest(BaseModel):
    name: str
    stage_order: int
    requires_weight: bool = True
    requires_approval: bool = False
    description: Optional[str] = None


@departments_router.post("/")
def create_department(
    data: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Create new department (Admin only)"""
    existing = db.query(Department).filter(Department.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Department with this name already exists")
    dept = Department(
        name=data.name, stage_order=data.stage_order,
        requires_weight=data.requires_weight,
        requires_approval=data.requires_approval,
        is_active=True
    )
    if data.description and hasattr(dept, "description"):
        dept.description = data.description
    db.add(dept)
    db.commit()
    db.refresh(dept)
    log_activity(db, current_user.id, f"Created department {dept.name}", "Departments", dept.id)
    db.commit()
    return {"id": dept.id, "name": dept.name, "stage_order": dept.stage_order}


@departments_router.put("/{dept_id}")
def update_department(
    dept_id: int,
    data: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Update department (Admin only)"""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    dept.name = data.name
    dept.stage_order = data.stage_order
    dept.requires_weight = data.requires_weight
    dept.requires_approval = data.requires_approval
    if data.description is not None and hasattr(dept, "description"):
        dept.description = data.description
    db.commit()
    log_activity(db, current_user.id, f"Updated department {dept.name}", "Departments", dept.id)
    db.commit()
    return {"id": dept.id, "name": dept.name, "message": "Updated"}


@departments_router.delete("/{dept_id}")
def deactivate_department(
    dept_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Deactivate department (Admin only, soft delete). Returns warning if active jobs present."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    active_jobs = db.query(Job).filter(Job.current_stage == dept.name, Job.status.notin_(["Completed","Dispatched","Cancelled"])).count()
    if active_jobs > 0 and not force:
        raise HTTPException(status_code=409, detail=f"WARNING:{active_jobs} active job(s) are currently in this stage. Pass force=true to remove anyway.")
    dept.is_active = False
    db.commit()
    log_activity(db, current_user.id, f"Deactivated department {dept.name}", "Departments", dept.id)
    db.commit()
    return {"message": f"Department '{dept.name}' deactivated", "had_active_jobs": active_jobs}


# Helper references for reports
def _metal_recon_helper(db, current_user):
    issued = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
    returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
    stocks = db.query(MetalStock).all()
    return {
        "total_issued": float(issued), "total_returned": float(returned),
        "net_outstanding": float(issued) - float(returned),
        "current_stock": [{"metal": s.metal_type, "type": s.stock_type, "qty": float(s.quantity)} for s in stocks]
    }


def _wage_report_helper(db, current_user):
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    return [
        {
            "karigar_id": k.id, "name": k.name, "karigar_code": k.karigar_code,
            "skill": k.skill_type, "piece_rate": float(k.piece_rate),
            "total_wages": float(db.query(func.sum(KarigarAssignment.labour_cost)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0),
            "pending_pieces": int(db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(KarigarAssignment.karigar_id == k.id, KarigarAssignment.status != "Completed").scalar() or 0)
        }
        for k in karigars
    ]


# ============================================================
# DESIGN ROUTER
# ============================================================
designs_router = APIRouter(prefix="/api/v1/designs", tags=["Designs"])

UPLOAD_DIR = "uploads/designs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class DesignCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


@designs_router.get("/")
def list_designs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """List all designs"""
    designs = db.query(Design).order_by(Design.created_at.desc()).all()
    return [
        {
            "id": d.id, "design_code": d.design_code, "name": d.name,
            "description": d.description,
            "image_path": d.image_path,
            "created_at": d.created_at.isoformat() if d.created_at else None
        }
        for d in designs
    ]


@designs_router.post("/")
def create_design(
    name: str,
    description: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Create new design (without image)"""
    count = db.query(Design).count() + 1
    design = Design(
        design_code=f"DES-{str(count).zfill(4)}",
        name=name,
        description=description,
        created_by=current_user.id
    )
    db.add(design)
    db.commit()
    db.refresh(design)
    log_activity(db, current_user.id, f"Created design {design.design_code}", "Designs", design.id)
    db.commit()
    return {"id": design.id, "design_code": design.design_code, "name": design.name}


@designs_router.post("/{design_id}/upload-image")
async def upload_design_image(
    design_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Upload image for a design (JPG/PNG, max 5MB)"""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    # Validate file type
    allowed = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPG/PNG/WEBP images allowed")

    # Read and check size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Max 5MB allowed.")

    # Save file
    ext = file.filename.split(".")[-1].lower()
    filename = f"{design.design_code}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    design.image_path = filepath
    db.commit()
    log_activity(db, current_user.id, f"Uploaded image for design {design.design_code}", "Designs", design.id)
    db.commit()

    return {
        "message": "Image uploaded successfully",
        "design_code": design.design_code,
        "image_path": filepath
    }


@designs_router.get("/{design_id}/image")
def get_design_image(
    design_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Get design image as base64 (for frontend display)"""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")
    if not design.image_path or not os.path.exists(design.image_path):
        raise HTTPException(status_code=404, detail="No image uploaded for this design")

    with open(design.image_path, "rb") as f:
        img_bytes = f.read()
    ext = design.image_path.split(".")[-1].lower()
    mime = f"image/{'jpeg' if ext == 'jpg' else ext}"
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return {"image_base64": f"data:{mime};base64,{b64}", "design_code": design.design_code}


@designs_router.put("/{design_id}")
def update_design(
    design_id: int,
    data: DesignCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Production Manager"))
):
    """Update design name/description"""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")
    design.name = data.name
    if data.description is not None:
        design.description = data.description
    db.commit()
    log_activity(db, current_user.id, f"Updated design {design.design_code}", "Designs", design.id)
    db.commit()
    return {"id": design.id, "design_code": design.design_code, "name": design.name, "message": "Updated"}


@designs_router.delete("/{design_id}")
def delete_design(
    design_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    """Delete design and its image (Admin only)"""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    # Delete image file if exists
    if design.image_path and os.path.exists(design.image_path):
        os.remove(design.image_path)

    db.delete(design)
    db.commit()
    return {"message": f"Design '{design.design_code}' deleted"}