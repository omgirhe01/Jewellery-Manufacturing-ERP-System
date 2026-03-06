from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import (Job, Department, MetalStock, MetalLedger,
                                    ScrapEntry, Karigar, KarigarAssignment,
                                    JobStage, JobCost, RefineryDispatch, ActivityLog)
from app.services.helpers import paginate

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Main KPI dashboard"""
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
        "metal_stock": [{"metal": s.metal_type, "type": s.stock_type,
                          "qty": float(s.quantity)} for s in metal_stocks],
        "scrap_pending_batches": scrap_pending,
        "active_karigars": active_karigars,
        "refinery_pending": refinery_pending
    }


@router.get("/weight-variance")
def weight_variance(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Stage-wise weight loss/variance report"""
    stages = db.query(JobStage).filter(
        JobStage.weight_in != None, JobStage.weight_out != None
    ).all()
    return [{"job_id": s.job_id, "stage": s.stage_name,
              "weight_in": float(s.weight_in), "weight_out": float(s.weight_out),
              "variance": round(float(s.weight_in) - float(s.weight_out), 4),
              "variance_pct": float(s.variance_pct) if s.variance_pct else None} for s in stages]


@router.get("/metal-reconciliation")
def metal_reconciliation(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Daily metal reconciliation summary"""
    issued   = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
    returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
    by_metal = db.query(MetalLedger.metal_type,
                         func.sum(MetalLedger.weight)).filter(
        MetalLedger.transaction_type == "Issue").group_by(MetalLedger.metal_type).all()
    return {"total_issued": float(issued), "total_returned": float(returned),
            "net_outstanding": float(issued) - float(returned),
            "by_metal": {m: float(w) for m, w in by_metal}}


@router.get("/karigar-productivity")
def karigar_productivity(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Karigar performance and productivity"""
    karigars = db.query(Karigar).filter(Karigar.is_active == True).all()
    result = []
    for k in karigars:
        assigned  = db.query(func.sum(KarigarAssignment.pieces_assigned)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0
        completed = db.query(func.sum(KarigarAssignment.pieces_completed)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0
        wages     = db.query(func.sum(KarigarAssignment.labour_cost)).filter(KarigarAssignment.karigar_id == k.id).scalar() or 0
        result.append({"name": k.name, "code": k.karigar_code, "skill": k.skill_type,
                        "assigned": int(assigned), "completed": int(completed),
                        "total_wages": float(wages),
                        "efficiency": round(int(completed)/int(assigned)*100,1) if assigned else 0})
    return result


@router.get("/scrap-trends")
def scrap_trends(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Scrap generation by type"""
    by_type = db.query(ScrapEntry.scrap_type, func.sum(ScrapEntry.gross_weight),
                        func.count(ScrapEntry.id)).group_by(ScrapEntry.scrap_type).all()
    total   = db.query(func.sum(ScrapEntry.gross_weight)).scalar() or 0
    return {"total_scrap_weight": float(total),
            "by_type": [{"type": t, "weight": float(w), "batches": int(c)} for t, w, c in by_type]}


@router.get("/profitability")
def profitability(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Job profitability analysis"""
    costs = db.query(JobCost).all()
    total_revenue = sum(float(c.sale_price) for c in costs)
    total_cost    = sum(float(c.total_cost)  for c in costs)
    total_profit  = sum(float(c.profit_loss) for c in costs)
    return {"summary": {"total_revenue": total_revenue, "total_cost": total_cost,
                         "total_profit": total_profit,
                         "avg_margin": round(total_profit/total_revenue*100,2) if total_revenue else 0},
            "jobs": [{"job_id": c.job_id, "total_cost": float(c.total_cost),
                       "sale_price": float(c.sale_price), "profit": float(c.profit_loss),
                       "margin_pct": float(c.margin_pct)} for c in costs]}


@router.get("/audit-trail")
def audit_trail(page: int = 1, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """System activity audit trail"""
    query = db.query(ActivityLog).order_by(ActivityLog.created_at.desc())
    result = paginate(query, page, 50)
    result["items"] = [{"id": l.id, "user_id": l.user_id, "action": l.action,
                         "module": l.module, "record_id": l.record_id,
                         "at": l.created_at.isoformat() if l.created_at else None}
                        for l in result["items"]]
    return result
