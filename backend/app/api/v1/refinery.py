from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import RefineryDispatch, RefinerySettlement, ScrapEntry, MetalStock
from app.services.helpers import generate_dispatch_no
from pydantic import BaseModel

router = APIRouter(prefix="/refinery", tags=["Refinery Management"])


class DispatchCreate(BaseModel):
    refinery_name: str
    dispatch_date: date
    gross_weight: float
    estimated_purity: float
    notes: Optional[str] = None


class SettlementCreate(BaseModel):
    dispatch_id: int
    settlement_date: date
    fine_gold_received: float
    refining_charges: float = 0.0
    settlement_notes: Optional[str] = None


@router.get("/")
def list_dispatches(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    dispatches = db.query(RefineryDispatch).order_by(RefineryDispatch.dispatch_date.desc()).all()
    return [{"id": d.id, "dispatch_no": d.dispatch_no, "refinery": d.refinery_name,
              "date": str(d.dispatch_date), "gross_weight": float(d.gross_weight),
              "expected_fine": float(d.expected_fine_gold) if d.expected_fine_gold else None,
              "status": d.status} for d in dispatches]


@router.post("/dispatch")
def create_dispatch(data: DispatchCreate, db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    exp_fine = round(data.gross_weight * data.estimated_purity / 100, 4)
    dispatch = RefineryDispatch(dispatch_no=generate_dispatch_no(),
                                 refinery_name=data.refinery_name,
                                 dispatch_date=data.dispatch_date,
                                 gross_weight=data.gross_weight,
                                 estimated_purity=data.estimated_purity / 100,
                                 expected_fine_gold=exp_fine, notes=data.notes,
                                 created_by=current_user.id)
    db.add(dispatch)
    db.commit()
    return {"dispatch_no": dispatch.dispatch_no, "expected_fine": exp_fine}


@router.post("/settle")
def settle(data: SettlementCreate, db: Session = Depends(get_db),
           current_user=Depends(get_current_user)):
    dispatch = db.query(RefineryDispatch).filter(RefineryDispatch.id == data.dispatch_id).first()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    recovery = round((data.fine_gold_received / float(dispatch.gross_weight)) * 100, 3) if dispatch.gross_weight else 0
    variance = round(recovery - float(dispatch.estimated_purity or 0) * 100, 3)
    settlement = RefinerySettlement(dispatch_id=data.dispatch_id,
                                     settlement_date=data.settlement_date,
                                     fine_gold_received=data.fine_gold_received,
                                     recovery_pct=recovery / 100,
                                     refining_charges=data.refining_charges,
                                     variance_pct=variance / 100,
                                     settlement_notes=data.settlement_notes,
                                     created_by=current_user.id)
    db.add(settlement)
    dispatch.status = "Settled"
    # Update pure gold stock
    stock = db.query(MetalStock).filter(MetalStock.metal_type == "24K",
                                         MetalStock.stock_type == "Pure").first()
    if stock:
        stock.quantity = float(stock.quantity) + data.fine_gold_received
    db.commit()
    return {"message": "Settled", "recovery_pct": recovery, "variance_pct": variance}
