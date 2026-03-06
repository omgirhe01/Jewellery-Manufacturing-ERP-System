from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import os

from app.core.database import engine, get_db
from app.core.config import settings
from app.models.all_models import (
    Base, User, Role
)
from app.api.v1.all_routers import (
    auth_router, jobs_router, scale_router, metal_router,
    karigar_router, scrap_router, refinery_router,
    inventory_router, costing_router, reports_router,
    users_router, customers_router, departments_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Create all database tables on startup
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database tables created/verified")
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"📖 API docs: http://localhost:8000/docs")
    yield
    print("👋 Server shutting down")


app = FastAPI(
    title="Jewellery Manufacturing ERP",
    version="1.0.0",
    description="Complete ERP system for jewellery manufacturing with 12 modules",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS - allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS, images)
if os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
elif os.path.exists("../frontend/static"):
    app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")

# Jinja2 templates for server-rendered HTML pages
# Auto-detect templates directory (works from both /backend and /jewellery-erp root)
import pathlib
_base = pathlib.Path(__file__).parent.parent.parent  # backend/app -> backend -> jewellery-erp
_tmpl = _base / "frontend" / "templates"
if not _tmpl.exists():
    _tmpl = pathlib.Path("frontend/templates")
templates = Jinja2Templates(directory=str(_tmpl))
_static = _base / "frontend" / "static"
if _static.exists() and not os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

# ============================================================
# REGISTER ALL API ROUTERS
# ============================================================
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(scale_router)
app.include_router(metal_router)
app.include_router(karigar_router)
app.include_router(scrap_router)
app.include_router(refinery_router)
app.include_router(inventory_router)
app.include_router(costing_router)
app.include_router(reports_router)
app.include_router(users_router)
app.include_router(customers_router)
app.include_router(departments_router)


# ============================================================
# HELPER: Get current user from cookie (for HTML pages)
# ============================================================
def _get_page_user(request: Request, db: Session = Depends(get_db)):
    """Non-throwing auth check for HTML page routes"""
    from jose import jwt, JWTError
    token = request.cookies.get("session_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if username:
            return db.query(User).filter(User.username == username, User.is_active == True).first()
    except JWTError:
        return None
    return None


# ============================================================
# HTML PAGE ROUTES
# ============================================================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("jobs.html", {"request": request, "user": user})


@app.get("/metal", response_class=HTMLResponse)
def metal_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("metal.html", {"request": request, "user": user})


@app.get("/karigar", response_class=HTMLResponse)
def karigar_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("karigar.html", {"request": request, "user": user})


@app.get("/scrap", response_class=HTMLResponse)
def scrap_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("scrap.html", {"request": request, "user": user})


@app.get("/refinery", response_class=HTMLResponse)
def refinery_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("refinery.html", {"request": request, "user": user})


@app.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("inventory.html", {"request": request, "user": user})


@app.get("/costing", response_class=HTMLResponse)
def costing_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("costing.html", {"request": request, "user": user})


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("reports.html", {"request": request, "user": user})


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("users.html", {"request": request, "user": user})


@app.get("/scale", response_class=HTMLResponse)
def scale_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("scale.html", {"request": request, "user": user})



@app.get("/barcode", response_class=HTMLResponse)
def barcode_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("barcode.html", {"request": request, "user": user})


@app.get("/health")
def health_check():
    """Health check endpoint for Docker/monitoring"""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)