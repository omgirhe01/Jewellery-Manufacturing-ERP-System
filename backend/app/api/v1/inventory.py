from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.all_models import InventoryItem, InventoryTransaction
from pydantic import BaseModel

router = APIRouter(prefix="/inventory", tags=["Inventory"])


class ItemCreate(BaseModel):
    name: str
    category: str
    unit: str
    reorder_level: float = 0
    unit_cost: float = 0


class StockAdjust(BaseModel):
    item_id: int
    transaction_type: str
    quantity: float
    notes: Optional[str] = None


@router.get("/")
def list_items(category: Optional[str] = None, db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    query = db.query(InventoryItem).filter(InventoryItem.is_active == True)
    if category:
        query = query.filter(InventoryItem.category == category)
    items = query.all()
    return [{"id": i.id, "code": i.item_code, "name": i.name, "category": i.category,
              "unit": i.unit, "stock": float(i.current_stock), "reorder": float(i.reorder_level),
              "unit_cost": float(i.unit_cost),
              "low_stock": float(i.current_stock) <= float(i.reorder_level)} for i in items]


@router.post("/")
def create_item(data: ItemCreate, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    count = db.query(InventoryItem).count() + 1
    item = InventoryItem(item_code=f"ITEM-{str(count).zfill(4)}", name=data.name,
                          category=data.category, unit=data.unit,
                          reorder_level=data.reorder_level, unit_cost=data.unit_cost)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "code": item.item_code}


@router.post("/adjust")
def adjust_stock(data: StockAdjust, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    item = db.query(InventoryItem).filter(InventoryItem.id == data.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if data.transaction_type == "In":
        item.current_stock = float(item.current_stock) + data.quantity
    elif data.transaction_type == "Out":
        if float(item.current_stock) < data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        item.current_stock = float(item.current_stock) - data.quantity
    else:
        item.current_stock = data.quantity
    txn = InventoryTransaction(item_id=data.item_id, transaction_type=data.transaction_type,
                                 quantity=data.quantity, balance_after=item.current_stock,
                                 notes=data.notes, created_by=current_user.id)
    db.add(txn)
    db.commit()
    return {"message": "Stock updated", "new_balance": float(item.current_stock)}
