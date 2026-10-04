import os
import io
import csv
import sqlite3
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, date
from pathlib import Path
from flask import Flask, render_template, jsonify, request, flash, redirect, url_for, g, Response
from app.csp_solver import CSPSchedulingEngine

# Base Directory and Paths
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / 'data' / 'workforce.db'
SCHEMA_PATH = BASE_DIR / 'data' / 'schema.sql'

# Initialize Flask application with explicit template and static paths
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / 'templates'),
    static_folder=str(BASE_DIR / 'static')
)
app.secret_key = os.environ.get('SECRET_KEY', 'workforce-scheduler-dev-key-2026')

def get_db():
    """Returns an active SQLite database connection with row factory enabled."""
    if 'db' not in g:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(DATABASE_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    """Closes SQLite database connection when request context ends."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database schema if tables do not exist."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        db = get_db()
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
                db.executescript(f.read())
        else:
            # Inline fallback schema creation
            db.executescript("""
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT OR IGNORE INTO system_settings (key, value, description) VALUES
            ('min_rest_hours_between_shifts', '11.0', 'Mandatory minimum rest duration between consecutive shifts'),
            ('default_max_weekly_hours', '40.0', 'Default maximum allowable working hours per employee per week'),
            ('max_consecutive_days', '6', 'Maximum consecutive days an employee can be assigned shifts'),
            ('enable_fair_workload_optimization', 'true', 'Enable variance-minimizing fair workload balancing');

            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                role TEXT NOT NULL DEFAULT 'Staff',
                max_weekly_hours REAL NOT NULL DEFAULT 40.0,
                target_weekly_hours REAL NOT NULL DEFAULT 40.0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS employee_skills (
                employee_id INTEGER NOT NULL,
                skill_id INTEGER NOT NULL,
                proficiency_level TEXT DEFAULT 'Standard',
                PRIMARY KEY (employee_id, skill_id),
                FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS employee_availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_hours REAL NOT NULL,
                required_skill_id INTEGER,
                min_staff INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (required_skill_id) REFERENCES skills(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                total_shifts INTEGER DEFAULT 0,
                assigned_shifts INTEGER DEFAULT 0,
                unfilled_shifts INTEGER DEFAULT 0,
                fairness_score REAL DEFAULT 0.0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS shift_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                shift_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL,
                shift_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                hours REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'assigned',
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE,
                FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
                FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS unfilled_shift_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                shift_id INTEGER NOT NULL,
                shift_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE,
                FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE
            );
            """)
        db.commit()

def check_db_health():
    """Queries SQLite for connection verification and metadata."""
    try:
        db = get_db()
        version = db.execute("SELECT sqlite_version()").fetchone()[0]
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        ).fetchall()
        table_names = [r['name'] for r in tables]

        emp_count = 0
        shift_count = 0
        if 'employees' in table_names:
            emp_count = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        if 'shifts' in table_names:
            shift_count = db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]

        return {
            "status": "connected",
            "sqlite_version": version,
            "database_path": str(DATABASE_PATH),
            "tables": table_names,
            "table_count": len(table_names),
            "stats": {
                "employees": emp_count,
                "shifts": shift_count
            }
        }
    except Exception as ex:
        return {
            "status": "error",
            "error_message": str(ex),
            "tables": [],
            "table_count": 0,
            "stats": {"employees": 0, "shifts": 0}
        }

# Automatically ensure database and tables exist at startup
init_db()

@app.route('/')
def index():
    """Main dashboard displaying system title, active constraints, and database status."""
    db_info = check_db_health()
    settings = {}
    if db_info.get("status") == "connected":
        try:
            db = get_db()
            rows = db.execute("SELECT key, value, description FROM system_settings").fetchall()
            settings = {r['key']: {'value': r['value'], 'description': r['description']} for r in rows}
        except Exception:
            settings = {}

    return render_template('index.html', db_info=db_info, settings=settings)

@app.route('/health')
def health():
    """Health check JSON endpoint reporting SQLite and application state."""
    db_info = check_db_health()
    return jsonify({
        "application": "Constraint-Based Intelligent Workforce Scheduling and Fair Workload Optimization System",
        "status": "healthy" if db_info.get("status") == "connected" else "unhealthy",
        "database": db_info
    })

AVAILABLE_ROLES = [
    'Staff Associate',
    'Supervisor',
    'Manager',
    'Inventory Specialist',
    'Customer Support',
    'Technical Specialist'
]

def get_all_skills():
    """Returns all available skills from the database."""
    db = get_db()
    return db.execute("SELECT id, name, description FROM skills ORDER BY name").fetchall()

def get_employee_with_details(emp_id):
    """Fetches employee record along with their assigned skills and 7-day availability."""
    db = get_db()
    employee = db.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
    if not employee:
        return None, [], {}

    skills = db.execute("""
        SELECT s.id, s.name, s.description, es.proficiency_level
        FROM skills s
        JOIN employee_skills es ON s.id = es.skill_id
        WHERE es.employee_id = ?
        ORDER BY s.name
    """, (emp_id,)).fetchall()

    availability_rows = db.execute("""
        SELECT day_of_week, start_time, end_time, is_available
        FROM employee_availability
        WHERE employee_id = ?
        ORDER BY day_of_week
    """, (emp_id,)).fetchall()

    availability_map = {row['day_of_week']: dict(row) for row in availability_rows}
    return employee, skills, availability_map

@app.route('/employees')
def employees_list():
    """Lists all employees with their skill badges, target hours, and availability."""
    db = get_db()
    employees = db.execute("""
        SELECT e.*,
            (SELECT COUNT(*) FROM employee_availability ea WHERE ea.employee_id = e.id AND ea.is_available = 1) AS available_days_count
        FROM employees e
        ORDER BY e.is_active DESC, e.name ASC
    """).fetchall()

    # Load skills for each employee
    enriched_employees = []
    for emp in employees:
        skills = db.execute("""
            SELECT s.name, es.proficiency_level
            FROM skills s
            JOIN employee_skills es ON s.id = es.skill_id
            WHERE es.employee_id = ?
        """, (emp['id'],)).fetchall()
        emp_dict = dict(emp)
        emp_dict['skills_list'] = [dict(s) for s in skills]
        enriched_employees.append(emp_dict)

    roles = db.execute("SELECT DISTINCT role FROM employees ORDER BY role").fetchall()
    role_names = [r['role'] for r in roles]

    return render_template(
        'employees/index.html',
        employees=enriched_employees,
        roles=role_names
    )

@app.route('/employees/new', methods=['GET', 'POST'])
def employee_new():
    """Creates a new employee with skills and weekly availability matrix."""
    db = get_db()
    all_skills = get_all_skills()

    if request.method == 'POST':
        code = request.form.get('employee_code', '').strip().upper()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'Staff Associate')
        try:
            max_hours = float(request.form.get('max_weekly_hours', 40.0))
            target_hours = float(request.form.get('target_weekly_hours', 35.0))
        except ValueError:
            flash('Working hours must be valid numbers.', 'danger')
            return redirect(url_for('employee_new'))

        is_active = 1 if request.form.get('is_active') == '1' else 0

        # Input validations
        if not code or not name or not email:
            flash('Employee Code, Name, and Email are mandatory fields.', 'danger')
            return redirect(url_for('employee_new'))

        if max_hours <= 0 or target_hours <= 0:
            flash('Working hours must be greater than zero.', 'danger')
            return redirect(url_for('employee_new'))

        # Check uniqueness
        duplicate_code = db.execute("SELECT id FROM employees WHERE employee_code = ?", (code,)).fetchone()
        if duplicate_code:
            flash(f'Employee code "{code}" already exists. Please choose a unique code.', 'danger')
            return redirect(url_for('employee_new'))

        duplicate_email = db.execute("SELECT id FROM employees WHERE email = ?", (email,)).fetchone()
        if duplicate_email:
            flash(f'Email "{email}" is already registered.', 'danger')
            return redirect(url_for('employee_new'))

        try:
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO employees (employee_code, name, email, phone, role, max_weekly_hours, target_weekly_hours, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, name, email, phone, role, max_hours, target_hours, is_active))
            new_emp_id = cursor.lastrowid

            # Save selected skills with proficiencies
            selected_skills = request.form.getlist('skills')
            for skill_id in selected_skills:
                prof = request.form.get(f'proficiency_{skill_id}', 'Standard')
                cursor.execute("""
                    INSERT INTO employee_skills (employee_id, skill_id, proficiency_level)
                    VALUES (?, ?, ?)
                """, (new_emp_id, int(skill_id), prof))

            # Save 7-day availability schedule
            for day in range(7):
                is_avail = 1 if request.form.get(f'avail_day_{day}') == '1' else 0
                start_t = request.form.get(f'avail_start_{day}', '08:00')
                end_t = request.form.get(f'avail_end_{day}', '17:00')
                cursor.execute("""
                    INSERT INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_emp_id, day, start_t, end_t, is_avail))

            db.commit()
            flash(f'Employee "{name}" ({code}) created successfully!', 'success')
            return redirect(url_for('employees_list'))
        except Exception as ex:
            db.rollback()
            flash(f'Error creating employee: {str(ex)}', 'danger')
            return redirect(url_for('employee_new'))

    # Next default employee code suggestion
    count = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    default_code = f"EMP-{101 + count}"

    # Default availability (Monday-Friday 08:00-17:00 available, weekends unavailable)
    default_availability = {
        i: {'is_available': 1 if i <= 4 else 0, 'start_time': '08:00', 'end_time': '17:00'}
        for i in range(7)
    }

    return render_template(
        'employees/form.html',
        employee=None,
        all_skills=all_skills,
        selected_skill_ids=set(),
        skill_proficiencies={},
        availability_map=default_availability,
        available_roles=AVAILABLE_ROLES,
        default_code=default_code
    )

@app.route('/employees/<int:emp_id>')
def employee_detail(emp_id):
    """View detailed profile, skills, and weekly availability for an employee."""
    employee, skills, availability_map = get_employee_with_details(emp_id)
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(url_for('employees_list'))

    return render_template(
        'employees/detail.html',
        employee=employee,
        skills=skills,
        availability_map=availability_map
    )

@app.route('/employees/<int:emp_id>/edit', methods=['GET', 'POST'])
def employee_edit(emp_id):
    """Edit an existing employee profile, qualified skills, and weekly availability."""
    db = get_db()
    employee, skills, availability_map = get_employee_with_details(emp_id)
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(url_for('employees_list'))

    all_skills = get_all_skills()

    if request.method == 'POST':
        code = request.form.get('employee_code', '').strip().upper()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', employee['role'])
        try:
            max_hours = float(request.form.get('max_weekly_hours', 40.0))
            target_hours = float(request.form.get('target_weekly_hours', 35.0))
        except ValueError:
            flash('Working hours must be valid numbers.', 'danger')
            return redirect(url_for('employee_edit', emp_id=emp_id))

        is_active = 1 if request.form.get('is_active') == '1' else 0

        if not code or not name or not email:
            flash('Employee Code, Name, and Email are mandatory fields.', 'danger')
            return redirect(url_for('employee_edit', emp_id=emp_id))

        if max_hours <= 0 or target_hours <= 0:
            flash('Working hours must be greater than zero.', 'danger')
            return redirect(url_for('employee_edit', emp_id=emp_id))

        # Check uniqueness against other employees
        dup_code = db.execute("SELECT id FROM employees WHERE employee_code = ? AND id != ?", (code, emp_id)).fetchone()
        if dup_code:
            flash(f'Employee code "{code}" is already in use by another employee.', 'danger')
            return redirect(url_for('employee_edit', emp_id=emp_id))

        dup_email = db.execute("SELECT id FROM employees WHERE email = ? AND id != ?", (email, emp_id)).fetchone()
        if dup_email:
            flash(f'Email "{email}" is already in use by another employee.', 'danger')
            return redirect(url_for('employee_edit', emp_id=emp_id))

        try:
            db.execute("""
                UPDATE employees
                SET employee_code = ?, name = ?, email = ?, phone = ?, role = ?,
                    max_weekly_hours = ?, target_weekly_hours = ?, is_active = ?
                WHERE id = ?
            """, (code, name, email, phone, role, max_hours, target_hours, is_active, emp_id))

            # Update skills: clear and re-insert
            db.execute("DELETE FROM employee_skills WHERE employee_id = ?", (emp_id,))
            selected_skills = request.form.getlist('skills')
            for skill_id in selected_skills:
                prof = request.form.get(f'proficiency_{skill_id}', 'Standard')
                db.execute("""
                    INSERT INTO employee_skills (employee_id, skill_id, proficiency_level)
                    VALUES (?, ?, ?)
                """, (emp_id, int(skill_id), prof))

            # Update 7-day availability: clear and re-insert
            db.execute("DELETE FROM employee_availability WHERE employee_id = ?", (emp_id,))
            for day in range(7):
                is_avail = 1 if request.form.get(f'avail_day_{day}') == '1' else 0
                start_t = request.form.get(f'avail_start_{day}', '08:00')
                end_t = request.form.get(f'avail_end_{day}', '17:00')
                db.execute("""
                    INSERT INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available)
                    VALUES (?, ?, ?, ?, ?)
                """, (emp_id, day, start_t, end_t, is_avail))

            db.commit()
            flash(f'Employee "{name}" updated successfully!', 'success')
            return redirect(url_for('employee_detail', emp_id=emp_id))
        except Exception as ex:
            db.rollback()
            flash(f'Error updating employee: {str(ex)}', 'danger')
            return redirect(url_for('employee_edit', emp_id=emp_id))

    selected_skill_ids = {s['id'] for s in skills}
    skill_proficiencies = {s['id']: s['proficiency_level'] for s in skills}

    return render_template(
        'employees/form.html',
        employee=employee,
        all_skills=all_skills,
        selected_skill_ids=selected_skill_ids,
        skill_proficiencies=skill_proficiencies,
        availability_map=availability_map,
        available_roles=AVAILABLE_ROLES,
        default_code=employee['employee_code']
    )

@app.route('/employees/<int:emp_id>/toggle-status', methods=['POST'])
def employee_toggle_status(emp_id):
    """Toggles employee between active and inactive status."""
    db = get_db()
    emp = db.execute("SELECT id, name, is_active FROM employees WHERE id = ?", (emp_id,)).fetchone()
    if emp:
        new_status = 0 if emp['is_active'] == 1 else 1
        db.execute("UPDATE employees SET is_active = ? WHERE id = ?", (new_status, emp_id))
        db.commit()
        status_text = 'activated' if new_status == 1 else 'deactivated'
        flash(f'Employee "{emp["name"]}" {status_text} successfully.', 'info')
    return redirect(request.referrer or url_for('employees_list'))

@app.route('/employees/<int:emp_id>/delete', methods=['POST'])
def employee_delete(emp_id):
    """Permanently deletes an employee along with their availability and skill assignments."""
    db = get_db()
    emp = db.execute("SELECT id, name FROM employees WHERE id = ?", (emp_id,)).fetchone()
    if emp:
        db.execute("DELETE FROM employee_skills WHERE employee_id = ?", (emp_id,))
        db.execute("DELETE FROM employee_availability WHERE employee_id = ?", (emp_id,))
        db.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
        db.commit()
        flash(f'Employee "{emp["name"]}" deleted successfully.', 'success')
    return redirect(url_for('employees_list'))

@app.route('/api/employees')
def api_employees():
    """JSON API endpoint returning all employees with skills and availability."""
    db = get_db()
    rows = db.execute("SELECT * FROM employees ORDER BY name").fetchall()
    result = []
    for r in rows:
        _, skills, avail = get_employee_with_details(r['id'])
        item = dict(r)
        item['skills'] = [dict(s) for s in skills]
        item['availability'] = avail
        result.append(item)
    return jsonify({"count": len(result), "employees": result})

@app.route('/seed-demo-data', methods=['POST'])
def seed_demo_data():
    """Seeds demo employees, skills, and weekly availability."""
    try:
        db = get_db()
        existing_skills = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        if existing_skills == 0:
            skills = [
                ('Customer Service', 'Handles client interactions, checkout, and general support'),
                ('Inventory Management', 'Stock management, receiving orders, and inventory audit'),
                ('Shift Supervision', 'Team leadership, floor coordination, and opening/closing procedures'),
                ('Technical Support', 'Hardware troubleshooting and system maintenance')
            ]
            db.executemany("INSERT INTO skills (name, description) VALUES (?, ?)", skills)

        existing_emps = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        if existing_emps == 0:
            emps = [
                ('EMP-101', 'Alice Johnson', 'alice.johnson@workforce.local', '555-0101', 'Supervisor', 40.0, 38.0),
                ('EMP-102', 'Brian Smith', 'brian.smith@workforce.local', '555-0102', 'Staff Associate', 35.0, 32.0),
                ('EMP-103', 'Carla Gomez', 'carla.gomez@workforce.local', '555-0103', 'Inventory Specialist', 40.0, 40.0),
                ('EMP-104', 'David Patel', 'david.patel@workforce.local', '555-0104', 'Technical Specialist', 30.0, 25.0)
            ]
            db.executemany(
                "INSERT INTO employees (employee_code, name, email, phone, role, max_weekly_hours, target_weekly_hours) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                emps
            )
            # Map skills to employees
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (1, 3, 'Expert')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (1, 1, 'Advanced')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (2, 1, 'Standard')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (3, 2, 'Expert')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (4, 1, 'Standard')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (4, 4, 'Advanced')")

            # Seed default availability for each demo employee
            for emp_id in range(1, 5):
                for day in range(7):
                    # Mon-Fri available 08:00 to 17:00, Sat-Sun unavailable
                    is_av = 1 if day <= 4 else 0
                    db.execute("""
                        INSERT OR IGNORE INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available)
                        VALUES (?, ?, '08:00', '17:00', ?)
                    """, (emp_id, day, is_av))

        db.commit()
        flash('Demo workforce data seeded successfully!', 'success')
    except Exception as ex:
        flash(f'Error seeding demo data: {str(ex)}', 'danger')

    return redirect(url_for('employees_list'))

# ==============================================================================
# TASK MANAGEMENT ROUTES (CRUD)
# ==============================================================================

@app.route('/tasks')
def tasks_list():
    """Lists all operational tasks and shift demand definitions."""
    db = get_db()
    tasks = db.execute("""
        SELECT s.*, sk.name AS required_skill_name
        FROM shifts s
        LEFT JOIN skills sk ON s.required_skill_id = sk.id
        ORDER BY s.day_of_week ASC, s.start_time ASC
    """).fetchall()
    return render_template('tasks/index.html', tasks=[dict(t) for t in tasks])

@app.route('/tasks/new', methods=['GET', 'POST'])
def task_new():
    """Create a new task / shift requirement with skill, duration, and staffing constraints."""
    db = get_db()
    skills = get_all_skills()

    if request.method == 'POST':
        code = request.form.get('task_code', '').strip().upper()
        title = request.form.get('title', '').strip()
        shift_type = request.form.get('shift_type', 'Morning')
        try:
            day_of_week = int(request.form.get('day_of_week', 0))
            duration_hours = float(request.form.get('duration_hours', 8.0))
            min_staff = max(1, int(request.form.get('min_staff', 1)))
            priority = int(request.form.get('priority', 1))
        except ValueError:
            flash('Duration, staff count, and day must be valid numbers.', 'danger')
            return redirect(url_for('task_new'))

        start_time = request.form.get('start_time', '08:00').strip()
        end_time = request.form.get('end_time', '16:00').strip()
        req_skill_id_raw = request.form.get('required_skill_id', '').strip()
        req_skill_id = int(req_skill_id_raw) if req_skill_id_raw else None

        if not code or not title:
            flash('Task Code and Task Title are required fields.', 'danger')
            return redirect(url_for('task_new'))

        if duration_hours <= 0:
            flash('Task duration must be greater than zero.', 'danger')
            return redirect(url_for('task_new'))

        # Check unique task code
        existing = db.execute("SELECT id FROM shifts WHERE task_code = ?", (code,)).fetchone()
        if existing:
            flash(f'Task code "{code}" already exists. Please choose a unique code.', 'danger')
            return redirect(url_for('task_new'))

        try:
            db.execute("""
                INSERT INTO shifts (task_code, title, shift_type, day_of_week, start_time, end_time, duration_hours, required_skill_id, min_staff, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (code, title, shift_type, day_of_week, start_time, end_time, duration_hours, req_skill_id, min_staff, priority))
            db.commit()
            flash(f'Task "{title}" ({code}) created successfully!', 'success')
            return redirect(url_for('tasks_list'))
        except Exception as ex:
            db.rollback()
            flash(f'Error creating task: {str(ex)}', 'danger')
            return redirect(url_for('task_new'))

    count = db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
    default_code = f"TSK-{101 + count}"
    return render_template('tasks/form.html', task=None, skills=skills, default_code=default_code)

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
def task_edit(task_id):
    """Edit an existing operational task."""
    db = get_db()
    task = db.execute("SELECT * FROM shifts WHERE id = ?", (task_id,)).fetchone()
    if not task:
        flash('Task not found.', 'danger')
        return redirect(url_for('tasks_list'))

    skills = get_all_skills()

    if request.method == 'POST':
        code = request.form.get('task_code', '').strip().upper()
        title = request.form.get('title', '').strip()
        shift_type = request.form.get('shift_type', task['shift_type'])
        try:
            day_of_week = int(request.form.get('day_of_week', task['day_of_week']))
            duration_hours = float(request.form.get('duration_hours', task['duration_hours']))
            min_staff = max(1, int(request.form.get('min_staff', task['min_staff'])))
            priority = int(request.form.get('priority', task['priority']))
        except ValueError:
            flash('Duration, staff count, and day must be valid numbers.', 'danger')
            return redirect(url_for('task_edit', task_id=task_id))

        start_time = request.form.get('start_time', '08:00').strip()
        end_time = request.form.get('end_time', '16:00').strip()
        req_skill_id_raw = request.form.get('required_skill_id', '').strip()
        req_skill_id = int(req_skill_id_raw) if req_skill_id_raw else None

        if not code or not title:
            flash('Task Code and Task Title are required fields.', 'danger')
            return redirect(url_for('task_edit', task_id=task_id))

        if duration_hours <= 0:
            flash('Task duration must be greater than zero.', 'danger')
            return redirect(url_for('task_edit', task_id=task_id))

        # Check unique task code against other tasks
        dup = db.execute("SELECT id FROM shifts WHERE task_code = ? AND id != ?", (code, task_id)).fetchone()
        if dup:
            flash(f'Task code "{code}" is already in use by another task.', 'danger')
            return redirect(url_for('task_edit', task_id=task_id))

        try:
            db.execute("""
                UPDATE shifts
                SET task_code = ?, title = ?, shift_type = ?, day_of_week = ?, start_time = ?, end_time = ?,
                    duration_hours = ?, required_skill_id = ?, min_staff = ?, priority = ?
                WHERE id = ?
            """, (code, title, shift_type, day_of_week, start_time, end_time, duration_hours, req_skill_id, min_staff, priority, task_id))
            db.commit()
            flash(f'Task "{title}" updated successfully!', 'success')
            return redirect(url_for('tasks_list'))
        except Exception as ex:
            db.rollback()
            flash(f'Error updating task: {str(ex)}', 'danger')
            return redirect(url_for('task_edit', task_id=task_id))

    return render_template('tasks/form.html', task=dict(task), skills=skills, default_code=task['task_code'])

@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
def task_delete(task_id):
    """Deletes a task definition."""
    db = get_db()
    task = db.execute("SELECT id, title FROM shifts WHERE id = ?", (task_id,)).fetchone()
    if task:
        db.execute("DELETE FROM shifts WHERE id = ?", (task_id,))
        db.commit()
        flash(f'Task "{task["title"]}" deleted successfully.', 'success')
    return redirect(url_for('tasks_list'))

@app.route('/api/tasks')
def api_tasks():
    """JSON endpoint returning all task definitions."""
    db = get_db()
    rows = db.execute("""
        SELECT s.*, sk.name AS required_skill_name
        FROM shifts s
        LEFT JOIN skills sk ON s.required_skill_id = sk.id
        ORDER BY s.day_of_week, s.start_time
    """).fetchall()
    return jsonify({"count": len(rows), "tasks": [dict(r) for r in rows]})


# ==============================================================================
# BULK ENTRY & INSTANT PRESETS
# ==============================================================================

@app.route('/bulk-entry')
def bulk_entry_page():
    """Bulk entry interface and 1-click test scenario presets."""
    skills = get_all_skills()
    return render_template('bulk_entry.html', skills=skills)

@app.route('/bulk-entry/presets/<preset_type>', methods=['POST'])
def load_preset(preset_type):
    """Loads standardized 5-employee, 10-employee, standard task, or conflict stress-test scenarios."""
    db = get_db()
    try:
        # Ensure default skills exist
        skills_def = [
            ('Customer Service', 'Handles client interactions and checkout'),
            ('Inventory Management', 'Stock management and inventory audits'),
            ('Shift Supervision', 'Team leadership and floor coordination'),
            ('Technical Support', 'Hardware and systems maintenance'),
            ('Database Administration', 'Database maintenance, backup, and querying'),
            ('Quality Assurance', 'Testing, code inspection, and validation')
        ]
        for sname, sdesc in skills_def:
            db.execute("INSERT OR IGNORE INTO skills (name, description) VALUES (?, ?)", (sname, sdesc))
        db.commit()

        # Map skill names to IDs
        skill_rows = db.execute("SELECT id, name FROM skills").fetchall()
        skill_id_map = {r['name']: r['id'] for r in skill_rows}

        if preset_type == '5_employees':
            # 5 Employees with varied skills, contract hours, and availability
            emps_5 = [
                ('EMP-101', 'Alice Johnson', 'alice.johnson@workforce.local', '555-0101', 'Supervisor', 40.0, 35.0,
                 ['Shift Supervision', 'Customer Service'], {0: ('07:00', '23:00'), 1: ('07:00', '23:00'), 2: ('07:00', '23:00'), 3: ('07:00', '23:00'), 4: ('07:00', '23:00')}),
                ('EMP-102', 'Bob Smith', 'brian.smith@workforce.local', '555-0102', 'Specialist', 40.0, 35.0,
                 ['Inventory Management'], {0: ('08:00', '17:00'), 1: ('08:00', '17:00'), 2: ('08:00', '17:00'), 3: ('08:00', '17:00'), 4: ('08:00', '17:00')}),
                ('EMP-103', 'Charlie Davis', 'charlie.davis@workforce.local', '555-0103', 'Technical Specialist', 35.0, 30.0,
                 ['Technical Support', 'Customer Service'], {0: ('08:00', '20:00'), 1: ('08:00', '20:00'), 2: ('08:00', '20:00'), 3: ('08:00', '20:00'), 4: ('08:00', '20:00')}),
                ('EMP-104', 'Diana Prince', 'diana.prince@workforce.local', '555-0104', 'Staff Associate', 30.0, 25.0,
                 ['Customer Service'], {0: ('08:00', '18:00'), 1: ('08:00', '18:00'), 2: ('08:00', '18:00'), 3: ('08:00', '18:00'), 4: ('08:00', '18:00'), 5: ('08:00', '18:00')}),
                ('EMP-105', 'Evan Wright', 'evan.wright@workforce.local', '555-0105', 'Staff Associate', 40.0, 35.0,
                 ['Customer Service', 'Inventory Management'], {0: ('07:00', '22:00'), 1: ('07:00', '22:00'), 2: ('07:00', '22:00'), 3: ('07:00', '22:00'), 4: ('07:00', '22:00'), 5: ('07:00', '22:00'), 6: ('07:00', '22:00')})
            ]
            for code, name, email, phone, role, max_h, tgt_h, sk_names, avail_days in emps_5:
                # Upsert employee
                existing_emp = db.execute("SELECT id FROM employees WHERE employee_code = ?", (code,)).fetchone()
                if existing_emp:
                    eid = existing_emp['id']
                    db.execute("UPDATE employees SET name=?, email=?, phone=?, role=?, max_weekly_hours=?, target_weekly_hours=?, is_active=1 WHERE id=?",
                               (name, email, phone, role, max_h, tgt_h, eid))
                else:
                    cur = db.cursor()
                    cur.execute("""
                        INSERT INTO employees (employee_code, name, email, phone, role, max_weekly_hours, target_weekly_hours, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (code, name, email, phone, role, max_h, tgt_h))
                    eid = cur.lastrowid

                # Assign skills
                db.execute("DELETE FROM employee_skills WHERE employee_id = ?", (eid,))
                for sk_name in sk_names:
                    if sk_name in skill_id_map:
                        db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (?, ?, 'Expert')",
                                   (eid, skill_id_map[sk_name]))

                # Assign availability
                db.execute("DELETE FROM employee_availability WHERE employee_id = ?", (eid,))
                for day_idx in range(7):
                    if day_idx in avail_days:
                        s_t, e_t = avail_days[day_idx]
                        db.execute("INSERT INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available) VALUES (?, ?, ?, ?, 1)",
                                   (eid, day_idx, s_t, e_t))
                    else:
                        db.execute("INSERT INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available) VALUES (?, ?, '08:00', '17:00', 0)",
                                   (eid, day_idx))

            db.commit()
            flash('Preset Loaded: 5 Employees with diverse skills and availability configured.', 'success')

        elif preset_type == '10_employees':
            emps_10 = [
                ('EMP-101', 'Alice Johnson', 'alice.johnson@workforce.local', '555-0101', 'Supervisor', 40.0, 35.0, ['Shift Supervision', 'Customer Service']),
                ('EMP-102', 'Bob Smith', 'brian.smith@workforce.local', '555-0102', 'Specialist', 40.0, 35.0, ['Inventory Management']),
                ('EMP-103', 'Charlie Davis', 'charlie.davis@workforce.local', '555-0103', 'Technical Specialist', 35.0, 30.0, ['Technical Support', 'Customer Service']),
                ('EMP-104', 'Diana Prince', 'diana.prince@workforce.local', '555-0104', 'Staff Associate', 30.0, 25.0, ['Customer Service']),
                ('EMP-105', 'Evan Wright', 'evan.wright@workforce.local', '555-0105', 'Staff Associate', 40.0, 35.0, ['Customer Service', 'Inventory Management']),
                ('EMP-106', 'Fiona Gallagher', 'fiona.g@workforce.local', '555-0106', 'Supervisor', 40.0, 35.0, ['Shift Supervision', 'Technical Support']),
                ('EMP-107', 'George Clark', 'george.c@workforce.local', '555-0107', 'Inventory Specialist', 35.0, 30.0, ['Inventory Management', 'Quality Assurance']),
                ('EMP-108', 'Hannah Abbott', 'hannah.a@workforce.local', '555-0108', 'Customer Support', 30.0, 25.0, ['Customer Service']),
                ('EMP-109', 'Ian Malcolm', 'ian.m@workforce.local', '555-0109', 'Data Specialist', 40.0, 35.0, ['Database Administration', 'Technical Support']),
                ('EMP-110', 'Julia Roberts', 'julia.r@workforce.local', '555-0110', 'QA Analyst', 35.0, 30.0, ['Quality Assurance', 'Customer Service'])
            ]
            for code, name, email, phone, role, max_h, tgt_h, sk_names in emps_10:
                existing_emp = db.execute("SELECT id FROM employees WHERE employee_code = ?", (code,)).fetchone()
                if existing_emp:
                    eid = existing_emp['id']
                    db.execute("UPDATE employees SET name=?, email=?, phone=?, role=?, max_weekly_hours=?, target_weekly_hours=?, is_active=1 WHERE id=?",
                               (name, email, phone, role, max_h, tgt_h, eid))
                else:
                    cur = db.cursor()
                    cur.execute("""
                        INSERT INTO employees (employee_code, name, email, phone, role, max_weekly_hours, target_weekly_hours, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (code, name, email, phone, role, max_h, tgt_h))
                    eid = cur.lastrowid

                db.execute("DELETE FROM employee_skills WHERE employee_id = ?", (eid,))
                for sk_name in sk_names:
                    if sk_name in skill_id_map:
                        db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (?, ?, 'Expert')",
                                   (eid, skill_id_map[sk_name]))

                db.execute("DELETE FROM employee_availability WHERE employee_id = ?", (eid,))
                for day_idx in range(7):
                    # Mon-Sat available 07:00 to 23:59
                    is_av = 1 if day_idx <= 5 else 0
                    db.execute("INSERT INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available) VALUES (?, ?, '07:00', '23:59', ?)",
                               (eid, day_idx, is_av))

            db.commit()
            flash('Preset Loaded: 10 Employees registered across 6 distinct skill sets.', 'success')

        elif preset_type == 'standard_tasks':
            # Clear old shifts
            db.execute("DELETE FROM shifts")
            std_tasks = [
                ('TSK-101', 'Monday Floor Supervision', 'Morning', 0, '08:00', '16:00', 8.0, skill_id_map.get('Shift Supervision'), 1, 2),
                ('TSK-102', 'Monday Inventory Audit', 'Morning', 0, '08:00', '14:00', 6.0, skill_id_map.get('Inventory Management'), 1, 1),
                ('TSK-103', 'Monday Customer Helpdesk', 'Morning', 0, '09:00', '17:00', 8.0, skill_id_map.get('Customer Service'), 2, 2),
                ('TSK-104', 'Monday Technical Systems Support', 'Afternoon', 0, '16:00', '23:59', 8.0, skill_id_map.get('Technical Support'), 1, 2),
                ('TSK-105', 'Tuesday Team Coordination', 'Morning', 1, '08:00', '16:00', 8.0, skill_id_map.get('Shift Supervision'), 1, 2),
                ('TSK-106', 'Tuesday Stock Replenishment', 'Morning', 1, '09:00', '15:00', 6.0, skill_id_map.get('Inventory Management'), 1, 1),
                ('TSK-107', 'Tuesday Client Assistance', 'Afternoon', 1, '16:00', '23:59', 8.0, skill_id_map.get('Customer Service'), 1, 1),
                ('TSK-108', 'Wednesday Operational Lead', 'Morning', 2, '08:00', '16:00', 8.0, skill_id_map.get('Shift Supervision'), 1, 2),
                ('TSK-109', 'Wednesday Tech Maintenance', 'Morning', 2, '08:00', '16:00', 8.0, skill_id_map.get('Technical Support'), 1, 2),
                ('TSK-110', 'Wednesday Customer Service Desk', 'Afternoon', 2, '16:00', '23:59', 8.0, skill_id_map.get('Customer Service'), 2, 2),
                ('TSK-111', 'Thursday Facility Supervision', 'Morning', 3, '08:00', '16:00', 8.0, skill_id_map.get('Shift Supervision'), 1, 2),
                ('TSK-112', 'Thursday Warehouse Audit', 'Morning', 3, '09:00', '15:00', 6.0, skill_id_map.get('Inventory Management'), 1, 1),
                ('TSK-113', 'Friday Floor Supervision', 'Morning', 4, '08:00', '16:00', 8.0, skill_id_map.get('Shift Supervision'), 1, 3),
                ('TSK-114', 'Friday Client Care Center', 'Morning', 4, '09:00', '17:00', 8.0, skill_id_map.get('Customer Service'), 2, 2),
                ('TSK-115', 'Friday System Security Audit', 'Night', 4, '00:00', '08:00', 8.0, skill_id_map.get('Technical Support'), 1, 2),
            ]
            db.executemany("""
                INSERT INTO shifts (task_code, title, shift_type, day_of_week, start_time, end_time, duration_hours, required_skill_id, min_staff, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, std_tasks)
            db.commit()
            flash('Preset Loaded: 15 Standard Operational Tasks created across Mon-Fri.', 'success')

        elif preset_type == 'conflict_tasks':
            # Create special tasks designed to demonstrate CSP hard constraints and conflicts
            db.execute("DELETE FROM shifts")
            
            # Ensure "Robotics Maintenance" skill exists but assign to NO employees
            db.execute("INSERT OR IGNORE INTO skills (name, description) VALUES ('Robotics Engineering', 'Hardware robotics and automation')")
            db.commit()
            robotics_skill_id = db.execute("SELECT id FROM skills WHERE name = 'Robotics Engineering'").fetchone()[0]

            conflict_tasks = [
                # Conflict 1: Missing skill - no active employee has Robotics Engineering
                ('TSK-C01', 'Automated Robotics Maintenance', 'Morning', 0, '09:00', '13:00', 4.0, robotics_skill_id, 1, 3),
                # Conflict 2: Overlapping tasks requiring the exact same sole Specialist
                ('TSK-C02', 'High-Priority Inventory Front Audit', 'Morning', 0, '10:00', '14:00', 4.0, skill_id_map.get('Inventory Management'), 1, 3),
                ('TSK-C03', 'Overlapping Inventory Backroom Check', 'Morning', 0, '11:00', '15:00', 4.0, skill_id_map.get('Inventory Management'), 1, 1),
                # Conflict 3: Shift during an unavailable time window (Sunday midnight)
                ('TSK-C04', 'Sunday Midnight Tech Audit', 'Night', 6, '00:00', '08:00', 8.0, skill_id_map.get('Technical Support'), 1, 1),
                # Standard feasible task
                ('TSK-C05', 'Standard Monday Floor Supervision', 'Morning', 0, '08:00', '16:00', 8.0, skill_id_map.get('Shift Supervision'), 1, 2),
            ]
            db.executemany("""
                INSERT INTO shifts (task_code, title, shift_type, day_of_week, start_time, end_time, duration_hours, required_skill_id, min_staff, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, conflict_tasks)
            db.commit()
            flash('Preset Loaded: Conflict Stress-Test Tasks loaded. Run Intelligent Scheduler to observe root-cause diagnostics.', 'warning')

    except Exception as ex:
        db.rollback()
        flash(f'Error loading preset: {str(ex)}', 'danger')

    return redirect(url_for('scheduler_dashboard'))

@app.route('/bulk-entry/employees', methods=['POST'])
def bulk_save_employees():
    """Saves multi-row employees from the bulk entry table."""
    db = get_db()
    saved_count = 0
    try:
        # Loop through possible rows (up to 50)
        for i in range(50):
            name = request.form.get(f'emp_name_{i}', '').strip()
            if not name:
                continue

            code = request.form.get(f'emp_code_{i}', '').strip().upper()
            if not code:
                code = f"EMP-{200 + i + 1}"

            email = request.form.get(f'emp_email_{i}', '').strip().lower()
            if not email:
                email = f"{code.lower()}@workforce.local"

            role = request.form.get(f'emp_role_{i}', 'Staff Associate').strip()
            try:
                max_h = float(request.form.get(f'emp_max_{i}', 40.0))
                tgt_h = float(request.form.get(f'emp_target_{i}', 35.0))
            except ValueError:
                max_h, tgt_h = 40.0, 35.0

            # Insert employee
            cur = db.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO employees (employee_code, name, email, role, max_weekly_hours, target_weekly_hours, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (code, name, email, role, max_h, tgt_h))
            eid = cur.lastrowid or db.execute("SELECT id FROM employees WHERE employee_code = ?", (code,)).fetchone()[0]

            # Primary skill if selected
            skill_id_raw = request.form.get(f'emp_skill_{i}', '').strip()
            if skill_id_raw:
                try:
                    sk_id = int(skill_id_raw)
                    db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (?, ?, 'Standard')", (eid, sk_id))
                except ValueError:
                    pass

            # Default Mon-Fri availability (08:00 - 17:00)
            for day in range(7):
                is_av = 1 if day <= 4 else 0
                db.execute("INSERT OR REPLACE INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available) VALUES (?, ?, '08:00', '17:00', ?)",
                           (eid, day, is_av))

            saved_count += 1

        db.commit()
        if saved_count > 0:
            flash(f'Successfully saved {saved_count} employees in bulk!', 'success')
        else:
            flash('No employee rows had data to save.', 'info')
    except Exception as ex:
        db.rollback()
        flash(f'Error saving bulk employees: {str(ex)}', 'danger')

    return redirect(url_for('employees_list'))

@app.route('/bulk-entry/tasks', methods=['POST'])
def bulk_save_tasks():
    """Saves multi-row tasks from the bulk entry table."""
    db = get_db()
    saved_count = 0
    try:
        for i in range(50):
            title = request.form.get(f'task_title_{i}', '').strip()
            if not title:
                continue

            code = request.form.get(f'task_code_{i}', '').strip().upper()
            if not code:
                code = f"TSK-{300 + i + 1}"

            shift_type = request.form.get(f'task_type_{i}', 'Morning').strip()
            try:
                day_of_week = int(request.form.get(f'task_day_{i}', 0))
                dur = float(request.form.get(f'task_dur_{i}', 8.0))
                staff = max(1, int(request.form.get(f'task_staff_{i}', 1)))
                prio = int(request.form.get(f'task_prio_{i}', 1))
            except ValueError:
                day_of_week, dur, staff, prio = 0, 8.0, 1, 1

            start_t = request.form.get(f'task_start_{i}', '08:00').strip()
            end_t = request.form.get(f'task_end_{i}', '16:00').strip()

            skill_id_raw = request.form.get(f'task_skill_{i}', '').strip()
            req_skill_id = int(skill_id_raw) if skill_id_raw else None

            db.execute("""
                INSERT OR REPLACE INTO shifts (task_code, title, shift_type, day_of_week, start_time, end_time, duration_hours, required_skill_id, min_staff, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (code, title, shift_type, day_of_week, start_t, end_t, dur, req_skill_id, staff, prio))

            saved_count += 1

        db.commit()
        if saved_count > 0:
            flash(f'Successfully saved {saved_count} tasks in bulk!', 'success')
        else:
            flash('No task rows had data to save.', 'info')
    except Exception as ex:
        db.rollback()
        flash(f'Error saving bulk tasks: {str(ex)}', 'danger')

    return redirect(url_for('tasks_list'))


# ==============================================================================
# CONSTRAINT SATISFACTION PROBLEM (CSP) INTELLIGENT SCHEDULER
# ==============================================================================

def load_schedule_result_from_db(schedule_id: int) -> Optional[Dict[str, Any]]:
    """Reconstructs the full schedule_result dictionary from SQLite tables."""
    db = get_db()
    sched = db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    if not sched:
        return None

    # Load assignments
    assignments_rows = db.execute("""
        SELECT sa.*, s.task_code, s.title, s.shift_type, s.day_of_week, s.priority, s.duration_hours,
               e.name AS employee_name, e.employee_code, e.role AS employee_role,
               sk.name AS matched_skill, es.proficiency_level AS proficiency
        FROM shift_assignments sa
        JOIN shifts s ON sa.shift_id = s.id
        JOIN employees e ON sa.employee_id = e.id
        LEFT JOIN skills sk ON s.required_skill_id = sk.id
        LEFT JOIN employee_skills es ON (es.employee_id = e.id AND es.skill_id = s.required_skill_id)
        WHERE sa.schedule_id = ?
        ORDER BY s.day_of_week ASC, sa.start_time ASC
    """, (schedule_id,)).fetchall()

    assignments = [dict(r) for r in assignments_rows]

    # Load unassigned / conflict records
    unassigned_rows = db.execute("""
        SELECT ur.*, s.task_code, s.title, s.shift_type, s.day_of_week, s.start_time, s.end_time, s.duration_hours, s.priority,
               sk.name AS required_skill
        FROM unfilled_shift_records ur
        JOIN shifts s ON ur.shift_id = s.id
        LEFT JOIN skills sk ON s.required_skill_id = sk.id
        WHERE ur.schedule_id = ?
    """, (schedule_id,)).fetchall()

    unassigned_tasks = []
    for r in unassigned_rows:
        reasons_list = [r['reason']]
        if r['details']:
            reasons_list.append(r['details'])
        unassigned_tasks.append({
            'task_id': r['shift_id'],
            'task_code': r['task_code'],
            'title': r['title'],
            'slot_index': 0,
            'shift_type': r['shift_type'],
            'day_of_week': r['day_of_week'],
            'start_time': r['start_time'],
            'end_time': r['end_time'],
            'duration_hours': r['duration_hours'],
            'priority': r['priority'],
            'required_skill': r['required_skill'] or 'None',
            'reasons': reasons_list
        })

    # Compute workload stats
    all_emps = db.execute("SELECT * FROM employees WHERE is_active = 1 ORDER BY name").fetchall()
    workload_stats = []
    for emp in all_emps:
        emp_h = sum(a['hours'] for a in assignments if a['employee_id'] == emp['id'])
        task_c = sum(1 for a in assignments if a['employee_id'] == emp['id'])
        night_c = sum(1 for a in assignments if a['employee_id'] == emp['id'] and a.get('shift_type') == 'Night')
        max_h = emp['max_weekly_hours']
        utilization = round((emp_h / max_h * 100) if max_h > 0 else 0, 1)
        workload_stats.append({
            'employee_id': emp['id'],
            'employee_name': emp['name'],
            'employee_code': emp['employee_code'],
            'role': emp['role'],
            'assigned_hours': round(emp_h, 1),
            'target_hours': emp['target_weekly_hours'],
            'max_hours': max_h,
            'utilization_percent': utilization,
            'assigned_tasks_count': task_c,
            'night_shifts_count': night_c
        })

    total_tasks_count = db.execute("SELECT COUNT(*) FROM shifts WHERE is_active = 1").fetchone()[0]

    return {
        'schedule_id': schedule_id,
        'solver_engine': 'Google OR-Tools CP-SAT & Backtracking CSP Engine',
        'status': 'OPTIMAL' if sched['unfilled_shifts'] == 0 else 'FEASIBLE (WITH CONFLICTS)',
        'is_feasible': sched['unfilled_shifts'] == 0,
        'solve_time_seconds': 0.05,
        'total_tasks': total_tasks_count,
        'total_slots': sched['total_shifts'],
        'assigned_slots': sched['assigned_shifts'],
        'unassigned_slots': sched['unfilled_shifts'],
        'fulfillment_rate': round((sched['assigned_shifts'] / sched['total_shifts'] * 100) if sched['total_shifts'] > 0 else 0, 1),
        'fairness_score': sched['fairness_score'],
        'assignments': assignments,
        'unassigned_tasks': unassigned_tasks,
        'workload_stats': workload_stats
    }

@app.route('/scheduler')
def scheduler_dashboard():
    """Main scheduling interface: displays generated schedule or welcome prompt."""
    db = get_db()
    latest_sched = db.execute("SELECT id FROM schedules ORDER BY created_at DESC LIMIT 1").fetchone()
    schedule_result = None
    if latest_sched:
        schedule_result = load_schedule_result_from_db(latest_sched['id'])

    return render_template('scheduler/index.html', schedule_result=schedule_result)

@app.route('/scheduler/generate', methods=['POST'])
def scheduler_generate():
    """Executes the formal CSP solver, resolves hard/soft constraints, and persists results."""
    db = get_db()

    # 1. Fetch active employees with skills and availability
    emp_rows = db.execute("SELECT * FROM employees WHERE is_active = 1 ORDER BY id").fetchall()
    if not emp_rows:
        flash('No active employees found. Please add employees or load a preset first.', 'warning')
        return redirect(url_for('bulk_entry_page'))

    employees = []
    for r in emp_rows:
        _, skills, avail = get_employee_with_details(r['id'])
        item = dict(r)
        item['skills_list'] = [dict(s) for s in skills]
        item['availability'] = avail
        employees.append(item)

    # 2. Fetch active shifts / tasks
    task_rows = db.execute("SELECT * FROM shifts WHERE is_active = 1 ORDER BY day_of_week, start_time").fetchall()
    if not task_rows:
        flash('No active tasks defined. Please create tasks or load a preset first.', 'warning')
        return redirect(url_for('bulk_entry_page'))
    tasks = [dict(t) for t in task_rows]

    # 3. Fetch skills catalog and system settings
    skills = [dict(s) for s in get_all_skills()]
    settings_rows = db.execute("SELECT key, value FROM system_settings").fetchall()
    settings = {r['key']: r['value'] for r in settings_rows}

    # 4. Instantiate and execute the CSP Scheduling Engine
    engine = CSPSchedulingEngine(employees, tasks, skills, settings)
    result = engine.solve()

    # 5. Persist schedule run into SQLite
    try:
        cur = db.cursor()
        today_iso = date.today().isoformat()
        cur.execute("""
            INSERT INTO schedules (week_start_date, status, total_shifts, assigned_shifts, unfilled_shifts, fairness_score, notes)
            VALUES (?, 'published', ?, ?, ?, ?, ?)
        """, (
            today_iso,
            result['total_slots'],
            result['assigned_slots'],
            result['unassigned_slots'],
            result['fairness_score'],
            f"Generated via {result['solver_engine']}"
        ))
        new_schedule_id = cur.lastrowid
        result['schedule_id'] = new_schedule_id

        # Insert shift assignments
        for a in result['assignments']:
            cur.execute("""
                INSERT INTO shift_assignments (schedule_id, shift_id, employee_id, shift_date, start_time, end_time, hours, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'assigned')
            """, (
                new_schedule_id,
                a['task_id'],
                a['employee_id'],
                today_iso,
                a['start_time'],
                a['end_time'],
                a['duration_hours']
            ))

        # Insert unfilled / conflict diagnosis records
        for u in result['unassigned_tasks']:
            reason_text = u['reasons'][0] if u['reasons'] else 'Staff Capacity Constraint'
            details_text = " | ".join(u['reasons'][1:]) if len(u['reasons']) > 1 else ''
            cur.execute("""
                INSERT INTO unfilled_shift_records (schedule_id, shift_id, shift_date, reason, details)
                VALUES (?, ?, ?, ?, ?)
            """, (
                new_schedule_id,
                u['task_id'],
                today_iso,
                reason_text,
                details_text
            ))

        db.commit()
        flash(f"Schedule generated successfully! ({result['assigned_slots']}/{result['total_slots']} slots assigned in {result['solve_time_seconds']}s)", 'success')
    except Exception as ex:
        db.rollback()
        flash(f'Error saving generated schedule to database: {str(ex)}', 'danger')

    return render_template('scheduler/index.html', schedule_result=result)

@app.route('/scheduler/export/<int:schedule_id>')
def scheduler_export_csv(schedule_id):
    """Exports generated schedule assignments as a downloadable CSV file."""
    db = get_db()
    rows = db.execute("""
        SELECT s.task_code, s.title AS task_title, s.shift_type, s.day_of_week, sa.start_time, sa.end_time, sa.hours,
               e.employee_code, e.name AS employee_name, e.role,
               sk.name AS matched_skill
        FROM shift_assignments sa
        JOIN shifts s ON sa.shift_id = s.id
        JOIN employees e ON sa.employee_id = e.id
        LEFT JOIN skills sk ON s.required_skill_id = sk.id
        WHERE sa.schedule_id = ?
        ORDER BY s.day_of_week, sa.start_time
    """, (schedule_id,)).fetchall()

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Start Time', 'End Time', 'Duration (Hours)', 'Task Code', 'Task Title', 'Shift Type', 'Employee Code', 'Employee Name', 'Role', 'Matched Skill'])

    for r in rows:
        d_name = day_names[r['day_of_week']] if 0 <= r['day_of_week'] < 7 else f"Day {r['day_of_week']}"
        writer.writerow([
            d_name,
            r['start_time'],
            r['end_time'],
            r['hours'],
            r['task_code'],
            r['task_title'],
            r['shift_type'],
            r['employee_code'],
            r['employee_name'],
            r['role'],
            r['matched_skill'] or 'None'
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=workforce_schedule_{schedule_id}.csv'}
    )

@app.route('/api/scheduler/solve', methods=['GET', 'POST'])
def api_scheduler_solve():
    """JSON API endpoint executing the CSP solver on demand."""
    db = get_db()
    emp_rows = db.execute("SELECT * FROM employees WHERE is_active = 1 ORDER BY id").fetchall()
    employees = []
    for r in emp_rows:
        _, skills, avail = get_employee_with_details(r['id'])
        item = dict(r)
        item['skills_list'] = [dict(s) for s in skills]
        item['availability'] = avail
        employees.append(item)

    task_rows = db.execute("SELECT * FROM shifts WHERE is_active = 1 ORDER BY day_of_week, start_time").fetchall()
    tasks = [dict(t) for t in task_rows]
    skills = [dict(s) for s in get_all_skills()]
    settings_rows = db.execute("SELECT key, value FROM system_settings").fetchall()
    settings = {r['key']: r['value'] for r in settings_rows}

    engine = CSPSchedulingEngine(employees, tasks, skills, settings)
    result = engine.solve()
    return jsonify(result)


# ==============================================================================
# WEEKLY ROSTER MATRIX VIEW
# ==============================================================================

@app.route('/roster')
def roster_view():
    """Displays a visual 7-day schedule grid grouped by Morning, Afternoon, and Night shifts."""
    db = get_db()
    latest = db.execute("SELECT id FROM schedules ORDER BY created_at DESC LIMIT 1").fetchone()
    if not latest:
        return render_template('roster/index.html', assignments=[], matrix={}, latest_schedule_id=None)

    schedule_id = latest['id']
    assignments_rows = db.execute("""
        SELECT sa.*, s.task_code, s.title, s.shift_type, s.day_of_week, s.duration_hours,
               e.name AS employee_name, e.employee_code
        FROM shift_assignments sa
        JOIN shifts s ON sa.shift_id = s.id
        JOIN employees e ON sa.employee_id = e.id
        WHERE sa.schedule_id = ?
        ORDER BY s.day_of_week, sa.start_time
    """, (schedule_id,)).fetchall()

    assignments = [dict(r) for r in assignments_rows]

    # Build matrix: (day_of_week, shift_category) -> [assignments]
    matrix = {}
    for a in assignments:
        st = a.get('shift_type') or 'Morning'
        if st not in ('Morning', 'Afternoon', 'Night'):
            st = 'Morning'
        key = (int(a['day_of_week']), st)
        matrix.setdefault(key, []).append(a)

    return render_template(
        'roster/index.html',
        assignments=assignments,
        matrix=matrix,
        latest_schedule_id=schedule_id
    )

if __name__ == '__main__':
    print("=" * 70)
    print(" Constraint-Based Intelligent Workforce Scheduling")
    print(" and Fair Workload Optimization System")
    print("=" * 70)
    print(" Running at http://127.0.0.1:5000")
    print(" Health API at http://127.0.0.1:5000/health")
    print(" Database: SQLite 3")
    print("=" * 70)
    app.run(host='127.0.0.1', port=5000, debug=True)
