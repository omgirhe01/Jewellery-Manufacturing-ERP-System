from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel

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
    FinishedGood, JobCost, ActivityLog, Notification, SystemSetting
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
def job_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
            variance = fmt_weight(current_stage_log.weight_in) - weight_out
            current_stage_log.weight_variance = round(variance, 4)
            if fmt_weight(current_stage_log.weight_in) > 0:
                current_stage_log.variance_pct = round(
                    variance / fmt_weight(current_stage_log.weight_in) * 100, 3
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
async def scale_status(current_user: User = Depends(get_current_user)):
    """Get scale connection status, mode, tare, last reading"""
    return await scale_service.get_status()


@scale_router.post("/read-weight")
async def read_weight(
    expected_weight: float = Query(10.0, description="Expected weight (used in simulation)"),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
async def clear_tare(current_user: User = Depends(get_current_user)):
    """Clear tare weight back to zero"""
    scale_service.clear_tare()
    return {"message": "Tare cleared", "tare": 0.0}


@scale_router.get("/detect-port")
async def detect_port(current_user: User = Depends(get_current_user)):
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
    current_user: User = Depends(get_current_user)
):
    """
    Log a confirmed weight reading against a job + department.
    Only STABLE readings should be passed here from frontend.
    """
    net_weight = round(gross_weight - tare_weight, 4)

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


@scale_router.get("/history/{job_id}")
def weight_history(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """All weight logs for a job, newest first"""
    logs = db.query(WeightLog).filter(
        WeightLog.job_id == job_id
    ).order_by(WeightLog.captured_at.desc()).all()

    return [
        {
            "id": l.id,
            "gross_weight": float(l.gross_weight),
            "tare_weight": float(l.tare_weight),
            "net_weight": float(l.net_weight),
            "scale_type": l.scale_type,
            "is_manual": l.is_manual_override,
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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

    return {"message": "Metal returned", "transaction_id": ledger.id, "new_balance": new_balance}


@metal_router.get("/ledger")
def get_metal_ledger(
    metal_type: Optional[str] = None,
    transaction_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    return {"id": k.id, "karigar_code": k.karigar_code, "name": k.name}


@karigar_router.post("/assign")
def assign_job(
    data: AssignmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    return {"message": "Assigned", "labour_cost": labour_cost, "id": assignment.id}


@karigar_router.get("/wage-report")
def wage_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
):
    """Karigar productivity tracking"""
    return wage_report(db, current_user)


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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
):
    """Record new scrap batch"""
    fine = round(data.gross_weight * data.estimated_purity / 100, 4)
    entry = ScrapEntry(
        batch_id=generate_batch_id("SCRAP"),
        source_department_id=data.source_department_id,
        scrap_type=data.scrap_type,
        gross_weight=data.gross_weight,
        estimated_purity=data.estimated_purity,
        estimated_fine_weight=fine,
        status="Collected",
        collected_by=current_user.id,
        notes=data.notes
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "batch_id": entry.batch_id, "estimated_fine_weight": fine}


@scrap_router.get("/summary")
def scrap_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    return {"dispatch_no": dispatch.dispatch_no, "expected_fine_gold": expected_fine}


@refinery_router.post("/settle")
def settle_dispatch(
    data: SettlementCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
):
    """List inventory items"""
    query = db.query(InventoryItem).filter(InventoryItem.is_active == True)
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


@inventory_router.post("/adjust")
def adjust_stock(
    data: StockAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    return {"message": "Stock updated", "new_balance": float(item.current_stock)}


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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
    return _cost_dict(cost)


@costing_router.get("/profitability")
def profitability_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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


@reports_router.get("/dashboard")
def dashboard_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Main dashboard KPIs"""
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


@reports_router.get("/weight-variance")
def weight_variance_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Stage-wise weight variance analysis"""
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


@reports_router.get("/metal-reconciliation")
def metal_recon_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Full metal reconciliation report"""
    return metal_reconciliation(db, current_user)


@reports_router.get("/karigar-productivity")
def karigar_productivity_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Karigar performance and productivity"""
    return wage_report(db, current_user)


@reports_router.get("/audit-trail")
def audit_trail(
    page: int = 1,
    module: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """System audit trail"""
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


# ============================================================
# USERS & CUSTOMERS ROUTER
# ============================================================
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
    return {"id": user.id, "username": user.username}


@users_router.get("/roles")
def list_roles(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all roles"""
    roles = db.query(Role).all()
    return [{"id": r.id, "name": r.name} for r in roles]


@customers_router.get("/")
def list_customers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
    current_user: User = Depends(get_current_user)
):
    """Add new customer"""
    c = Customer(**data.dict())
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "name": c.name}


@departments_router.get("/")
def list_departments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all production departments in order"""
    depts = db.query(Department).filter(
        Department.is_active == True
    ).order_by(Department.stage_order).all()
    return [
        {
            "id": d.id, "name": d.name, "stage_order": d.stage_order,
            "requires_weight": d.requires_weight, "requires_approval": d.requires_approval
        }
        for d in depts
    ]


# Helper references for reports
def metal_reconciliation(db, current_user):
    issued = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
    returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
    stocks = db.query(MetalStock).all()
    return {
        "total_issued": float(issued), "total_returned": float(returned),
        "net_outstanding": float(issued) - float(returned),
        "current_stock": [{"metal": s.metal_type, "type": s.stock_type, "qty": float(s.quantity)} for s in stocks]
    }


def wage_report(db, current_user):
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