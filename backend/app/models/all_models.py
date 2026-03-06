from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    Text, Enum, Date, JSON, ForeignKey, DECIMAL, SmallInteger
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum

# ============================================================
# ENUMS
# ============================================================
class JobStageEnum(enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

# ============================================================
# SYSTEM & AUTH MODELS
# ============================================================
class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    permissions = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    role = relationship("Role", back_populates="users")

class JobStage(Base):
    __tablename__ = "job_stages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False)
    action = Column(String(100), nullable=False)
    module = Column(String(50), nullable=False)
    record_id = Column(BigInteger)
    old_value = Column(JSON)
    new_value = Column(JSON)
    ip_address = Column(String(45))
    created_at = Column(DateTime, server_default=func.now())

# ============================================================
# CUSTOMER & DESIGN MODELS
# ============================================================
class Customer(Base):
    __tablename__ = "customers"
    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    contact_person = Column(String(100))
    phone = Column(String(20))
    email = Column(String(100))
    address = Column(Text)
    gst_number = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    jobs = relationship("Job", back_populates="customer")

class Design(Base):
    __tablename__ = "designs"
    id = Column(BigInteger, primary_key=True, index=True)
    design_code = Column(String(50), unique=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    image_path = Column(String(255))
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())

# ============================================================
# JOB MODEL
# ============================================================
class Job(Base):
    __tablename__ = "jobs"
    id = Column(BigInteger, primary_key=True, index=True)
    job_code = Column(String(25), unique=True, nullable=False)
    barcode = Column(String(120), unique=True, nullable=False)
    barcode_image_b64 = Column(Text)
    design_id = Column(BigInteger, ForeignKey("designs.id"))
    design_name = Column(String(100))
    customer_id = Column(BigInteger, ForeignKey("customers.id"), nullable=False)
    metal_type = Column(Enum("24K", "22K", "18K", "Silver", "Other"), nullable=False)
    target_weight = Column(DECIMAL(10, 3), nullable=False)
    current_weight = Column(DECIMAL(10, 3), default=0.000)
    wastage_allowed = Column(DECIMAL(5, 2), default=2.50)
    order_qty = Column(Integer, default=1)
    current_stage = Column(
        Enum("Design","Wax","CAM","Casting","Filing","Pre-polish",
             "Stone Setting","Polishing","Quality Control","Finished Goods","Dispatch"),
        default="Design"
    )
    status = Column(
        Enum("New","Active","QC Pending","QC Rejected","Completed","Dispatched","On Hold","Cancelled"),
        default="New"
    )
    priority = Column(Enum("Normal", "High", "Urgent"), default="Normal")
    expected_delivery = Column(Date)
    notes = Column(Text)
    created_by = Column(BigInteger)
    updated_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer", back_populates="jobs")
    stage_logs = relationship("JobStageLog", back_populates="job", cascade="all, delete-orphan")
    weight_logs = relationship("WeightLog", back_populates="job", cascade="all, delete-orphan")
    cost = relationship("JobCost", back_populates="job", uselist=False)

# ============================================================
# PRODUCTION MODELS
# ============================================================
class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    stage_order = Column(Integer, nullable=False)
    requires_weight = Column(Boolean, default=True)
    requires_approval = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

class JobStageLog(Base):
    __tablename__ = "job_stage_logs"
    id = Column(BigInteger, primary_key=True, index=True)
    job_id = Column(BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    stage_name = Column(String(50), nullable=False)
    karigar_id = Column(BigInteger, ForeignKey("karigars.id"))
    operator_id = Column(BigInteger)
    weight_in = Column(DECIMAL(10, 4))
    weight_out = Column(DECIMAL(10, 4))
    weight_variance = Column(DECIMAL(10, 4))
    variance_pct = Column(DECIMAL(6, 3))
    status = Column(
        Enum("Pending", "In Progress", "Completed", "Rejected", "Skipped"),
        default="Pending"
    )
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    approved_by = Column(BigInteger)
    approved_at = Column(DateTime)
    rejection_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    job = relationship("Job", back_populates="stage_logs")
    karigar = relationship("Karigar", back_populates="stage_logs")

class BarcodeScan(Base):
    __tablename__ = "barcode_scans"
    id = Column(BigInteger, primary_key=True, index=True)
    barcode = Column(String(120), nullable=False)
    job_id = Column(BigInteger, ForeignKey("jobs.id"))
    scanned_by = Column(BigInteger)
    department_id = Column(Integer)
    scan_type = Column(Enum("Check-In","Check-Out","QC","Dispatch","Inventory"), default="Check-In")
    scan_source = Column(Enum("USB Scanner","Webcam","Manual"), default="USB Scanner")
    scanned_at = Column(DateTime, server_default=func.now())

BarcodeScans = BarcodeScan

class WeightLog(Base):
    __tablename__ = "weight_logs"
    id = Column(BigInteger, primary_key=True, index=True)
    job_id = Column(BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    stage_log_id = Column(BigInteger, ForeignKey("job_stage_logs.id"))
    department_id = Column(Integer)
    gross_weight = Column(DECIMAL(10, 4), nullable=False)
    tare_weight = Column(DECIMAL(10, 4), default=0.0000)
    net_weight = Column(DECIMAL(10, 4), nullable=False)
    scale_id = Column(Integer)
    scale_type = Column(Enum("USB","RS232","Simulation","Manual"), default="Simulation")
    is_manual_override = Column(Boolean, default=False)
    operator_id = Column(BigInteger)
    captured_at = Column(DateTime, server_default=func.now())
    job = relationship("Job", back_populates="weight_logs")

# ============================================================
# KARIGAR MODELS
# ============================================================
class Karigar(Base):
    __tablename__ = "karigars"
    id = Column(BigInteger, primary_key=True, index=True)
    karigar_code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    address = Column(Text)
    skill_type = Column(String(50))
    experience_years = Column(Integer, default=0)
    piece_rate = Column(DECIMAL(10, 2), default=0.00)
    daily_rate = Column(DECIMAL(10, 2), default=0.00)
    is_active = Column(Boolean, default=True)
    joined_date = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
    assignments = relationship("KarigarAssignment", back_populates="karigar")
    stage_logs = relationship("JobStageLog", back_populates="karigar")

class KarigarAssignment(Base):
    __tablename__ = "karigar_assignments"
    id = Column(BigInteger, primary_key=True, index=True)
    karigar_id = Column(BigInteger, ForeignKey("karigars.id"), nullable=False)
    job_id = Column(BigInteger, ForeignKey("jobs.id"), nullable=False)
    stage_log_id = Column(BigInteger, ForeignKey("job_stage_logs.id"))
    pieces_assigned = Column(Integer, default=0)
    pieces_completed = Column(Integer, default=0)
    metal_issued = Column(DECIMAL(10, 4), default=0.0000)
    metal_returned = Column(DECIMAL(10, 4), default=0.0000)
    labour_cost = Column(DECIMAL(12, 2), default=0.00)
    status = Column(Enum("Assigned","In Progress","Completed","Partial"), default="Assigned")
    assigned_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)
    karigar = relationship("Karigar", back_populates="assignments")

# ============================================================
# METAL & SCRAP MODELS
# ============================================================
class MetalStock(Base):
    __tablename__ = "metal_stock"
    id = Column(Integer, primary_key=True, index=True)
    metal_type = Column(Enum("24K","22K","18K","Silver","Alloy","Scrap"), nullable=False)
    stock_type = Column(Enum("Pure","Alloy","Scrap","Refinery Pending","WIP"), nullable=False)
    quantity = Column(DECIMAL(14, 4), default=0.0000)
    purity_pct = Column(DECIMAL(6, 3), default=99.900)
    last_rate = Column(DECIMAL(10, 2), default=0.00)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class MetalLedger(Base):
    __tablename__ = "metal_ledger"
    id = Column(BigInteger, primary_key=True, index=True)
    transaction_type = Column(
        Enum("Issue","Return","Adjustment","Refinery Out","Refinery In","Opening"),
        nullable=False
    )
    metal_type = Column(Enum("24K","22K","18K","Silver","Alloy","Scrap"), nullable=False)
    weight = Column(DECIMAL(12, 4), nullable=False)
    purity_pct = Column(DECIMAL(6, 3))
    fine_weight = Column(DECIMAL(12, 4))
    issue_rate = Column(DECIMAL(10, 2))
    total_value = Column(DECIMAL(16, 2))
    balance_after = Column(DECIMAL(14, 4))
    issued_to_type = Column(Enum("Department","Karigar"))
    issued_to_id = Column(BigInteger)
    issued_to_name = Column(String(100))
    job_id = Column(BigInteger, ForeignKey("jobs.id", ondelete="SET NULL"))
    reference_no = Column(String(60))
    notes = Column(Text)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())

class ScrapEntry(Base):
    __tablename__ = "scrap_entries"
    id = Column(BigInteger, primary_key=True, index=True)
    batch_id = Column(String(35), unique=True, nullable=False)
    source_department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    scrap_type = Column(
        Enum("Filing","Casting","Polishing Dust","Broken Pieces","Wax","Other"),
        nullable=False
    )
    gross_weight = Column(DECIMAL(10, 4), nullable=False)
    estimated_purity = Column(DECIMAL(6, 3))
    estimated_fine_weight = Column(DECIMAL(10, 4))
    status = Column(
        Enum("Collected","In Stock","Sent to Refinery","Settled"),
        default="Collected"
    )
    collected_by = Column(BigInteger)
    collected_at = Column(DateTime, server_default=func.now())
    notes = Column(Text)

class RefineryDispatch(Base):
    __tablename__ = "refinery_dispatches"
    id = Column(BigInteger, primary_key=True, index=True)
    dispatch_no = Column(String(35), unique=True, nullable=False)
    refinery_name = Column(String(100), nullable=False)
    dispatch_date = Column(Date, nullable=False)
    total_gross_weight = Column(DECIMAL(14, 4), nullable=False)
    estimated_purity = Column(DECIMAL(6, 3))
    expected_fine_gold = Column(DECIMAL(14, 4))
    status = Column(
        Enum("Dispatched","Partial Settlement","Settled"),
        default="Dispatched"
    )
    notes = Column(Text)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    settlement = relationship("RefinerySettlement", back_populates="dispatch", uselist=False)

class RefinerySettlement(Base):
    __tablename__ = "refinery_settlements"
    id = Column(BigInteger, primary_key=True, index=True)
    dispatch_id = Column(BigInteger, ForeignKey("refinery_dispatches.id"), unique=True, nullable=False)
    settlement_date = Column(Date, nullable=False)
    fine_gold_received = Column(DECIMAL(14, 4), nullable=False)
    recovery_pct = Column(DECIMAL(6, 3))
    refining_charges = Column(DECIMAL(12, 2), default=0.00)
    variance_pct = Column(DECIMAL(6, 3))
    payment_status = Column(Enum("Pending","Paid","Adjusted"), default="Pending")
    notes = Column(Text)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    dispatch = relationship("RefineryDispatch", back_populates="settlement")

# ============================================================
# INVENTORY & COSTING MODELS
# ============================================================
class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(BigInteger, primary_key=True, index=True)
    item_code = Column(String(30), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(
        Enum("Gold","Silver","Diamond","Gemstone","Consumable","Packaging","WIP","Finished Good"),
        nullable=False
    )
    unit = Column(String(20), nullable=False)
    current_stock = Column(DECIMAL(14, 4), default=0.0000)
    reorder_level = Column(DECIMAL(14, 4), default=0.0000)
    unit_cost = Column(DECIMAL(12, 2), default=0.00)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    transactions = relationship("InventoryTransaction", back_populates="item")

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id = Column(BigInteger, primary_key=True, index=True)
    item_id = Column(BigInteger, ForeignKey("inventory_items.id"), nullable=False)
    transaction_type = Column(Enum("Purchase","Issue","Return","Adjust","Scrap"), nullable=False)
    quantity = Column(DECIMAL(14, 4), nullable=False)
    unit_cost = Column(DECIMAL(12, 2))
    total_cost = Column(DECIMAL(16, 2))
    balance_after = Column(DECIMAL(14, 4), nullable=False)
    reference_type = Column(String(50))
    reference_id = Column(BigInteger)
    notes = Column(Text)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    item = relationship("InventoryItem", back_populates="transactions")

class FinishedGood(Base):
    __tablename__ = "finished_goods"
    id = Column(BigInteger, primary_key=True, index=True)
    job_id = Column(BigInteger, ForeignKey("jobs.id"), unique=True, nullable=False)
    item_code = Column(String(30))
    final_weight = Column(DECIMAL(10, 4))
    pieces_count = Column(Integer, default=1)
    hallmark_no = Column(String(50))
    qc_passed = Column(Boolean, default=False)
    qc_officer_id = Column(BigInteger)
    qc_date = Column(DateTime)
    qc_notes = Column(Text)
    dispatch_date = Column(DateTime)
    dispatch_ref = Column(String(60))
    status = Column(Enum("Ready","Dispatched","On Hold","Returned"), default="Ready")

class JobCost(Base):
    __tablename__ = "job_costs"
    id = Column(BigInteger, primary_key=True, index=True)
    job_id = Column(BigInteger, ForeignKey("jobs.id"), unique=True, nullable=False)
    gold_weight_used = Column(DECIMAL(10, 4), default=0.0000)
    gold_rate = Column(DECIMAL(10, 2), default=0.00)
    gold_cost = Column(DECIMAL(14, 2), default=0.00)
    labour_cost = Column(DECIMAL(14, 2), default=0.00)
    stone_cost = Column(DECIMAL(14, 2), default=0.00)
    wastage_cost = Column(DECIMAL(14, 2), default=0.00)
    refinery_adjustment = Column(DECIMAL(14, 2), default=0.00)
    overhead_cost = Column(DECIMAL(14, 2), default=0.00)
    total_cost = Column(DECIMAL(14, 2), default=0.00)
    sale_price = Column(DECIMAL(14, 2), default=0.00)
    profit_loss = Column(DECIMAL(14, 2), default=0.00)
    margin_pct = Column(DECIMAL(6, 2), default=0.00)
    calculated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    job = relationship("Job", back_populates="cost")

# ============================================================
# SYSTEM MODELS
# ============================================================
class ScaleDevice(Base):
    __tablename__ = "scale_devices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60), nullable=False)
    port = Column(String(30))
    baudrate = Column(Integer, default=9600)
    device_type = Column(Enum("USB","RS232","Simulation"), default="Simulation")
    is_active = Column(Boolean, default=True)
    last_reading = Column(DECIMAL(10, 4))
    last_read_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(Text)
    setting_type = Column(String(20), default="string")
    description = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(Enum("info","warning","error","success"), default="info")
    is_read = Column(Boolean, default=False)
    related_module = Column(String(50))
    related_id = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())