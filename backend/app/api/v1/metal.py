from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import MetalStock, MetalLedger, User
from app.services.helpers import paginate
from pydantic import BaseModel

router = APIRouter(prefix="/metal", tags=["Metal Accounting"])


class MetalIssue(BaseModel):
    metal_type: str
    weight: float
    purity: float
    issue_rate: float
    issued_to_type: str
    issued_to_id: int
    issued_to_name: str
    job_id: Optional[int] = None
    notes: Optional[str] = None


class MetalReturn(BaseModel):
    metal_type: str
    weight: float
    purity: float
    from_type: str
    from_id: int
    from_name: str
    job_id: Optional[int] = None
    notes: Optional[str] = None


@router.get("/stock")
def get_stock(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Current metal stock by type"""
    stocks = db.query(MetalStock).all()
    return [{"id": s.id, "metal_type": s.metal_type, "stock_type": s.stock_type,
             "quantity": float(s.quantity), "purity": float(s.purity) if s.purity else None} for s in stocks]


@router.post("/issue")
def issue_metal(data: MetalIssue, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    """Issue metal to department or karigar (ACID transaction)"""
    fine_weight = round(data.weight * data.purity / 100, 4)
    total_value = round(data.weight * data.issue_rate, 2)

    # Get current stock balance
    stock = db.query(MetalStock).filter(MetalStock.metal_type == data.metal_type).first()
    if not stock or float(stock.quantity) < data.weight:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    with db.begin_nested():
        # Deduct from stock
        stock.quantity = float(stock.quantity) - data.weight

        # Record in ledger
        txn = MetalLedger(
            transaction_type="Issue", metal_type=data.metal_type, weight=data.weight,
            purity=data.purity / 100, fine_weight=fine_weight, issue_rate=data.issue_rate,
            total_value=total_value, issued_to_type=data.issued_to_type,
            issued_to_id=data.issued_to_id, issued_to_name=data.issued_to_name,
            job_id=data.job_id, balance_after=float(stock.quantity), notes=data.notes,
            created_by=current_user.id
        )
        db.add(txn)

    db.commit()
    return {"message": "Metal issued", "transaction_id": txn.id,
            "fine_weight": fine_weight, "total_value": total_value}


@router.post("/return")
def return_metal(data: MetalReturn, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    """Record metal return and update stock"""
    fine_weight = round(data.weight * data.purity / 100, 4)
    stock = db.query(MetalStock).filter(MetalStock.metal_type == data.metal_type).first()

    with db.begin_nested():
        if stock:
            stock.quantity = float(stock.quantity) + data.weight
        txn = MetalLedger(
            transaction_type="Return", metal_type=data.metal_type, weight=data.weight,
            purity=data.purity / 100, fine_weight=fine_weight,
            issued_to_type=data.from_type, issued_to_id=data.from_id,
            issued_to_name=data.from_name, job_id=data.job_id,
            balance_after=float(stock.quantity) if stock else None,
            notes=data.notes, created_by=current_user.id
        )
        db.add(txn)

    db.commit()
    return {"message": "Metal returned", "transaction_id": txn.id}


@router.get("/ledger")
def get_ledger(page: int = Query(1, ge=1), per_page: int = Query(30, le=100),
               metal_type: Optional[str] = None,
               db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Paginated metal transaction ledger"""
    query = db.query(MetalLedger).order_by(MetalLedger.created_at.desc())
    if metal_type:
        query = query.filter(MetalLedger.metal_type == metal_type)
    result = paginate(query, page, per_page)
    result["items"] = [
        {"id": t.id, "type": t.transaction_type, "metal": t.metal_type,
         "weight": float(t.weight), "purity": float(t.purity) if t.purity else None,
         "fine_weight": float(t.fine_weight) if t.fine_weight else None,
         "rate": float(t.issue_rate) if t.issue_rate else None,
         "value": float(t.total_value) if t.total_value else None,
         "to_name": t.issued_to_name, "to_type": t.issued_to_type,
         "balance": float(t.balance_after) if t.balance_after else None,
         "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in result["items"]
    ]
    return result


@router.get("/reconciliation")
def reconciliation(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Daily metal reconciliation"""
    issued = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Issue").scalar() or 0
    returned = db.query(func.sum(MetalLedger.weight)).filter(MetalLedger.transaction_type == "Return").scalar() or 0
    stocks = db.query(MetalStock).all()
    return {
        "total_issued": float(issued),
        "total_returned": float(returned),
        "net_outstanding": float(issued) - float(returned),
        "current_stock": [{"metal": s.metal_type, "type": s.stock_type,
                            "qty": float(s.quantity)} for s in stocks]
    }
