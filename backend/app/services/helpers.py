import random
import string
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

# ============================================================
# ID GENERATORS
# ============================================================

def generate_batch_id(prefix: str = "SCRAP") -> str:
    ts = datetime.now().strftime("%y%m%d%H%M")
    return f"{prefix}-{ts}-{''.join(random.choices(string.digits, k=3))}"

def generate_dispatch_no() -> str:
    return f"REF-{datetime.now().strftime('%y%m%d%H%M')}"

def generate_job_code() -> str:
    """Generates a unique Job Code (e.g., JOB-20260305-A1B2)"""
    date_str = datetime.now().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4().hex[:4]).upper()
    return f"JOB-{date_str}-{unique_id}"

def generate_karigar_code() -> str:
    """Generates a unique Karigar Code (e.g., KRG-832)"""
    return f"KRG-{''.join(random.choices(string.digits, k=3))}"

def generate_barcode_value() -> str:
    """Generates a unique numeric barcode string"""
    return str(int(datetime.now().timestamp()))

# Aliases for different naming conventions
generate_barcode = generate_barcode_value

# ============================================================
# FORMATTING HELPERS
# ============================================================

def fmt_weight(weight: float, precision: int = 3) -> str:
    """Formats weight to specified decimal places (default 3 for gold)"""
    if weight is None: return "0.000"
    return f"{float(weight):.{precision}f}"

def fmt_date(dt: datetime) -> str:
    """Formats datetime to string"""
    if dt is None: return ""
    return dt.strftime("%d-%m-%Y %H:%M")

def format_currency(amount: float) -> str:
    """Formats amount to 2 decimal places"""
    if amount is None: return "0.00"
    return f"{float(amount):.2f}"

# ============================================================
# UTILITY & SETTINGS FUNCTIONS
# ============================================================

def get_setting(db: Session, key: str, default=None):
    """Fetches a value from the SystemSetting table"""
    from app.models.all_models import SystemSetting
    setting = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
    return setting.setting_value if setting else default

def paginate(query, page: int = 1, per_page: int = 20) -> dict:
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "total": total, 
        "page": page, 
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page), 
        "items": items
    }

def log_activity(db: Session, user_id: int, action: str, module: str,
                 record_id: int = None, old_val=None, new_val=None, ip: str = None):
    from app.models.all_models import ActivityLog
    log = ActivityLog(
        user_id=user_id, 
        action=action, 
        module=module,
        record_id=record_id, 
        old_value=old_val, 
        new_value=new_val, 
        ip_address=ip
    )
    db.add(log)
    db.commit()