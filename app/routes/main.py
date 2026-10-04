from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from app.database import get_db, check_db_connection

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main dashboard showing system overview, constraints, and SQLite connection status."""
    db_info = check_db_connection()
    
    settings = {}
    if db_info.get("status") == "connected":
        try:
            db = get_db()
            rows = db.execute("SELECT key, value, description FROM system_settings").fetchall()
            settings = {row['key']: {'value': row['value'], 'description': row['description']} for row in rows}
        except Exception:
            settings = {}

    return render_template(
        'index.html',
        db_info=db_info,
        settings=settings
    )

@main_bp.route('/health')
def health_check():
    """API endpoint providing application and database health status."""
    db_info = check_db_connection()
    return jsonify({
        "application": "Constraint-Based Intelligent Workforce Scheduling and Fair Workload Optimization System",
        "database": db_info,
        "status": "healthy" if db_info.get("status") == "connected" else "unhealthy"
    })

@main_bp.route('/seed-demo-data', methods=['POST'])
def seed_demo_data():
    """Populates basic sample skills and employees to verify database read/write functionality."""
    try:
        db = get_db()
        # Insert sample skills if empty
        existing_skills = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        if existing_skills == 0:
            sample_skills = [
                ('Customer Service', 'Handles client interactions, checkout, and general support'),
                ('Inventory Management', 'Stock management, receiving orders, and inventory audit'),
                ('Shift Supervision', 'Team leadership, floor coordination, and opening/closing procedures'),
                ('Technical Support', 'Hardware troubleshooting and system maintenance')
            ]
            db.executemany("INSERT INTO skills (name, description) VALUES (?, ?)", sample_skills)

        # Insert sample employees if empty
        existing_emps = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        if existing_emps == 0:
            sample_employees = [
                ('EMP-101', 'Alice Johnson', 'alice.johnson@workforce.local', '555-0101', 'Supervisor', 40.0, 38.0),
                ('EMP-102', 'Brian Smith', 'brian.smith@workforce.local', '555-0102', 'Staff Associate', 35.0, 32.0),
                ('EMP-103', 'Carla Gomez', 'carla.gomez@workforce.local', '555-0103', 'Inventory Specialist', 40.0, 40.0),
                ('EMP-104', 'David Patel', 'david.patel@workforce.local', '555-0104', 'Customer Support', 30.0, 25.0)
            ]
            db.executemany(
                "INSERT INTO employees (employee_code, name, email, phone, role, max_weekly_hours, target_weekly_hours) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                sample_employees
            )

            # Map skills to employees
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (1, 3, 'Expert')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (1, 1, 'Advanced')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (2, 1, 'Standard')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (3, 2, 'Expert')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (4, 1, 'Standard')")
            db.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (4, 4, 'Advanced')")

        db.commit()
        flash('Sample workforce data loaded successfully!', 'success')
    except Exception as ex:
        flash(f'Failed to seed sample data: {str(ex)}', 'danger')

    return redirect(url_for('main.index'))
