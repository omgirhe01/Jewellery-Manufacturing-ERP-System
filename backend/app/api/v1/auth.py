from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, hash_password, get_current_user
from app.models.all_models import User, Role
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    username: str
    password: str
    role_id: int = 3


@router.post("/login")
def login(response: Response, data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username, User.is_active == True).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": user.username, "role": user.role.name})
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400, samesite="lax")
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "name": user.name, "role": user.role.name, "username": user.username}}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name,
            "username": current_user.username, "email": current_user.email,
            "role": current_user.role.name}


@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(name=data.name, email=data.email, username=data.username,
                password_hash=hash_password(data.password), role_id=data.role_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "message": "User created successfully"}
