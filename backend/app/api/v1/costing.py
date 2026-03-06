from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import JobCost, Job
from pydantic import BaseModel

router = APIRouter(prefix="/costing", tags=["Costing"])


class CostData(BaseModel):
    job_id: int
    gold_cost: float = 0
    labour_cost: float = 0
    stone_cost: float = 0
    wastage_cost: float = 0
    refinery_adjustment: float = 0
    overhead_cost: float = 0
    sale_price: float = 0


@router.get("/job/{job_id}")
def get_cost(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cost = db.query(JobCost).filter(JobCost.job_id == job_id).first()
    if not cost:
        raise HTTPException(status_code=404, detail="No cost data")
    return _cost_dict(cost)


@router.post("/calculate")
def calculate(data: CostData, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    total  = data.gold_cost + data.labour_cost + data.stone_cost + data.wastage_cost + data.refinery_adjustment + data.overhead_cost
    profit = data.sale_price - total
    margin = round(profit / data.sale_price * 100, 3) if data.sale_price else 0
    cost = db.query(JobCost).filter(JobCost.job_id == data.job_id).first()
    if not cost:
        cost = JobCost(job_id=data.job_id)
        db.add(cost)
    cost.gold_cost = data.gold_cost; cost.labour_cost = data.labour_cost
    cost.stone_cost = data.stone_cost; cost.wastage_cost = data.wastage_cost
    cost.refinery_adjustment = data.refinery_adjustment; cost.overhead_cost = data.overhead_cost
    cost.total_cost = total; cost.sale_price = data.sale_price
    cost.profit_loss = profit; cost.margin_pct = margin
    db.commit()
    return _cost_dict(cost)


def _cost_dict(c):
    return {"job_id": c.job_id, "gold_cost": float(c.gold_cost), "labour_cost": float(c.labour_cost),
            "stone_cost": float(c.stone_cost), "wastage_cost": float(c.wastage_cost),
            "refinery_adjustment": float(c.refinery_adjustment), "overhead_cost": float(c.overhead_cost),
            "total_cost": float(c.total_cost), "sale_price": float(c.sale_price),
            "profit_loss": float(c.profit_loss), "margin_pct": float(c.margin_pct)}
