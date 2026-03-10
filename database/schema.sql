-- ============================================================
-- JEWELLERY MANUFACTURING ERP - Complete MySQL Schema
-- Version 2.0 | Fully synced with all_models.py
-- MySQL 8.0+ | InnoDB | ACID Compliant
-- ============================================================

CREATE DATABASE IF NOT EXISTS jewellery_erp
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE jewellery_erp;

SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- TABLE 1: ROLES
-- ============================================================
CREATE TABLE roles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    permissions JSON,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 2: USERS
-- ============================================================
CREATE TABLE users (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(100) NOT NULL UNIQUE,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id       INT NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    last_login    DATETIME NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    INDEX idx_username (username)
);

-- ============================================================
-- TABLE 3: ACTIVITY LOGS
-- ============================================================
CREATE TABLE activity_logs (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    action     VARCHAR(100) NOT NULL,
    module     VARCHAR(50)  NOT NULL,
    record_id  BIGINT,
    old_value  JSON,
    new_value  JSON,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_module_user (module, user_id),
    INDEX idx_created     (created_at)
);

-- ============================================================
-- TABLE 4: CUSTOMERS
-- ============================================================
CREATE TABLE customers (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    contact_person VARCHAR(100),          -- model: contact_person
    phone          VARCHAR(20),
    email          VARCHAR(100),
    address        TEXT,
    gst_number     VARCHAR(20),           -- model: gst_number
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 5: DEPARTMENTS (Production Stages)
-- ============================================================
CREATE TABLE departments (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(50) NOT NULL UNIQUE,
    stage_order       INT NOT NULL,
    requires_weight   BOOLEAN DEFAULT TRUE,
    requires_approval BOOLEAN DEFAULT FALSE,
    is_active         BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- TABLE 6: DESIGNS
-- ============================================================
CREATE TABLE designs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    design_code VARCHAR(50) UNIQUE,
    description TEXT,
    image_path  VARCHAR(255),
    created_by  BIGINT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 7: JOBS (Core Business Table)
-- ============================================================
CREATE TABLE jobs (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_code          VARCHAR(25)   NOT NULL UNIQUE,
    barcode           VARCHAR(120)  UNIQUE,
    barcode_image_b64 MEDIUMTEXT,
    design_id         BIGINT,
    design_name       VARCHAR(100),
    customer_id       BIGINT NOT NULL,
    metal_type        ENUM('24K','22K','18K','Silver','Other') NOT NULL,
    target_weight     DECIMAL(10,3) NOT NULL,
    current_weight    DECIMAL(10,3) DEFAULT 0.000,
    wastage_allowed   DECIMAL(5,2)  DEFAULT 2.50,
    order_qty         INT DEFAULT 1,
    current_stage     ENUM('Design','Wax','CAM','Casting','Filing',
                          'Pre-polish','Stone Setting','Polishing',
                          'QC','Finished Goods','Dispatch') DEFAULT 'Design',
    status            ENUM('New','Active','QC Pending','QC Rejected',
                          'Completed','Dispatched','On Hold','Cancelled') DEFAULT 'New',
    priority          ENUM('Normal','High','Urgent') DEFAULT 'Normal',
    expected_delivery DATE,
    notes             TEXT,
    created_by        BIGINT,
    updated_by        BIGINT,               -- model: updated_by (was missing)
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (design_id)   REFERENCES designs(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX idx_job_code        (job_code),
    INDEX idx_status_stage    (status, current_stage),
    INDEX idx_customer        (customer_id),
    INDEX idx_created         (created_at)
);

-- ============================================================
-- TABLE 8: JOB STAGES (JobStage model - stage definitions)
-- ============================================================
CREATE TABLE job_stages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255)
);

-- ============================================================
-- TABLE 9: JOB STAGE LOGS (JobStageLog model - execution logs)
-- ============================================================
CREATE TABLE job_stage_logs (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id           BIGINT NOT NULL,
    department_id    INT    NOT NULL,
    stage_name       VARCHAR(50) NOT NULL,
    karigar_id       BIGINT,
    operator_id      BIGINT,
    weight_in        DECIMAL(10,4),
    weight_out       DECIMAL(10,4),
    weight_variance  DECIMAL(10,4),
    variance_pct     DECIMAL(6,3),
    status           ENUM('Pending','In Progress','Completed','Rejected','Skipped') DEFAULT 'Pending',
    started_at       DATETIME NULL,
    completed_at     DATETIME NULL,
    approved_by      BIGINT,
    approved_at      DATETIME,
    rejection_reason TEXT,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)        REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments(id),
    INDEX idx_job_stage (job_id, stage_name)
);

-- ============================================================
-- TABLE 10: BARCODE SCANS
-- ============================================================
CREATE TABLE barcode_scans (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    barcode     VARCHAR(120) NOT NULL,
    job_id      BIGINT,
    scanned_by  BIGINT,
    scan_result VARCHAR(50),
    location    VARCHAR(100),
    scanned_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    INDEX idx_barcode    (barcode),
    INDEX idx_scanned_at (scanned_at)
);

-- ============================================================
-- TABLE 11: WEIGHT LOGS
-- ============================================================
CREATE TABLE weight_logs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id      BIGINT NOT NULL,
    stage       VARCHAR(50),
    weight      DECIMAL(10,4) NOT NULL,
    unit        VARCHAR(10) DEFAULT 'g',
    recorded_by BIGINT,
    device_id   INT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    INDEX idx_job_weight (job_id)
);

-- ============================================================
-- TABLE 12: METAL STOCK
-- ============================================================
CREATE TABLE metal_stock (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    metal_type ENUM('24K','22K','18K','Silver','Alloy','Scrap') NOT NULL,
    stock_type ENUM('Pure','Alloy','Scrap','Refinery Pending','WIP') NOT NULL,  -- added WIP
    quantity   DECIMAL(14,4) NOT NULL DEFAULT 0.0000,
    purity_pct DECIMAL(6,3)  DEFAULT 99.900,   -- model: purity_pct (was 'purity')
    last_rate  DECIMAL(10,2) DEFAULT 0.00,      -- model: last_rate (new)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_metal_stock (metal_type, stock_type)
);

-- ============================================================
-- TABLE 13: METAL LEDGER
-- ============================================================
CREATE TABLE metal_ledger (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_type ENUM('Issue','Return','Adjustment','Refinery Out','Refinery In','Opening') NOT NULL,  -- added Opening
    metal_type       ENUM('24K','22K','18K','Silver','Alloy','Scrap') NOT NULL,
    weight           DECIMAL(12,4) NOT NULL,
    purity_pct       DECIMAL(6,3),
    fine_weight      DECIMAL(12,4),
    issue_rate       DECIMAL(10,2),
    total_value      DECIMAL(16,2),
    balance_after    DECIMAL(14,4),
    issued_to_type   ENUM('Department','Karigar'),
    issued_to_id     BIGINT,
    issued_to_name   VARCHAR(100),
    job_id           BIGINT,
    reference_no     VARCHAR(60),
    notes            TEXT,
    created_by       BIGINT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    INDEX idx_metal_type     (metal_type),
    INDEX idx_trans_type     (transaction_type),
    INDEX idx_created        (created_at)
);

-- ============================================================
-- TABLE 14: KARIGARS (Artisans)
-- ============================================================
CREATE TABLE karigars (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    karigar_code     VARCHAR(20) NOT NULL UNIQUE,
    name             VARCHAR(100) NOT NULL,
    phone            VARCHAR(20),
    address          TEXT,
    skill_type       VARCHAR(50),
    experience_years INT DEFAULT 0,           -- model: experience_years (was missing)
    piece_rate       DECIMAL(10,2) DEFAULT 0.00,
    daily_rate       DECIMAL(10,2) DEFAULT 0.00,  -- model: daily_rate (was missing)
    is_active        BOOLEAN DEFAULT TRUE,
    joined_date      DATE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_karigar_code (karigar_code)
);

-- ============================================================
-- TABLE 15: KARIGAR ASSIGNMENTS
-- ============================================================
CREATE TABLE karigar_assignments (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    karigar_id       BIGINT NOT NULL,
    job_id           BIGINT NOT NULL,
    job_stage_id     BIGINT,
    pieces_assigned  INT DEFAULT 0,
    pieces_completed INT DEFAULT 0,
    metal_issued     DECIMAL(10,4) DEFAULT 0.0000,
    metal_returned   DECIMAL(10,4) DEFAULT 0.0000,
    labour_cost      DECIMAL(10,2) DEFAULT 0.00,
    status           ENUM('Assigned','In Progress','Completed','Partial') DEFAULT 'Assigned',
    assigned_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMP NULL,
    FOREIGN KEY (karigar_id)   REFERENCES karigars(id),
    FOREIGN KEY (job_id)       REFERENCES jobs(id),
    FOREIGN KEY (job_stage_id) REFERENCES job_stage_logs(id),
    INDEX idx_karigar_job (karigar_id, job_id)
);

-- ============================================================
-- TABLE 16: SCRAP ENTRIES
-- ============================================================
CREATE TABLE scrap_entries (
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id              VARCHAR(35) NOT NULL UNIQUE,
    source_department_id  INT NOT NULL,
    scrap_type            ENUM('Filing','Casting','Polishing Dust','Broken Pieces','Wax','Other') NOT NULL,
    gross_weight          DECIMAL(10,4) NOT NULL,
    estimated_purity      DECIMAL(6,3),
    estimated_fine_weight DECIMAL(10,4),
    status                ENUM('Collected','In Stock','Sent to Refinery','Settled') DEFAULT 'Collected',
    notes                 TEXT,
    collected_by          BIGINT,
    collected_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_department_id) REFERENCES departments(id),
    INDEX idx_batch_id (batch_id),
    INDEX idx_status   (status)
);

-- ============================================================
-- TABLE 17: REFINERY DISPATCHES
-- ============================================================
CREATE TABLE refinery_dispatches (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    dispatch_no       VARCHAR(30) NOT NULL UNIQUE,
    refinery_name     VARCHAR(100) NOT NULL,
    dispatch_date     DATE NOT NULL,
    total_gross_weight DECIMAL(12,4),
    expected_purity   DECIMAL(6,3),
    expected_fine_gold DECIMAL(12,4),
    status            ENUM('Dispatched','Received','Settled') DEFAULT 'Dispatched',
    notes             TEXT,
    dispatched_by     BIGINT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dispatch_no   (dispatch_no),
    INDEX idx_dispatch_date (dispatch_date)
);

-- ============================================================
-- TABLE 18: REFINERY SETTLEMENTS
-- ============================================================
CREATE TABLE refinery_settlements (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    dispatch_id      BIGINT NOT NULL UNIQUE,
    settlement_date  DATE NOT NULL,
    fine_gold_received DECIMAL(12,4),
    refining_charges DECIMAL(12,2),
    recovery_pct     DECIMAL(6,3),
    variance_pct     DECIMAL(6,3),
    payment_status   ENUM('Pending','Paid','Partial') DEFAULT 'Pending',
    notes            TEXT,
    settled_by       BIGINT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dispatch_id) REFERENCES refinery_dispatches(id),
    INDEX idx_dispatch (dispatch_id)
);

-- ============================================================
-- TABLE 19: REFINERY DISPATCH BATCHES (scrap batches per dispatch)
-- ============================================================
CREATE TABLE refinery_dispatch_batches (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    dispatch_id BIGINT NOT NULL,
    scrap_id    BIGINT NOT NULL,
    weight      DECIMAL(10,4) NOT NULL,
    FOREIGN KEY (dispatch_id) REFERENCES refinery_dispatches(id),
    FOREIGN KEY (scrap_id)    REFERENCES scrap_entries(id)
);

-- ============================================================
-- TABLE 20: INVENTORY ITEMS
-- ============================================================
CREATE TABLE inventory_items (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_code     VARCHAR(30) NOT NULL UNIQUE,
    name          VARCHAR(100) NOT NULL,
    category      ENUM('Gold','Silver','Stone','Consumable','Other') NOT NULL,
    unit          VARCHAR(20) NOT NULL,
    current_stock DECIMAL(14,4) DEFAULT 0.0000,
    reorder_level DECIMAL(14,4) DEFAULT 0.0000,
    unit_cost     DECIMAL(12,2) DEFAULT 0.00,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_item_code (item_code),
    INDEX idx_category  (category)
);

-- ============================================================
-- TABLE 21: INVENTORY TRANSACTIONS
-- ============================================================
CREATE TABLE inventory_transactions (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_id          BIGINT NOT NULL,
    transaction_type ENUM('Purchase','Issue','Return','Adjust','Scrap') NOT NULL,
    quantity         DECIMAL(14,4) NOT NULL,
    unit_cost        DECIMAL(12,2),
    total_cost       DECIMAL(16,2),
    balance_after    DECIMAL(14,4) NOT NULL,
    reference_type   VARCHAR(50),
    reference_id     BIGINT,
    notes            TEXT,
    created_by       BIGINT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES inventory_items(id),
    INDEX idx_item_trans (item_id, transaction_type),
    INDEX idx_created    (created_at)
);

-- ============================================================
-- TABLE 22: FINISHED GOODS
-- ============================================================
CREATE TABLE finished_goods (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id        BIGINT NOT NULL UNIQUE,
    item_code     VARCHAR(30),
    final_weight  DECIMAL(10,4),
    pieces_count  INT DEFAULT 1,
    hallmark_no   VARCHAR(50),
    qc_passed     BOOLEAN DEFAULT FALSE,
    qc_officer_id BIGINT,
    qc_date       DATETIME,
    qc_notes      TEXT,
    dispatch_date DATETIME,
    dispatch_ref  VARCHAR(60),
    status        ENUM('Ready','Dispatched','On Hold','Returned') DEFAULT 'Ready',
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    INDEX idx_job    (job_id),
    INDEX idx_status (status)
);

-- ============================================================
-- TABLE 23: JOB COSTS
-- ============================================================
CREATE TABLE job_costs (
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id                BIGINT NOT NULL UNIQUE,
    gold_weight_used      DECIMAL(10,4) DEFAULT 0.0000,
    gold_rate             DECIMAL(10,2) DEFAULT 0.00,
    gold_cost             DECIMAL(14,2) DEFAULT 0.00,
    labour_cost           DECIMAL(14,2) DEFAULT 0.00,
    stone_cost            DECIMAL(14,2) DEFAULT 0.00,
    wastage_cost          DECIMAL(14,2) DEFAULT 0.00,
    refinery_adjustment   DECIMAL(14,2) DEFAULT 0.00,
    overhead_cost         DECIMAL(14,2) DEFAULT 0.00,
    total_cost            DECIMAL(14,2) DEFAULT 0.00,
    sale_price            DECIMAL(14,2) DEFAULT 0.00,
    profit_loss           DECIMAL(14,2) DEFAULT 0.00,
    margin_pct            DECIMAL(6,2)  DEFAULT 0.00,
    calculated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    INDEX idx_job (job_id)
);

-- ============================================================
-- TABLE 24: SCALE DEVICES
-- ============================================================
CREATE TABLE scale_devices (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(60) NOT NULL,
    port         VARCHAR(30),
    baudrate     INT DEFAULT 9600,
    device_type  ENUM('USB','RS232','Simulation') DEFAULT 'Simulation',
    is_active    BOOLEAN DEFAULT TRUE,
    last_reading DECIMAL(10,4),
    last_read_at DATETIME,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 25: SYSTEM SETTINGS
-- ============================================================
CREATE TABLE system_settings (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    setting_key   VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT,
    setting_type  VARCHAR(20) DEFAULT 'string',
    description   TEXT,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 26: NOTIFICATIONS
-- ============================================================
CREATE TABLE notifications (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT,
    title          VARCHAR(200) NOT NULL,
    message        TEXT NOT NULL,
    type           ENUM('info','warning','error','success') DEFAULT 'info',
    is_read        BOOLEAN DEFAULT FALSE,
    related_module VARCHAR(50),
    related_id     BIGINT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_read (user_id, is_read),
    INDEX idx_created   (created_at)
);

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- SEED DATA
-- ============================================================

INSERT INTO roles (name, permissions) VALUES
('Admin',              '{"all":true}'),
('Production Manager', '{"jobs":true,"stages":true,"reports":true}'),
('Department Operator','{"stages":true,"weight":true}'),
('Metal Store Manager','{"metal":true,"scrap":true,"refinery":true}'),
('Accountant',         '{"costing":true,"reports":true}'),
('QC Officer',         '{"qc":true,"reports":true}');

-- Passwords set by setup script (all = admin123)
INSERT INTO users (name, email, username, password_hash, role_id) VALUES
('Admin User',   'admin@jewelerp.com',  'admin',  'PLACEHOLDER', 1),
('Ravi Sharma',  'ravi@jewelerp.com',   'ravi',   'PLACEHOLDER', 2),
('Suresh Kumar', 'suresh@jewelerp.com', 'suresh', 'PLACEHOLDER', 3),
('Anita Patel',  'anita@jewelerp.com',  'anita',  'PLACEHOLDER', 4),
('Ramesh Joshi', 'ramesh@jewelerp.com', 'ramesh', 'PLACEHOLDER', 5),
('Priya Singh',  'priya@jewelerp.com',  'priya',  'PLACEHOLDER', 6);

INSERT INTO departments (name, stage_order, requires_weight, requires_approval) VALUES
('Design',        1,  FALSE, FALSE),
('Wax',           2,  TRUE,  FALSE),
('CAM',           3,  FALSE, FALSE),
('Casting',       4,  TRUE,  FALSE),
('Filing',        5,  TRUE,  FALSE),
('Pre-polish',    6,  TRUE,  FALSE),
('Stone Setting', 7,  TRUE,  FALSE),
('Polishing',     8,  TRUE,  FALSE),
('QC',            9,  TRUE,  TRUE),
('Finished Goods',10, TRUE,  FALSE),
('Dispatch',      11, TRUE,  FALSE);

INSERT INTO customers (name, contact_person, phone, email) VALUES
('Mehta Jewellers', 'Rohit Mehta',  '9876543210', 'rohit@mehta.com'),
('Raj Exports',     'Priya Raj',    '9876543211', 'priya@raj.com'),
('Star Diamonds',   'Anand Star',   '9876543212', 'anand@star.com'),
('Puja Jewels',     'Puja Devi',    '9876543213', 'puja@jewels.com'),
('Heritage Gold',   'Vikram Singh', '9876543214', 'vikram@heritage.com');

INSERT INTO metal_stock (metal_type, stock_type, quantity, purity_pct) VALUES
('24K',    'Pure',             500.0000, 99.900),
('22K',    'Alloy',            300.0000, 91.600),
('18K',    'Alloy',            200.0000, 75.000),
('Silver', 'Pure',            1000.0000, 99.900),
('24K',    'Scrap',             45.5000, 85.000),
('24K',    'Refinery Pending',   0.0000, NULL);

INSERT INTO karigars (karigar_code, name, phone, skill_type, piece_rate, daily_rate, experience_years, joined_date) VALUES
('KAR-001', 'Mohammed Salim', '9812345678', 'Stone Setting', 250.00, 800.00, 5, '2020-01-15'),
('KAR-002', 'Rajan Patel',    '9812345679', 'Filigree',      300.00, 900.00, 6, '2019-06-10'),
('KAR-003', 'Deepak Yadav',   '9812345680', 'Casting',       200.00, 700.00, 4, '2021-03-20'),
('KAR-004', 'Firoz Khan',     '9812345681', 'Polishing',     150.00, 600.00, 5, '2020-08-05'),
('KAR-005', 'Sanjay Mehra',   '9812345682', 'Filing',        175.00, 650.00, 3, '2022-01-12'),
('KAR-006', 'Abdul Rashid',   '9812345683', 'Wax',           220.00, 750.00, 7, '2018-11-30');

INSERT INTO inventory_items (item_code, name, category, unit, current_stock, reorder_level, unit_cost) VALUES
('GOLD-24K',  '24K Gold Bar',    'Gold',       'g',    500.00,  50.00, 6200.00),
('GOLD-22K',  '22K Gold Alloy',  'Gold',       'g',    300.00,  30.00, 5700.00),
('GOLD-18K',  '18K Gold Alloy',  'Gold',       'g',    200.00,  20.00, 4650.00),
('SILV-999',  'Silver 999',      'Silver',     'g',   1000.00, 100.00,   80.00),
('STONE-DIA', 'Diamond 0.5ct',   'Stone',      'pcs',  500.00,  50.00, 25000.00),
('STONE-RUB', 'Ruby 3mm',        'Stone',      'pcs', 1000.00, 100.00,   500.00),
('CONS-WAX',  'Injection Wax',   'Consumable', 'kg',    10.00,   2.00, 1200.00),
('CONS-ACID', 'Acid Polish',     'Consumable', 'ltr',    5.00,   1.00,  800.00);

INSERT INTO system_settings (setting_key, setting_value, setting_type, description) VALUES
('company_name',     'Sona Jewellers',     'string',  'Company display name'),
('gold_rate_24k',    '6200',               'number',  'Current 24K gold rate per gram'),
('gold_rate_22k',    '5700',               'number',  'Current 22K gold rate per gram'),
('gold_rate_18k',    '4650',               'number',  'Current 18K gold rate per gram'),
('wastage_default',  '2.5',                'number',  'Default wastage % for new jobs'),
('currency_symbol',  '₹',                  'string',  'Currency symbol');

INSERT INTO scale_devices (name, port, device_type, is_active) VALUES
('Main Scale', 'Simulation', 'Simulation', TRUE);

-- ============================================================
-- MIGRATION SCRIPT (run ONCE on existing DBs to add missing columns)
-- Saved in: database/migration.sql
-- ============================================================