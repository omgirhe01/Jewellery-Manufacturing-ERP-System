from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
from datetime import date
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import (Job, Department, MetalStock, MetalLedger,
                                    ScrapEntry, Karigar, KarigarAssignment,
                                    JobStageLog, JobCost, RefineryDispatch,
                                    RefinerySettlement, ActivityLog, User,
                                    InventoryItem, Customer)
from app.services.helpers import paginate

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    total_jobs  = db.query(Job).count()
    active_jobs = db.query(Job).filter(Job.status.in_(["New","Active"])).count()
    qc_pending  = db.query(Job).filter(Job.status == "QC Pending").count()
    completed   = db.query(Job).filter(Job.status.in_(["Completed","Dispatched"])).count()
    on_hold     = db.query(Job).filter(Job.status == "On Hold").count()
    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    pipeline = [{"name": d.name, "count": db.query(Job).filter(Job.current_stage == d.name).count()} for d in depts]
    metal_stocks = db.query(MetalStock).all()
    scrap_pending = db.query(ScrapEntry).filter(ScrapEntry.status.in_(["Collected","In Stock"])).count()
    active_karigars = db.query(Karigar).filter(Karigar.is_active == True).count()
    refinery_pending = db.query(RefineryDispatch).filter(RefineryDispatch.status == "Dispatched").count()
    return {
        "jobs": {"total": total_jobs, "active": active_jobs, "qc_pending": qc_pending,
                  "completed": completed, "on_hold": on_hold},
        "pipeline": pipeline,
        "metal_stock": [{"metal": s.metal_type, "type": s.stock_type, "qty": float(s.quantity)} for s in metal_stocks],
        "scrap_pending_batches": scrap_pending,
        "active_karigars": active_karigars,
        "refinery_pending": refinery_pending
    }


@router.get("/master-summary")
def master_summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    today = date.today()
    total_jobs  = db.query(Job).count()
    active_jobs = db.query(Job).filter(Job.status.in_(["New","Active"])).count()
    qc_pending  = db.query(Job).filter(Job.status == "QC Pending").count()
    completed   = db.query(Job).filter(Job.status.in_(["Completed","Dispatched"])).count()
    overdue     = db.query(Job).filter(
        Job.expected_delivery < today,
        Job.status.notin_(["Completed","Dispatched","Cancelled"])
    ).count()
    issued   = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
    returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
    metal_stocks = db.query(MetalStock).all()
    active_kar   = db.query(Karigar).filter(Karigar.is_active == True).count()
    total_wages  = db.query(func.sum(KarigarAssignment.labour_cost)).scalar() or 0
    costs = db.query(JobCost).all()
    total_revenue = sum(float(c.sale_price) for c in costs)
    total_cost    = sum(float(c.total_cost)  for c in costs)
    scrap_pending = db.query(ScrapEntry).filter(ScrapEntry.status.in_(["Collected","In Stock"])).count()
    scrap_weight  = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
    low_stock_items = db.query(InventoryItem).filter(
        InventoryItem.is_active == True,
        InventoryItem.current_stock <= InventoryItem.reorder_level
    ).count()
    pending_refinery = db.query(RefineryDispatch).filter(RefineryDispatch.status == "Dispatched").count()
    return {
        "jobs": {"total": total_jobs, "active": active_jobs, "qc_pending": qc_pending, "completed": completed},
        "metal": {
            "total_issued": float(issued), "total_returned": float(returned),
            "outstanding": float(issued) - float(returned),
            "stocks": [{"metal": s.metal_type, "type": s.stock_type, "qty": float(s.quantity)} for s in metal_stocks]
        },
        "karigars": {"active": active_kar, "total_wages": float(total_wages)},
        "financials": {"total_revenue": total_revenue, "total_cost": total_cost, "gross_profit": total_revenue - total_cost},
        "scrap": {"pending_batches": scrap_pending, "total_weight": float(scrap_weight)},
        "alerts": {"overdue_jobs": overdue, "low_stock_items": low_stock_items, "pending_refinery_settlements": pending_refinery}
    }


@router.get("/job-history")
def job_history(
    status: Optional[str] = None,
    metal_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    per_page: int = Query(200, le=500),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = db.query(Job).options(joinedload(Job.customer))
    if status:     query = query.filter(Job.status == status)
    if metal_type: query = query.filter(Job.metal_type == metal_type)
    if from_date:  query = query.filter(Job.created_at >= from_date)
    if to_date:    query = query.filter(Job.created_at <= to_date + " 23:59:59")
    query = query.order_by(Job.created_at.desc())
    result = paginate(query, page, per_page)
    result["items"] = [{
        "id": j.id, "job_code": j.job_code, "design_name": j.design_name,
        "customer": j.customer.name if j.customer else "",
        "metal_type": j.metal_type,
        "target_weight": float(j.target_weight),
        "current_weight": float(j.current_weight or 0),
        "wastage_allowed": float(j.wastage_allowed),
        "order_qty": j.order_qty,
        "current_stage": j.current_stage, "status": j.status, "priority": j.priority,
        "expected_delivery": str(j.expected_delivery) if j.expected_delivery else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    } for j in result["items"]]
    return result


@router.get("/weight-variance")
def weight_variance(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Stage-wise weight loss with allowed wastage comparison"""
    stages = db.query(JobStageLog).options(joinedload(JobStageLog.job)).filter(
        JobStageLog.weight_in != None, JobStageLog.weight_out != None
    ).all()
    result = []
    for s in stages:
        w_in     = float(s.weight_in)
        w_out    = float(s.weight_out)
        variance = round(w_in - w_out, 4)
        allowed  = float(s.job.wastage_allowed) if s.job else 0
        var_pct  = float(s.variance_pct) if s.variance_pct else (round((variance / w_in) * 100, 3) if w_in > 0 else 0)
        result.append({
            "job_id": s.job_id,
            "job_code": s.job.job_code if s.job else "",
            "design_name": s.job.design_name if s.job else "",
            "stage": s.stage_name,
            "weight_in": w_in, "weight_out": w_out,
            "variance": variance, "variance_pct": var_pct,
            "allowed_pct": allowed,
            "over_limit": var_pct > allowed,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None
        })
    result.sort(key=lambda x: (-int(x["over_limit"]), -x["variance"]))
    return result


@router.get("/department-loss")
def department_loss(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Department-wise metal loss analysis"""
    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    result = []
    for d in depts:
        stages = db.query(JobStageLog).filter(
            JobStageLog.department_id == d.id,
            JobStageLog.weight_in != None, JobStageLog.weight_out != None
        ).all()
        if not stages:
            result.append({"dept": d.name, "order": d.stage_order, "jobs": 0,
                           "total_in": 0, "total_out": 0, "total_loss": 0, "avg_loss_pct": 0})
            continue
        total_in  = sum(float(s.weight_in) for s in stages)
        total_out = sum(float(s.weight_out) for s in stages)
        total_loss = round(total_in - total_out, 4)
        result.append({
            "dept": d.name, "order": d.stage_order, "jobs": len(stages),
            "total_in": round(total_in, 4), "total_out": round(total_out, 4),
            "total_loss": total_loss,
            "avg_loss_pct": round((total_loss / total_in * 100), 3) if total_in > 0 else 0
        })
    return result


@router.get("/metal-reconciliation")
def metal_reconciliation(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    issued   = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
    returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
    by_metal = db.query(MetalLedger.metal_type, func.sum(MetalLedger.weight)).filter(
        MetalLedger.transaction_type == "Issue").group_by(MetalLedger.metal_type).all()
    dept_balances = db.query(MetalLedger.issued_to_name, func.sum(MetalLedger.weight)).filter(
        MetalLedger.issued_to_type == "Department").group_by(MetalLedger.issued_to_name).all()
    kar_balances = db.query(MetalLedger.issued_to_name, func.sum(MetalLedger.weight)).filter(
        MetalLedger.issued_to_type == "Karigar").group_by(MetalLedger.issued_to_name).all()
    return {
        "total_issued": float(issued), "total_returned": float(returned),
        "net_outstanding": float(issued) - float(returned),
        "by_metal": {m: float(w) for m, w in by_metal},
        "dept_balances": [{"name": n, "weight": float(w)} for n, w in dept_balances],
        "karigar_balances": [{"name": n, "weight": float(w)} for n, w in kar_balances]
    }


@router.get("/karigar-productivity")
def karigar_productivity(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    result = []
    for k in karigars:
        assigned  = db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0
        completed = db.query(func.sum(KarigarAssignment.pieces_completed)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0
        wages     = db.query(func.sum(KarigarAssignment.labour_cost)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0
        result.append({
            "name": k.name, "code": k.karigar_code, "skill": k.skill_type,
            "assigned": int(assigned), "completed": int(completed),
            "pending_pieces": int(assigned) - int(completed),
            "total_wages": float(wages),
            "efficiency": round(int(completed) / int(assigned) * 100, 1) if assigned else 0
        })
    return result


@router.get("/scrap-generation")
def scrap_generation(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    by_type = db.query(ScrapEntry.scrap_type, func.sum(ScrapEntry.gross_weight),
                        func.count(ScrapEntry.id)).group_by(ScrapEntry.scrap_type).all()
    total   = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
    pending = db.query(func.sum(ScrapEntry.gross_weight)).filter(
        ScrapEntry.status.in_(["Collected","In Stock"])).scalar() or 0
    return {
        "total_scrap_weight": float(total), "pending_weight": float(pending),
        "by_type": [{"type": t, "weight": float(w), "batches": int(c)} for t, w, c in by_type]
    }


@router.get("/refinery-recovery")
def refinery_recovery(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    dispatches = db.query(RefineryDispatch).options(
        joinedload(RefineryDispatch.settlement)
    ).order_by(RefineryDispatch.dispatch_date.desc()).all()
    rows = []
    total_gross = total_fine = settled_count = 0
    for d in dispatches:
        s = d.settlement
        total_gross += float(d.gross_weight)
        row = {
            "id": d.id,
            "dispatch_date": str(d.dispatch_date) if d.dispatch_date else None,
            "refinery_name": d.refinery_name,
            "gross_weight": float(d.gross_weight),
            "expected_fine": float(d.expected_fine_gold) if d.expected_fine_gold else 0,
            "status": d.status, "settlement": None
        }
        if s:
            settled_count += 1
            fine = float(s.fine_gold_received)
            total_fine += fine
            row["settlement"] = {
                "settlement_date": str(s.settlement_date),
                "fine_received": fine,
                "recovery_pct": float(s.recovery_pct) if s.recovery_pct else 0,
                "refining_charges": float(s.refining_charges),
                "variance_pct": float(s.variance_pct) if s.variance_pct else 0,
                "payment_status": s.payment_status
            }
        rows.append(row)
    return {
        "summary": {
            "total_dispatches": len(dispatches), "settled": settled_count,
            "pending": len(dispatches) - settled_count,
            "total_gross_weight": round(total_gross, 4),
            "total_fine_received": round(total_fine, 4),
            "avg_recovery_pct": round((total_fine / total_gross * 100), 2) if total_gross > 0 else 0
        },
        "dispatches": rows
    }


@router.get("/cost-comparison")
def cost_comparison(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    costs = db.query(JobCost).options(joinedload(JobCost.job)).all()
    total_revenue = sum(float(c.sale_price) for c in costs)
    total_cost    = sum(float(c.total_cost)  for c in costs)
    total_profit  = sum(float(c.profit_loss) for c in costs)
    rows = [{
        "job_id": c.job_id,
        "job_code": c.job.job_code if c.job else "",
        "design_name": c.job.design_name if c.job else "",
        "gold_cost": float(c.gold_cost or 0), "labour_cost": float(c.labour_cost or 0),
        "stone_cost": float(c.stone_cost or 0), "other_cost": float(c.other_cost or 0),
        "total_cost": float(c.total_cost), "sale_price": float(c.sale_price),
        "profit": float(c.profit_loss), "margin_pct": float(c.margin_pct or 0)
    } for c in costs]
    rows.sort(key=lambda x: x["margin_pct"])
    return {
        "summary": {
            "total_revenue": total_revenue, "total_cost": total_cost,
            "total_profit": total_profit,
            "avg_margin_pct": round(total_profit / total_revenue * 100, 2) if total_revenue else 0
        },
        "jobs": rows
    }


@router.get("/audit-trail")
def audit_trail(
    page: int = Query(1, ge=1),
    module: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = db.query(ActivityLog).order_by(ActivityLog.created_at.desc())
    if module:
        query = query.filter(ActivityLog.module == module)
    result = paginate(query, page, 50)
    user_ids = list({l.user_id for l in result["items"] if l.user_id})
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    result["items"] = [{
        "id": l.id, "user_id": l.user_id,
        "user_name": users.get(l.user_id, f"User #{l.user_id}"),
        "action": l.action, "module": l.module, "record_id": l.record_id,
        "at": l.created_at.isoformat() if l.created_at else None
    } for l in result["items"]]
    return result