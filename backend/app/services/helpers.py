import random
import string
from datetime import datetime
from sqlalchemy.orm import Session


def generate_batch_id(prefix: str = "SCRAP") -> str:
    ts = datetime.now().strftime("%y%m%d%H%M")
    return f"{prefix}-{ts}-{''.join(random.choices(string.digits, k=3))}"


def generate_dispatch_no() -> str:
    return f"REF-{datetime.now().strftime('%y%m%d%H%M')}"


def generate_job_code(db: Session) -> str:
    from app.models.all_models import Job
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"JEW-{today}-"
    count = db.query(Job).filter(Job.job_code.like(f"{prefix}%")).count()
    seq = str(count + 1).zfill(3)
    job_code = f"{prefix}{seq}"
    while db.query(Job).filter(Job.job_code == job_code).first():
        count += 1
        job_code = f"{prefix}{str(count).zfill(3)}"
    return job_code


def generate_barcode_value(job_code: str, metal_type: str = "", order_qty: int = 1) -> str:
    metal_codes = {"24K":"24","22K":"22","18K":"18","Silver":"SL","Other":"OT"}
    metal_code = metal_codes.get(metal_type, "XX")
    return f"{job_code}-{metal_code}"


def generate_karigar_code(db: Session) -> str:
    from app.models.all_models import Karigar
    count = db.query(Karigar).count()
    code = f"KAR-{str(count + 1).zfill(3)}"
    while db.query(Karigar).filter(Karigar.karigar_code == code).first():
        count += 1
        code = f"KAR-{str(count).zfill(3)}"
    return code


def paginate(query, page: int = 1, per_page: int = 20) -> dict:
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"total": total, "page": page, "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page), "items": items}


def log_activity(db: Session, user_id: int, action: str, module: str,
                 record_id: int = None, old_val=None, new_val=None, ip: str = None):
    try:
        from app.models.all_models import ActivityLog
        log = ActivityLog(user_id=user_id, action=action, module=module,
                          record_id=record_id,
                          old_value=str(old_val) if old_val else None,
                          new_value=str(new_val) if new_val else None,
                          ip_address=ip)
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


def get_setting(db: Session, key: str, default=None):
    try:
        from app.models.all_models import SystemSetting
        s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return s.value if s else default
    except Exception:
        return default


def fmt_weight(value, decimals: int = 4) -> str:
    try:
        return f"{float(value):.{decimals}f}g"
    except (TypeError, ValueError):
        return "0.0000g"