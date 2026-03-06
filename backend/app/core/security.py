from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings

# UPDATED: Using bcrypt_sha256 to solve '72 bytes' compatibility error with bcrypt 4.1.0+
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt_sha256 wrapper"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create a signed JWT access token"""
    to_encode = data.copy()
    # UTC time is used for consistency
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    # Using 'sub' is standard for the subject (usually username or user_id)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    session_token: str = Cookie(default=None),
    db: Session = Depends(get_db),
):
    """FastAPI dependency - extracts and validates current user from JWT/Cookie"""
    # Import inside function to avoid circular import issues
    from app.models.all_models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Token check from header or cookie
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

    # User lookup with error handling
    user = db.query(User).filter(
        User.username == username, 
        User.is_active == True
    ).first()
    
    if not user:
        raise credentials_exception
    return user

def require_roles(*roles: str):
    """Factory for role-based access control (RBAC)"""
    def checker(current_user=Depends(get_current_user)):
        # Admin bypass and role verification
        if current_user.role.name not in roles and current_user.role.name != "Admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(roles)}"
            )
        return current_user
    return checker