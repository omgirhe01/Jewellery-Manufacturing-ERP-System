# 🪙 Jewellery Manufacturing ERP System
## FastAPI + MySQL 8.0 + HTML/CSS/JS | Production Ready

---

## 📁 Project Structure

```
jewellery-erp/
├── backend/
│   ├── app/
│   │   ├── main.py                    ← FastAPI entry point
│   │   ├── core/
│   │   │   ├── config.py              ← Settings (DB, JWT, Scale)
│   │   │   ├── database.py            ← SQLAlchemy engine + session
│   │   │   └── security.py            ← JWT auth + bcrypt
│   │   ├── models/
│   │   │   └── all_models.py          ← All 25 database models
│   │   ├── api/v1/
│   │   │   └── all_routers.py         ← All 100+ API endpoints
│   │   └── services/
│   │       ├── scale_service.py       ← Scale integration + simulation
│   │       ├── barcode_service.py     ← Code128 barcode generation
│   │       └── helpers.py             ← Utilities, code generators
│   ├── setup_passwords.py             ← One-time password setup script
│   ├── requirements.txt               ← Python dependencies
│   └── .env.example                   ← Environment config template
├── database/
│   └── schema.sql                     ← Complete MySQL schema (25 tables + seed)
└── frontend/
    ├── static/
    │   ├── css/main.css               ← Design system
    │   └── js/main.js                 ← API client + utilities
    └── templates/                     ← Jinja2 HTML pages (12 pages)
        ├── base.html, login.html, dashboard.html
        ├── jobs.html, metal.html, karigar.html
        ├── scrap.html, refinery.html, inventory.html
        ├── costing.html, reports.html, users.html
        └── scale.html
```

---

## 🚀 STEP-BY-STEP SETUP (VS Code / Windows)

### STEP 1 — Install Required Software

Download and install these if you don't have them:
- **Python 3.11+** → https://www.python.org/downloads/
- **MySQL 8.0** → https://dev.mysql.com/downloads/installer/
- **VS Code** → https://code.visualstudio.com/

During MySQL install, set root password — **remember it!**

---

### STEP 2 — Open Project in VS Code

```
File → Open Folder → Select the jewellery-erp folder
```

Open VS Code Terminal: **Ctrl + `** (backtick)

---

### STEP 3 — Go to backend folder

```powershell
cd backend
```

---

### STEP 4 — Create Python Virtual Environment

```powershell
python -m venv venv
```

Activate it:
```powershell
venv\Scripts\activate
```

You should see `(venv)` at the start of your terminal prompt.

---

### STEP 5 — Install Python packages

```powershell
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, pymysql, JWT, barcode library etc.
Takes 1-3 minutes.

---

### STEP 6 — Create the Database in MySQL

Open a NEW terminal (keep venv terminal open) and run:

```powershell
mysql -u root -p
```

Type your MySQL root password when asked. Then inside MySQL:

```sql
SOURCE C:/path/to/jewellery-erp/database/schema.sql;
```

Replace `C:/path/to/` with your actual folder path.
Example: `SOURCE C:/Users/omgir/Downloads/jewellery-erp/database/schema.sql;`

Then type:
```sql
EXIT;
```

---

### STEP 7 — Configure Environment

Back in the backend terminal (with venv active):

```powershell
copy .env.example .env
```

Open `.env` in VS Code and set your MySQL password:

```
DB_PASSWORD=your_actual_mysql_password_here
```

Leave everything else as-is for development.

---

### STEP 8 — Set User Passwords

```powershell
python setup_passwords.py
```

This sets all user passwords to `admin123`.

---

### STEP 9 — Start the Server

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
✅ Database tables created/verified
🚀 Jewellery ERP v1.0.0 started
📖 API docs: http://localhost:8000/docs
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### STEP 10 — Open in Browser

| URL | Page |
|-----|------|
| http://localhost:8000 | Dashboard |
| http://localhost:8000/login | Login |
| http://localhost:8000/docs | Swagger API Docs |

**Default Login:** `admin` / `admin123`

---

## 👤 All Login Credentials

| Username | Password | Role |
|----------|----------|------|
| admin    | admin123 | Admin (full access) |
| ravi     | admin123 | Production Manager |
| suresh   | admin123 | Department Operator |
| metalm   | admin123 | Metal Store Manager |
| priya    | admin123 | Accountant |
| qcraj    | admin123 | QC Officer |

---

## 📋 All Pages

| URL | Module |
|-----|--------|
| `/` | Dashboard |
| `/jobs` | Job & Production Management |
| `/metal` | Metal Ledger & Accounting |
| `/karigar` | Karigar Management |
| `/scrap` | Scrap Management |
| `/refinery` | Refinery Management |
| `/inventory` | Inventory |
| `/costing` | Job Costing |
| `/reports` | Reports & Analytics |
| `/users` | User Management |
| `/scale` | Weighing Scale (Simulation) |

---

## 🔌 API Endpoints Reference

All APIs start with `/api/v1/`. Open http://localhost:8000/docs for full interactive docs.

```
POST  /api/v1/auth/login           Login
GET   /api/v1/auth/me              Current user

GET   /api/v1/jobs/                List jobs
POST  /api/v1/jobs/                Create job
GET   /api/v1/jobs/{id}            Get job detail
POST  /api/v1/jobs/{id}/advance-stage  Move to next stage
GET   /api/v1/jobs/barcode/{bc}    Lookup by barcode

GET   /api/v1/scale/status         Scale status
POST  /api/v1/scale/read-weight    Read weight (simulation)
POST  /api/v1/scale/log-weight     Log weight to job

POST  /api/v1/metal/issue          Issue metal
POST  /api/v1/metal/return         Return metal
GET   /api/v1/metal/ledger         Transaction history
GET   /api/v1/metal/reconciliation Daily reconciliation

GET   /api/v1/karigar/             List karigars
POST  /api/v1/karigar/assign       Assign job
GET   /api/v1/karigar/wage-report  Wage report

POST  /api/v1/scrap/               Record scrap
GET   /api/v1/scrap/summary        Scrap summary

POST  /api/v1/refinery/dispatch    New refinery dispatch
POST  /api/v1/refinery/settle      Record settlement

GET   /api/v1/inventory/           List inventory
POST  /api/v1/inventory/adjust     Stock adjustment

POST  /api/v1/costing/calculate    Calculate job cost
GET   /api/v1/costing/profitability Profitability report

GET   /api/v1/reports/dashboard    All KPIs
GET   /api/v1/reports/weight-variance    Weight variance
GET   /api/v1/reports/karigar-productivity  Karigar stats
GET   /api/v1/reports/audit-trail    Activity log
```

---

## ⚖ Weighing Scale

### Simulation Mode (Default — No hardware needed)
Scale simulation is ON by default. It generates realistic weights with ±3% variance.

Test it: Go to http://localhost:8000/scale and click **"Read Weight"**

### Real Scale (USB/RS232)
1. Set `SCALE_SIMULATION=false` in `.env`
2. Set `SCALE_PORT=COM3` (check your port in Device Manager)
3. Restart server

---

## 🏭 Production Flow — 11 Stages

```
Design → Wax → CAM → Casting → Filing →
Pre-polish → Stone Setting → Polishing →
Quality Control → Finished Goods → Dispatch
```

Each stage:
- Records weight in/out
- Calculates variance
- Tracks operator/karigar
- Requires approval (QC stage)

---

## ❓ Troubleshooting

**"ModuleNotFoundError"**
```powershell
# Make sure venv is activated
venv\Scripts\activate
pip install -r requirements.txt
```

**"Can't connect to MySQL"**
- Check `.env` DB_PASSWORD is correct
- Make sure MySQL service is running: `net start MySQL80`

**"No such file requirements.txt"**
```powershell
# Make sure you're in the backend folder
cd backend
ls  # Should show requirements.txt
```

**Port 8000 already in use**
```powershell
uvicorn app.main:app --reload --port 8001
```

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.115 + Python 3.11 |
| ORM | SQLAlchemy 2.0 |
| Database | MySQL 8.0 (InnoDB, ACID) |
| Auth | JWT (python-jose) + bcrypt |
| Templates | Jinja2 |
| Frontend | Vanilla HTML + CSS + JS |
| Scale | pyserial + Simulation Mode |
| Barcode | python-barcode (Code128) |
