from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import os
import pathlib

from app.core.database import engine, get_db
from app.core.config import settings
from app.core.security import has_page_access, get_user_permissions
from app.models.all_models import Base, User, Role
from app.api.v1.all_routers import (
    auth_router, jobs_router, scale_router, metal_router,
    karigar_router, scrap_router, refinery_router,
    inventory_router, costing_router, reports_router,
    users_router, customers_router, departments_router,
    finished_goods_router, designs_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database tables created/verified")

    # ── Seed roles & default admin ──────────────────────────────────────────
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    db = SessionLocal()
    try:
        ROLES = [
            "Admin",
            "Production Manager",
            "Department Operator",
            "Metal Store Manager",
            "Accountant",
            "QC Officer",
        ]
        role_map = {}
        for rname in ROLES:
            r = db.query(Role).filter(Role.name == rname).first()
            if not r:
                r = Role(name=rname)
                db.add(r)
                db.flush()
                print(f"  ➕ Role created: {rname}")
            role_map[rname] = r

        db.commit()

        # Create default admin if no users exist
        if db.query(User).count() == 0:
            admin_role = db.query(Role).filter(Role.name == "Admin").first()
            admin = User(
                name="Administrator",
                username="admin",
                email="admin@sonajewels.com",
                password_hash=hash_password("admin123"),
                role_id=admin_role.id,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("  👤 Default admin created — username: admin / password: admin123")
        else:
            print(f"  ✅ {db.query(Role).count()} roles ready, {db.query(User).count()} users found")
    except Exception as e:
        db.rollback()
        print(f"  ⚠ Seed error: {e}")
    finally:
        db.close()
    # ────────────────────────────────────────────────────────────────────────

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

from fastapi import status as http_status
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure all unhandled exceptions return JSON, never HTML"""
    print(f"❌ Unhandled error on {request.url}: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server error: {str(exc)}"}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# STATIC FILES & TEMPLATES — Single clean mount (BUG FIX)
# ============================================================
_base = pathlib.Path(__file__).parent.parent.parent  # → project root
_static_dir = _base / "frontend" / "static"
_tmpl_dir   = _base / "frontend" / "templates"

# Fallback: if running from project root directly (e.g. uvicorn main:app)
if not _static_dir.exists():
    _static_dir = pathlib.Path("frontend/static")
if not _tmpl_dir.exists():
    _tmpl_dir = pathlib.Path("frontend/templates")

# Mount static ONCE only
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
else:
    print("⚠️  WARNING: frontend/static directory not found!")

templates = Jinja2Templates(directory=str(_tmpl_dir))

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
app.include_router(finished_goods_router)
app.include_router(costing_router)
app.include_router(reports_router)
app.include_router(users_router)
app.include_router(customers_router)
app.include_router(departments_router)
app.include_router(designs_router)


# ============================================================
# HELPER: Get current user from cookie (for HTML page routes)
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


def _render_or_deny(request, templates, template_name, user, page_key, extra_ctx=None):
    """Render page if user has access, else return 403 page"""
    if not has_page_access(user.role.name, page_key):
        ctx = {
            "request": request,
            "user": user,
            "denied_page": page_key,
            "user_permissions": get_user_permissions(user.role.name)
        }
        return templates.TemplateResponse("403.html", ctx, status_code=403)
    ctx = {"request": request, "user": user, "active_page": page_key,
           "user_permissions": get_user_permissions(user.role.name)}
    if extra_ctx:
        ctx.update(extra_ctx)
    return templates.TemplateResponse(template_name, ctx)


# ============================================================
# HTML PAGE ROUTES — All with role-based access control
# ============================================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "dashboard.html", user, "dashboard")


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "jobs.html", user, "jobs")


@app.get("/metal", response_class=HTMLResponse)
def metal_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "metal.html", user, "metal")


@app.get("/karigar", response_class=HTMLResponse)
def karigar_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "karigar.html", user, "karigar")


@app.get("/scrap", response_class=HTMLResponse)
def scrap_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "scrap.html", user, "scrap")


@app.get("/refinery", response_class=HTMLResponse)
def refinery_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "refinery.html", user, "refinery")


@app.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "inventory.html", user, "inventory")


@app.get("/costing", response_class=HTMLResponse)
def costing_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "costing.html", user, "costing")


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "reports.html", user, "reports")


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "users.html", user, "users")


@app.get("/scale", response_class=HTMLResponse)
def scale_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "scale.html", user, "scale")


@app.get("/barcode", response_class=HTMLResponse)
def barcode_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "barcode.html", user, "barcode")


@app.get("/finished-goods", response_class=HTMLResponse)
def finished_goods_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "finished_goods.html", user, "finished_goods")


@app.get("/designs", response_class=HTMLResponse)
def designs_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "designs.html", user, "designs")


@app.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "customers.html", user, "customers")


@app.get("/departments", response_class=HTMLResponse)
def departments_page(request: Request, db: Session = Depends(get_db)):
    user = _get_page_user(request, db)
    if not user:
        return RedirectResponse("/login")
    return _render_or_deny(request, templates, "departments.html", user, "departments")


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)