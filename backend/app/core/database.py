from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # Test connection before using from pool
    pool_recycle=3600,        # Recycle connections every hour
    pool_size=10,             # Keep 10 connections in pool
    max_overflow=20,          # Allow 20 overflow connections
    echo=settings.DEBUG       # Log SQL in debug mode
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency - provides database session per request"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
