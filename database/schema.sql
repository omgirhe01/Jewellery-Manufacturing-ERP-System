-- ============================================================
-- JEWELLERY MANUFACTURING ERP - Complete MySQL Schema
-- MySQL 8.0 | InnoDB | ACID Compliant | 25+ Tables
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
    module     VARCHAR(50) NOT NULL,
    record_id  BIGINT,
    old_value  JSON,
    new_value  JSON,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_module_user (module, user_id),
    INDEX idx_created (created_at)
);

-- ============================================================
-- TABLE 4: CUSTOMERS
-- ============================================================
CREATE TABLE customers (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    contact    VARCHAR(100),
    phone      VARCHAR(20),
    email      VARCHAR(100),
    address    TEXT,
    gst_no     VARCHAR(20),
    is_active  BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 5: DEPARTMENTS (11 Production Stages)
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
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- ============================================================
-- TABLE 7: JOBS (Core Business Table)
-- ============================================================
CREATE TABLE jobs (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_code           VARCHAR(25) NOT NULL UNIQUE,
    barcode            VARCHAR(100) UNIQUE,
    barcode_image_b64  MEDIUMTEXT,
    design_id          BIGINT,
    design_name        VARCHAR(100),
    customer_id        BIGINT NOT NULL,
    metal_type         ENUM('24K','22K','18K','Silver','Other') NOT NULL,
    target_weight      DECIMAL(10,3) NOT NULL,
    current_weight     DECIMAL(10,3) DEFAULT 0.000,
    wastage_allowed    DECIMAL(5,2) DEFAULT 2.50,
    order_qty          INT DEFAULT 1,
    current_stage      ENUM('Design','Wax','CAM','Casting','Filing',
                            'Pre-polish','Stone Setting','Polishing',
                            'QC','Finished Goods','Dispatch') DEFAULT 'Design',
    status             ENUM('New','Active','QC Pending','QC Rejected',
                            'Completed','Dispatched','On Hold','Cancelled') DEFAULT 'New',
    priority           ENUM('Normal','High','Urgent') DEFAULT 'Normal',
    expected_delivery  DATE,
    notes              TEXT,
    created_by         BIGINT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (design_id)   REFERENCES designs(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (created_by)  REFERENCES users(id),
    INDEX idx_job_code (job_code),
    INDEX idx_status_stage (status, current_stage),
    INDEX idx_customer (customer_id),
    INDEX idx_created (created_at)
);

-- ============================================================
-- TABLE 8: JOB STAGES
-- ============================================================
CREATE TABLE job_stages (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id           BIGINT NOT NULL,
    department_id    INT NOT NULL,
    stage_name       VARCHAR(50) NOT NULL,
    operator_id      BIGINT,
    weight_in        DECIMAL(10,4),
    weight_out       DECIMAL(10,4),
    weight_variance  DECIMAL(10,4),
    variance_pct     DECIMAL(6,3),
    status           ENUM('Pending','In Progress','Completed','Rejected') DEFAULT 'Pending',
    started_at       TIMESTAMP NULL,
    completed_at     TIMESTAMP NULL,
    approved_by      BIGINT,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)        REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (operator_id)   REFERENCES users(id),
    FOREIGN KEY (approved_by)   REFERENCES users(id),
    INDEX idx_job_stage (job_id, stage_name)
);

-- ============================================================
-- TABLE 9: BARCODE SCANS
-- ============================================================
CREATE TABLE barcode_scans (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    barcode       VARCHAR(100) NOT NULL,
    job_id        BIGINT,
    scanned_by    BIGINT,
    department_id INT,
    scan_type     ENUM('Check-In','Check-Out','QC','Dispatch') DEFAULT 'Check-In',
    scanned_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)        REFERENCES jobs(id),
    FOREIGN KEY (scanned_by)    REFERENCES users(id),
    FOREIGN KEY (department_id) REFERENCES departments(id),
    INDEX idx_barcode (barcode),
    INDEX idx_scan_time (scanned_at)
);

-- ============================================================
-- TABLE 10: WEIGHT LOGS
-- ============================================================
CREATE TABLE weight_logs (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id        BIGINT NOT NULL,
    job_stage_id  BIGINT,
    department_id INT,
    gross_weight  DECIMAL(10,4) NOT NULL,
    tare_weight   DECIMAL(10,4) DEFAULT 0.0000,
    net_weight    DECIMAL(10,4) NOT NULL,
    scale_id      VARCHAR(50),
    operator_id   BIGINT,
    is_manual     BOOLEAN DEFAULT FALSE,
    is_simulated  BOOLEAN DEFAULT FALSE,
    captured_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)        REFERENCES jobs(id),
    FOREIGN KEY (job_stage_id)  REFERENCES job_stages(id),
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (operator_id)   REFERENCES users(id),
    INDEX idx_job_weights (job_id)
);

-- ============================================================
-- TABLE 11: METAL STOCK
-- ============================================================
CREATE TABLE metal_stock (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    metal_type ENUM('24K','22K','18K','Silver','Alloy','Scrap') NOT NULL,
    stock_type ENUM('Pure','Alloy','Scrap','Refinery Pending') NOT NULL,
    quantity   DECIMAL(14,4) NOT NULL DEFAULT 0.0000,
    purity     DECIMAL(5,3),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_metal_stock (metal_type, stock_type)
);

-- ============================================================
-- TABLE 12: METAL LEDGER (ACID Critical)
-- ============================================================
CREATE TABLE metal_ledger (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_type ENUM('Issue','Return','Adjustment','Refinery Out','Refinery In') NOT NULL,
    metal_type       ENUM('24K','22K','18K','Silver','Alloy','Scrap') NOT NULL,
    job_id           BIGINT,
    department_id    INT,
    karigar_id       BIGINT,
    weight           DECIMAL(12,4) NOT NULL,
    purity           DECIMAL(5,3),
    fine_weight      DECIMAL(12,4),
    issue_rate       DECIMAL(10,2),
    total_value      DECIMAL(14,2),
    issued_to_type   ENUM('Department','Karigar') NULL,
    issued_to_id     BIGINT NULL,
    issued_to_name   VARCHAR(100),
    balance_after    DECIMAL(14,4),
    reference_no     VARCHAR(50),
    notes            TEXT,
    created_by       BIGINT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)        REFERENCES jobs(id),
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (created_by)    REFERENCES users(id),
    INDEX idx_job_metal (job_id),
    INDEX idx_txn_type (transaction_type),
    INDEX idx_created (created_at)
);

-- ============================================================
-- TABLE 13: KARIGARS
-- ============================================================
CREATE TABLE karigars (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    karigar_code VARCHAR(20) UNIQUE NOT NULL,
    name         VARCHAR(100) NOT NULL,
    phone        VARCHAR(20),
    address      TEXT,
    skill_type   VARCHAR(50),
    piece_rate   DECIMAL(10,2) DEFAULT 0.00,
    is_active    BOOLEAN DEFAULT TRUE,
    joined_date  DATE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_karigar_code (karigar_code)
);

-- ============================================================
-- TABLE 14: KARIGAR ASSIGNMENTS
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
    FOREIGN KEY (job_stage_id) REFERENCES job_stages(id),
    INDEX idx_karigar_job (karigar_id, job_id)
);

-- ============================================================
-- TABLE 15: SCRAP ENTRIES
-- ============================================================
CREATE TABLE scrap_entries (
    id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id             VARCHAR(30) NOT NULL UNIQUE,
    source_department_id INT NOT NULL,
    scrap_type           ENUM('Filing','Casting','Polishing Dust','Broken Pieces','Other') NOT NULL,
    gross_weight         DECIMAL(10,4) NOT NULL,
    estimated_purity     DECIMAL(5,3),
    estimated_fine_weight DECIMAL(10,4),
    status               ENUM('Collected','In Stock','Sent to Refinery','Settled') DEFAULT 'Collected',
    collected_by         BIGINT,
    collected_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes                TEXT,
    FOREIGN KEY (source_department_id) REFERENCES departments(id),
    FOREIGN KEY (collected_by) REFERENCES users(id),
    INDEX idx_batch (batch_id),
    INDEX idx_status (status)
);

-- ============================================================
-- TABLE 16: REFINERY DISPATCHES
-- ============================================================
CREATE TABLE refinery_dispatches (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    dispatch_no        VARCHAR(30) NOT NULL UNIQUE,
    refinery_name      VARCHAR(100) NOT NULL,
    dispatch_date      DATE NOT NULL,
    gross_weight       DECIMAL(12,4) NOT NULL,
    estimated_purity   DECIMAL(5,3),
    expected_fine_gold DECIMAL(12,4),
    status             ENUM('Dispatched','Settled','Partial') DEFAULT 'Dispatched',
    notes              TEXT,
    created_by         BIGINT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- ============================================================
-- TABLE 17: REFINERY SETTLEMENTS
-- ============================================================
CREATE TABLE refinery_settlements (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    dispatch_id        BIGINT NOT NULL UNIQUE,
    settlement_date    DATE NOT NULL,
    fine_gold_received DECIMAL(12,4) NOT NULL,
    recovery_pct       DECIMAL(5,3),
    refining_charges   DECIMAL(10,2) DEFAULT 0.00,
    variance_pct       DECIMAL(6,3),
    settlement_notes   TEXT,
    created_by         BIGINT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dispatch_id) REFERENCES refinery_dispatches(id),
    FOREIGN KEY (created_by)  REFERENCES users(id)
);

-- ============================================================
-- TABLE 18: REFINERY DISPATCH BATCHES
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
-- TABLE 19: INVENTORY ITEMS
-- ============================================================
CREATE TABLE inventory_items (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_code     VARCHAR(30) UNIQUE NOT NULL,
    name          VARCHAR(100) NOT NULL,
    category      ENUM('Gold','Silver','Stone','Consumable','WIP','Finished Good') NOT NULL,
    unit          VARCHAR(20) NOT NULL,
    current_stock DECIMAL(14,4) DEFAULT 0.0000,
    reorder_level DECIMAL(14,4) DEFAULT 0.0000,
    unit_cost     DECIMAL(10,2) DEFAULT 0.00,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_category (category)
);

-- ============================================================
-- TABLE 20: INVENTORY TRANSACTIONS
-- ============================================================
CREATE TABLE inventory_transactions (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_id          BIGINT NOT NULL,
    transaction_type ENUM('In','Out','Adjust') NOT NULL,
    quantity         DECIMAL(14,4) NOT NULL,
    balance_after    DECIMAL(14,4) NOT NULL,
    reference_type   VARCHAR(50),
    reference_id     BIGINT,
    notes            TEXT,
    created_by       BIGINT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id)    REFERENCES inventory_items(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- ============================================================
-- TABLE 21: FINISHED GOODS
-- ============================================================
CREATE TABLE finished_goods (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id         BIGINT NOT NULL UNIQUE,
    final_weight   DECIMAL(10,4),
    pieces_count   INT DEFAULT 1,
    qc_passed      BOOLEAN DEFAULT FALSE,
    qc_officer_id  BIGINT,
    qc_date        TIMESTAMP NULL,
    dispatch_date  TIMESTAMP NULL,
    dispatch_ref   VARCHAR(50),
    status         ENUM('Ready','Dispatched','On Hold') DEFAULT 'Ready',
    FOREIGN KEY (job_id)        REFERENCES jobs(id),
    FOREIGN KEY (qc_officer_id) REFERENCES users(id)
);

-- ============================================================
-- TABLE 22: JOB COSTS
-- ============================================================
CREATE TABLE job_costs (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id              BIGINT NOT NULL UNIQUE,
    gold_cost           DECIMAL(14,2) DEFAULT 0.00,
    labour_cost         DECIMAL(14,2) DEFAULT 0.00,
    stone_cost          DECIMAL(14,2) DEFAULT 0.00,
    wastage_cost        DECIMAL(14,2) DEFAULT 0.00,
    refinery_adjustment DECIMAL(14,2) DEFAULT 0.00,
    overhead_cost       DECIMAL(14,2) DEFAULT 0.00,
    total_cost          DECIMAL(14,2) DEFAULT 0.00,
    sale_price          DECIMAL(14,2) DEFAULT 0.00,
    profit_loss         DECIMAL(14,2) DEFAULT 0.00,
    margin_pct          DECIMAL(6,3)  DEFAULT 0.000,
    calculated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- SEED DATA
-- ============================================================

INSERT INTO roles (name, permissions) VALUES
('Admin',              '{"all": true}'),
('Production Manager', '{"jobs":true,"stages":true,"reports":true}'),
('Department Operator','{"stages":true,"weight":true}'),
('Metal Store Manager','{"metal":true,"scrap":true,"refinery":true}'),
('Accountant',         '{"costing":true,"reports":true}'),
('QC Officer',         '{"qc":true,"reports":true}');

-- Passwords will be set by setup script (all = admin123)
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

INSERT INTO customers (name, contact, phone, email) VALUES
('Mehta Jewellers', 'Rohit Mehta',  '9876543210', 'rohit@mehta.com'),
('Raj Exports',     'Priya Raj',    '9876543211', 'priya@raj.com'),
('Star Diamonds',   'Anand Star',   '9876543212', 'anand@star.com'),
('Puja Jewels',     'Puja Devi',    '9876543213', 'puja@jewels.com'),
('Heritage Gold',   'Vikram Singh', '9876543214', 'vikram@heritage.com');

INSERT INTO metal_stock (metal_type, stock_type, quantity, purity) VALUES
('24K',    'Pure',             500.0000, 0.999),
('22K',    'Alloy',            300.0000, 0.916),
('18K',    'Alloy',            200.0000, 0.750),
('Silver', 'Pure',            1000.0000, 0.999),
('24K',    'Scrap',             45.5000, 0.850),
('24K',    'Refinery Pending',   0.0000, NULL);

INSERT INTO karigars (karigar_code, name, phone, skill_type, piece_rate, joined_date) VALUES
('KAR-001', 'Mohammed Salim', '9812345678', 'Stone Setting', 250.00, '2020-01-15'),
('KAR-002', 'Rajan Patel',    '9812345679', 'Filigree',      300.00, '2019-06-10'),
('KAR-003', 'Deepak Yadav',   '9812345680', 'Casting',       200.00, '2021-03-20'),
('KAR-004', 'Firoz Khan',     '9812345681', 'Polishing',     150.00, '2020-08-05'),
('KAR-005', 'Sanjay Mehra',   '9812345682', 'Filing',        175.00, '2022-01-12'),
('KAR-006', 'Abdul Rashid',   '9812345683', 'Wax',           220.00, '2018-11-30');

INSERT INTO inventory_items (item_code, name, category, unit, current_stock, reorder_level, unit_cost) VALUES
('GOLD-24K',  '24K Gold Bar',    'Gold',       'g',    500.00,  50.00, 6200.00),
('GOLD-22K',  '22K Gold Alloy',  'Gold',       'g',    300.00,  30.00, 5700.00),
('GOLD-18K',  '18K Gold Alloy',  'Gold',       'g',    200.00,  20.00, 4650.00),
('SILV-999',  'Silver 999',      'Silver',     'g',   1000.00, 100.00,   80.00),
('STONE-DIA', 'Diamond 0.5ct',   'Stone',      'pcs',  500.00,  50.00, 25000.00),
('STONE-RUB', 'Ruby 3mm',        'Stone',      'pcs', 1000.00, 100.00,   500.00),
('CONS-WAX',  'Injection Wax',   'Consumable', 'kg',    10.00,   2.00, 1200.00),
('CONS-ACID', 'Acid Polish',     'Consumable', 'ltr',    5.00,   1.00,  800.00);
