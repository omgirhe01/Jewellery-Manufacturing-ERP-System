from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings

# Using bcrypt_sha256 to solve '72 bytes' compatibility error with bcrypt 4.1.0+
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# ============================================================
# ROLE PERMISSIONS MAP (from SRS Section 3.12)
# ============================================================
# Admin                - Full access to everything
# Production Manager   - Production, Jobs, Metal, Artisans, Scrap, Refinery, Reports
# Department Operator  - Barcode Scanner, Weighing Scale only
# Metal Store Manager  - Metal Ledger, Scrap, Refinery, Reports (metal)
# Accountant           - Costing, Reports (full), Jobs (read-only)
# QC Officer           - Jobs (QC actions), Barcode, Finished Goods, Reports

ROLE_PERMISSIONS = {
    "Admin": [
        "dashboard", "jobs", "barcode", "scale", "metal", "karigar",
        "scrap", "refinery", "inventory", "costing", "reports",
        "users", "designs", "finished_goods", "customers", "departments"
    ],
    "Production Manager": [
        "dashboard", "jobs", "barcode", "scale", "metal", "karigar",
        "scrap", "refinery", "inventory", "finished_goods", "designs", "reports", "customers"
    ],
    "Department Operator": [
        "dashboard", "barcode", "scale"
    ],
    "Metal Store Manager": [
        "dashboard", "metal", "scrap", "refinery", "reports"
    ],
    "Accountant": [
        "dashboard", "jobs", "costing", "reports", "customers"
    ],
    "QC Officer": [
        "dashboard", "jobs", "barcode", "finished_goods", "reports"
    ],
}


def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt_sha256 wrapper"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create a signed JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session_token: str = Cookie(default=None),
    db: Session = Depends(get_db),
):
    """FastAPI dependency - extracts and validates current user from JWT/Cookie"""
    from app.models.all_models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    raw = token or session_token
    if not raw:
        raise credentials_exception

    try:
        payload = jwt.decode(raw, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(
        User.username == username,
        User.is_active == True
    ).first()

    if not user:
        raise credentials_exception
    return user


def require_roles(*roles: str):
    """Dependency factory - restricts API endpoint to specific roles. Admin always passes."""
    def checker(current_user=Depends(get_current_user)):
        if current_user.role.name != "Admin" and current_user.role.name not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Your role '{current_user.role.name}' is not authorized for this action."
            )
        return current_user
    return checker


def has_page_access(role_name: str, page: str) -> bool:
    """Check if a role has access to a given page/module"""
    allowed = ROLE_PERMISSIONS.get(role_name, [])
    return page in allowed


def get_user_permissions(role_name: str) -> list:
    """Return list of permitted pages for a role"""
    return ROLE_PERMISSIONS.get(role_name, [])
