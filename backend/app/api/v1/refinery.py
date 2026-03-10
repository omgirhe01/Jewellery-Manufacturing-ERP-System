from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import date
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import RefineryDispatch, RefinerySettlement, MetalStock
from app.services.helpers import generate_dispatch_no
from pydantic import BaseModel

router = APIRouter(prefix="/refinery", tags=["Refinery Management"])


class DispatchCreate(BaseModel):
    refinery_name: str
    dispatch_date: date
    total_gross_weight: float
    estimated_purity: float
    notes: Optional[str] = None


class SettlementCreate(BaseModel):
    dispatch_id: int
    settlement_date: date
    fine_gold_received: float
    refining_charges: float = 0.0
    settlement_notes: Optional[str] = None


def _dispatch_dict(d: RefineryDispatch) -> dict:
    s = d.settlement
    return {
        "id":                 d.id,
        "dispatch_no":        d.dispatch_no,
        "refinery_name":      d.refinery_name,
        "dispatch_date":      str(d.dispatch_date),
        "total_gross_weight": float(d.total_gross_weight),
        "estimated_purity":   float(d.estimated_purity) * 100 if d.estimated_purity else None,
        "expected_fine_gold": float(d.expected_fine_gold) if d.expected_fine_gold else None,
        "status":             d.status,
        "notes":              d.notes,
        "created_at":         d.created_at.isoformat() if d.created_at else None,
        # Settlement fields (if settled)
        "fine_gold_received": float(s.fine_gold_received) if s else None,
        "recovery_pct":       float(s.recovery_pct) * 100 if s and s.recovery_pct else None,
        "refining_charges":   float(s.refining_charges) if s else None,
        "variance_pct":       float(s.variance_pct) * 100 if s and s.variance_pct else None,
        "settlement_date":    str(s.settlement_date) if s else None,
        "payment_status":     s.payment_status if s else None,
    }


@router.get("/")
def list_dispatches(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = db.query(RefineryDispatch).options(
        joinedload(RefineryDispatch.settlement)
    ).order_by(RefineryDispatch.dispatch_date.desc())
    if status:
        query = query.filter(RefineryDispatch.status == status)
    dispatches = query.all()
    return [_dispatch_dict(d) for d in dispatches]


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    from sqlalchemy import func
    dispatches = db.query(RefineryDispatch).options(
        joinedload(RefineryDispatch.settlement)
    ).all()

    total        = len(dispatches)
    pending      = sum(1 for d in dispatches if d.status == "Dispatched")
    total_gross  = sum(float(d.total_gross_weight) for d in dispatches)
    total_fine   = sum(
        float(d.settlement.fine_gold_received)
        for d in dispatches if d.settlement
    )
    total_charges = sum(
        float(d.settlement.refining_charges or 0)
        for d in dispatches if d.settlement
    )
    avg_recovery = (
        sum(float(d.settlement.recovery_pct or 0) * 100 for d in dispatches if d.settlement)
        / sum(1 for d in dispatches if d.settlement)
    ) if any(d.settlement for d in dispatches) else 0

    return {
        "total_dispatches":  total,
        "pending_settlement": pending,
        "total_gross_weight": total_gross,
        "total_fine_recovered": total_fine,
        "total_refining_charges": total_charges,
        "avg_recovery_pct": round(avg_recovery, 3),
    }


@router.post("/dispatch")
def create_dispatch(
    data: DispatchCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    exp_fine = round(data.total_gross_weight * data.estimated_purity / 100, 4)
    dispatch = RefineryDispatch(
        dispatch_no=generate_dispatch_no(),
        refinery_name=data.refinery_name,
        dispatch_date=data.dispatch_date,
        total_gross_weight=data.total_gross_weight,
        estimated_purity=data.estimated_purity / 100,
        expected_fine_gold=exp_fine,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(dispatch)
    db.commit()
    db.refresh(dispatch)
    return {
        "id":           dispatch.id,
        "dispatch_no":  dispatch.dispatch_no,
        "expected_fine_gold": exp_fine,
        "status":       dispatch.status,
    }


@router.post("/settle")
def settle(
    data: SettlementCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    dispatch = db.query(RefineryDispatch).filter(
        RefineryDispatch.id == data.dispatch_id
    ).first()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if dispatch.status == "Settled":
        raise HTTPException(status_code=400, detail="Already settled")

    gross    = float(dispatch.total_gross_weight)
    recovery = round(data.fine_gold_received / gross * 100, 3) if gross else 0
    variance = round(recovery - float(dispatch.estimated_purity or 0) * 100, 3)

    settlement = RefinerySettlement(
        dispatch_id=data.dispatch_id,
        settlement_date=data.settlement_date,
        fine_gold_received=data.fine_gold_received,
        recovery_pct=recovery / 100,
        refining_charges=data.refining_charges,
        variance_pct=variance / 100,
        notes=data.settlement_notes,
        created_by=current_user.id,
    )
    db.add(settlement)
    dispatch.status = "Settled"

    # Credit pure gold stock
    stock = db.query(MetalStock).filter(
        MetalStock.metal_type == "24K",
        MetalStock.stock_type == "Pure"
    ).first()
    if stock:
        stock.quantity = float(stock.quantity) + data.fine_gold_received

    db.commit()
    return {
        "message":      "Settlement recorded",
        "recovery_pct": recovery,
        "variance_pct": variance,
        "fine_gold_received": data.fine_gold_received,
    }


@router.get("/{dispatch_id}")
def get_dispatch(
    dispatch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    d = db.query(RefineryDispatch).options(
        joinedload(RefineryDispatch.settlement)
    ).filter(RefineryDispatch.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return _dispatch_dict(d)