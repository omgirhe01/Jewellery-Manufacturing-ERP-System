from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user, hash_password, require_roles
from app.models.all_models import User, Role, Customer, Department
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["User Management"])


class UserCreate(BaseModel):
    name: str; email: str; username: str; password: str; role_id: int


class UserUpdate(BaseModel):
    name: Optional[str] = None; email: Optional[str] = None
    role_id: Optional[int] = None; is_active: Optional[bool] = None


@router.get("/")
def list_users(db: Session = Depends(get_db), current_user=Depends(require_roles("Admin"))):
    users = db.query(User).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "username": u.username,
              "role": u.role.name, "is_active": u.is_active} for u in users]


@router.post("/")
def create_user(data: UserCreate, db: Session = Depends(get_db),
                current_user=Depends(require_roles("Admin"))):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username exists")
    user = User(name=data.name, email=data.email, username=data.username,
                password_hash=hash_password(data.password), role_id=data.role_id)
    db.add(user); db.commit(); db.refresh(user)
    return {"id": user.id, "username": user.username}


@router.put("/{user_id}")
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db),
                current_user=Depends(require_roles("Admin"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    if data.name: user.name = data.name
    if data.email: user.email = data.email
    if data.role_id: user.role_id = data.role_id
    if data.is_active is not None: user.is_active = data.is_active
    db.commit()
    return {"message": "Updated"}


@router.get("/roles")
def list_roles(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [{"id": r.id, "name": r.name} for r in db.query(Role).all()]


# Customer endpoints
customers_router = APIRouter(prefix="/customers", tags=["Customers"])


class CustomerCreate(BaseModel):
    name: str; contact: Optional[str] = None; phone: Optional[str] = None
    email: Optional[str] = None; address: Optional[str] = None; gst_no: Optional[str] = None


@customers_router.get("/")
def list_customers(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [{"id": c.id, "name": c.name, "contact": c.contact, "phone": c.phone,
              "email": c.email, "gst_no": c.gst_no} for c in db.query(Customer).filter(Customer.is_active == True).all()]


@customers_router.post("/")
def create_customer(data: CustomerCreate, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    c = Customer(**data.dict()); db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name}


# Departments endpoint
departments_router = APIRouter(prefix="/departments", tags=["Departments"])


@departments_router.get("/")
def list_departments(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.stage_order).all()
    return [{"id": d.id, "name": d.name, "stage_order": d.stage_order,
              "requires_weight": d.requires_weight} for d in depts]
