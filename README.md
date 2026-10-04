# Constraint-Based Intelligent Workforce Scheduling and Fair Workload Optimization System

A comprehensive web application designed for intelligent shift scheduling, hard constraint satisfaction, workload balancing, and transparent conflict root-cause diagnostics.

---

## 🚀 Key Features

1. **Employee Management (CRUD)**:
   - Full control to Add, View, Edit, Toggle Status, and Delete employees.
   - Profile configuration includes: Employee Code, Name, Email, Phone, Role, Target Hours, Maximum Weekly Hours, Skills with Proficiency, and a 7-Day Availability Matrix (Monday–Sunday).

2. **Task & Shift Demand Management (CRUD)**:
   - Add, Edit, List, and Delete operational tasks.
   - Parameters include: Task Code, Title, Shift Category (Morning, Afternoon, Night, Flexible), Day of Week, Start Time, Deadline/End Time, Duration, Required Skill, Headcount (min staff), and Priority (Normal, High, Critical).

3. **Bulk Entry & 1-Click Test Presets**:
   - Multi-row bulk entry for entering 5–10+ employees and tasks simultaneously.
   - **Preset A (5 Employees)**: Diverse skill team (Supervision, Inventory, Tech, Customer Support) with customized weekly hour limits (30h–40h).
   - **Preset B (10 Employees)**: Large-scale operations team across 6 skill disciplines for full fairness benchmarking.
   - **Preset C (15 Standard Tasks)**: Standard weekly tasks across Mon–Fri (Morning, Afternoon, Night).
   - **Preset D (Conflict Stress Test)**: Tests hard constraint handling (missing skills, time overlaps, max hour limits).

4. **Genuine Constraint Satisfaction Problem (CSP) Solver**:
   - Dual-engine architecture:
     - **Google OR-Tools CP-SAT** constraint satisfaction solver.
     - **Pure-Python Backtracking Search** with **Minimum Remaining Values (MRV)** and **Forward Checking / Pruning**.
   - Enforces **8 Hard Constraints**:
     1. **Skill Constraint**: Staff must possess required qualifications.
     2. **Availability Window Constraint**: Staff must be marked available during task times.
     3. **No Overlapping Tasks Constraint**: Zero concurrent task double-booking for the same worker.
     4. **Minimum Rest Period Constraint**: Mandatory 11-hour rest interval between consecutive shifts.
     5. **Maximum Working Hours Constraint**: Weekly total hours must never exceed contract ceilings.
     6. **Staffing Capacity Constraint**: Fulfills multi-worker headcount requirements.
     7. **Task Deadline Constraint**: Tasks are completed strictly within allowed windows.
     8. **Priority Weighting**: Critical and high-priority tasks are scheduled before lower-priority tasks.
   - **Multi-Objective Fair Workload Optimization**:
     - Minimizes variance in assigned hours across workers against contract targets.
     - Balances night-shift distribution fairly across all eligible employees.

5. **Transparent Conflict & Unassigned Task Diagnostics**:
   - If an impossible task cannot be scheduled, it is never assigned incorrectly.
   - The engine performs root-cause conflict relaxation analysis to report exact failure reasons (e.g., *Missing Skill*, *Time Overlap with another task*, *Exceeded Weekly Hours Limit*, *Availability Window Mismatch*).

6. **Interactive Schedule Dashboard & Roster Matrix**:
   - Summary statistics (Total Slots, Assigned Slots, Unassigned Slots, Fulfillment Rate, Fairness Score).
   - Generated Work Assignments table.
   - Employee Workload Distribution with visual utilization meters.
   - Visual 7-day Weekly Shift Roster Matrix (Morning, Afternoon, Night).
   - One-click CSV Schedule Export.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.13.12, Flask 3.1.3
- **CSP Solvers**: Google OR-Tools CP-SAT & Pure-Python CSP Backtracking Engine
- **Database**: SQLite 3 (embedded relational database with foreign keys enabled)
- **Frontend**: Responsive HTML5, Custom Design System CSS3, Vanilla ES6 JavaScript

---

## 📁 Project Structure

```
AI MINI PROJECT/
├── app.py                      # Main Flask application with all routes & endpoints
├── run.py                      # Application launcher script
├── requirements.txt            # Python dependencies
├── README.md                   # System documentation & usage instructions
│
├── app/
│   ├── csp_solver.py           # Formal CSP Engine (OR-Tools + MRV Backtracking)
│   ├── database.py             # SQLite helper functions
│   ├── config.py               # Application configuration
│   └── routes/main.py          # Routes
│
├── data/
│   ├── schema.sql              # Complete SQLite DDL schema (9 tables)
│   └── workforce.db            # Active SQLite database file
│
├── templates/                  # Full Jinja2 UI templates
│   ├── base.html               # Global navigation layout
│   ├── index.html              # Main system dashboard & DB diagnostics
│   ├── bulk_entry.html         # 1-Click presets (5 & 10 employees) & bulk entry forms
│   ├── employees/              # Employee CRUD templates (index, form, detail)
│   ├── tasks/                  # Task CRUD templates (index, form)
│   ├── scheduler/              # Schedule generation dashboard & conflict explanations
│   └── roster/                 # 7-day visual weekly matrix roster
│
├── static/
│   ├── css/style.css           # Modern design system & responsive styling
│   └── js/main.js              # Client-side filters & dynamic rows
│
└── tests/
    ├── test_basic.py           # DB connection & health tests
    ├── test_csp_scheduler.py   # CSP algorithm unit tests (6 test cases)
    ├── test_employees.py       # Employee CRUD integration tests
    └── test_tasks_and_scheduler.py # Tasks, Presets, CSP & User Scenario tests
```

---

## ⚙️ How to Run

### 1. Run Automated Test Suite (23 Tests)
```powershell
python -m unittest discover -s tests -v
```

### 2. Start the Flask Application
```powershell
python app.py
```
*(Alternatively: `python run.py`)*

### 3. Open Web Application
Navigate in your web browser to:
```
http://127.0.0.1:5000
```

---

## 🧪 Demonstration Steps (For College Project Evaluation)

### Step 1: Employee Management
1. Go to **Employees** (`http://127.0.0.1:5000/employees`).
2. View existing employee records or click **"+ Add New Employee"** to enter an employee with custom skills and availability matrix.

### Step 2: 1-Click Presets & Bulk Entry
1. Go to **Bulk Entry** (`http://127.0.0.1:5000/bulk-entry`).
2. Click **"Load 5 Employees"** (Preset A) or **"Load 10 Employees"** (Preset B).
3. Click **"Load 15 Tasks"** (Preset C) to populate operational tasks across Monday–Friday.

### Step 3: Run the Intelligent Scheduler
1. Go to **Intelligent Scheduler** (`http://127.0.0.1:5000/scheduler`).
2. Click **"⚡ Generate Work Assignments"**.
3. Observe:
   - **Fulfillment & Fairness Score** computed automatically.
   - **Generated Work Assignments**: Each slot displays task title, day, time, assigned employee, matched skill, and role.
   - **Employee Workload**: Shows assigned hours, target hours, and utilization progress bars.
   - **Overlap Prevention**: Proves that no employee is double-booked across overlapping time windows.

### Step 4: Test Impossible Schedule & Conflict Diagnostics
1. Return to **Bulk Entry** and click **"Load Stress-Test Tasks"** (Preset D).
2. Go to **Intelligent Scheduler** and click **"⚡ Generate Work Assignments"**.
3. View the **Unassigned Tasks & Conflict Root-Cause Explanations** section showing transparent reasons (*Missing Skill*, *Time Overlap*, *Max Hours Limit*).

### Step 5: View Weekly Roster & CSV Export
1. Click **Weekly Roster** (`http://127.0.0.1:5000/roster`) to see the 7-day schedule grid divided into Morning, Afternoon, and Night shifts.
2. Click **"📥 Export CSV"** on the Scheduler or Roster page to download the schedule file.
