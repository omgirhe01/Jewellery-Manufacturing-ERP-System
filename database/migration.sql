-- ============================================================
-- SONA ERP - Migration v2.1 (MySQL 8.0 compatible)
-- Run ONCE on existing database
-- ============================================================

USE jewellery_erp;

-- ============================================================
-- 1. karigar_assignments — add stage_log_id
-- ============================================================
ALTER TABLE karigar_assignments
    ADD COLUMN stage_log_id BIGINT,
    ADD FOREIGN KEY fk_ka_stagelog (stage_log_id) REFERENCES job_stage_logs(id);

-- ============================================================
-- 2. refinery_dispatches — add total_gross_weight, fix status enum
-- ============================================================
ALTER TABLE refinery_dispatches
    ADD COLUMN total_gross_weight DECIMAL(14,4) DEFAULT 0.0000;

ALTER TABLE refinery_dispatches
    MODIFY COLUMN status
    ENUM('Dispatched','Partial Settlement','Settled') DEFAULT 'Dispatched';

-- ============================================================
-- 3. refinery_settlements — fix payment_status enum
-- ============================================================
ALTER TABLE refinery_settlements
    MODIFY COLUMN payment_status
    ENUM('Pending','Paid','Adjusted') DEFAULT 'Pending';

-- ============================================================
-- 4. job_costs — add gold_weight_used and all missing columns
-- ============================================================
ALTER TABLE job_costs
    ADD COLUMN gold_weight_used   DECIMAL(10,4) DEFAULT 0.0000,
    ADD COLUMN gold_rate          DECIMAL(10,2) DEFAULT 0.00,
    ADD COLUMN gold_cost          DECIMAL(14,2) DEFAULT 0.00,
    ADD COLUMN stone_cost         DECIMAL(14,2) DEFAULT 0.00,
    ADD COLUMN wastage_cost       DECIMAL(14,2) DEFAULT 0.00,
    ADD COLUMN refinery_adjustment DECIMAL(14,2) DEFAULT 0.00,
    ADD COLUMN overhead_cost      DECIMAL(14,2) DEFAULT 0.00,
    ADD COLUMN margin_pct         DECIMAL(6,2)  DEFAULT 0.00;

-- ============================================================
-- Verify
-- ============================================================
SELECT 'karigar_assignments columns:' AS info;
SHOW COLUMNS FROM karigar_assignments;

SELECT 'refinery_dispatches columns:' AS info;
SHOW COLUMNS FROM refinery_dispatches;

SELECT 'job_costs columns:' AS info;
SHOW COLUMNS FROM job_costs;

-- ============================================================
-- 5. metal_ledger — rename 'purity' to 'purity_pct' (backend expects purity_pct)
-- ============================================================
ALTER TABLE metal_ledger
    CHANGE COLUMN purity purity_pct DECIMAL(6,3) DEFAULT NULL;

SELECT 'metal_ledger columns:' AS info;
SHOW COLUMNS FROM metal_ledger;

SELECT 'All done!' AS status;
-- Fix inventory_items category enum mismatch: Stone -> Diamond/Gemstone
-- Run this in MySQL to fix existing data
UPDATE inventory_items SET category = 'Diamond'  WHERE category = 'Stone' AND (name LIKE '%Diamond%' OR name LIKE '%Dia%' OR item_code LIKE '%DIA%');
UPDATE inventory_items SET category = 'Gemstone' WHERE category = 'Stone' AND category = 'Stone';
-- Fix any remaining Stone categories
UPDATE inventory_items SET category = 'Gemstone' WHERE category = 'Stone';

-- Fix finished_goods table: add missing columns
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS item_code VARCHAR(30) AFTER job_id;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS hallmark_no VARCHAR(50) AFTER pieces_count;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS qc_passed BOOLEAN DEFAULT FALSE AFTER hallmark_no;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS qc_officer_id BIGINT AFTER qc_passed;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS qc_date DATETIME AFTER qc_officer_id;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS qc_notes TEXT AFTER qc_date;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS dispatch_date DATETIME AFTER qc_notes;
ALTER TABLE finished_goods ADD COLUMN IF NOT EXISTS dispatch_ref VARCHAR(60) AFTER dispatch_date;

ALTER TABLE finished_goods 
  ADD COLUMN item_code VARCHAR(30) AFTER job_id,
  ADD COLUMN hallmark_no VARCHAR(50) AFTER pieces_count,
  ADD COLUMN qc_notes TEXT AFTER qc_date;