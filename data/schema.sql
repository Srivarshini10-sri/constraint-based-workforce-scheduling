-- Workforce Scheduling and Fair Workload Optimization Database Schema
-- Target: SQLite 3

PRAGMA foreign_keys = ON;

-- System Configuration & Scheduling Constraint Parameters
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pre-populate default system settings
INSERT OR IGNORE INTO system_settings (key, value, description) VALUES
('min_rest_hours_between_shifts', '11.0', 'Mandatory minimum rest duration between consecutive shifts in hours'),
('default_max_weekly_hours', '40.0', 'Default maximum allowable working hours per employee per week'),
('max_consecutive_days', '6', 'Maximum consecutive days an employee can be assigned shifts'),
('enable_fair_workload_optimization', 'true', 'Enable variance-minimizing fair workload balancing');

-- Skills definitions
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Employees table
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

-- Mapping employees to their skills
CREATE TABLE IF NOT EXISTS employee_skills (
    employee_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    proficiency_level TEXT DEFAULT 'Standard',
    PRIMARY KEY (employee_id, skill_id),
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

-- Weekly availability rules for employees
-- day_of_week: 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
CREATE TABLE IF NOT EXISTS employee_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT NOT NULL, -- Format: HH:MM (24-hour)
    end_time TEXT NOT NULL,   -- Format: HH:MM (24-hour)
    is_available INTEGER NOT NULL DEFAULT 1, -- 1 = available, 0 = unavailable
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

-- Master task / shift templates (definitions of recurring weekly workforce tasks)
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_code TEXT,
    title TEXT NOT NULL,
    shift_type TEXT NOT NULL DEFAULT 'Morning',
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT NOT NULL, -- Format: HH:MM
    end_time TEXT NOT NULL,   -- Format: HH:MM
    duration_hours REAL NOT NULL,
    required_skill_id INTEGER,
    min_staff INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 1, -- 1 = normal, 2 = high, 3 = critical
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (required_skill_id) REFERENCES skills(id) ON DELETE SET NULL
);

-- Schedule weekly runs
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start_date TEXT NOT NULL, -- Format: YYYY-MM-DD (Monday)
    status TEXT NOT NULL DEFAULT 'draft', -- draft, published, archived
    total_shifts INTEGER DEFAULT 0,
    assigned_shifts INTEGER DEFAULT 0,
    unfilled_shifts INTEGER DEFAULT 0,
    fairness_score REAL DEFAULT 0.0, -- Gini coefficient or workload standard deviation
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual shift assignments generated for a schedule
CREATE TABLE IF NOT EXISTS shift_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL,
    shift_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL, -- Format: YYYY-MM-DD
    start_time TEXT NOT NULL, -- Format: HH:MM
    end_time TEXT NOT NULL,   -- Format: HH:MM
    hours REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'assigned',
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE,
    FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

-- Unfilled shift logs with transparent constraint explanation
CREATE TABLE IF NOT EXISTS unfilled_shift_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL,
    shift_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL,
    reason TEXT NOT NULL, -- e.g., 'SKILL_MISMATCH', 'REST_PERIOD_VIOLATION', 'MAX_HOURS_EXCEEDED', 'UNAVAILABLE'
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE,
    FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_assignments_schedule ON shift_assignments(schedule_id);
CREATE INDEX IF NOT EXISTS idx_assignments_employee ON shift_assignments(employee_id);
CREATE INDEX IF NOT EXISTS idx_assignments_date ON shift_assignments(shift_date);
CREATE INDEX IF NOT EXISTS idx_availability_emp_day ON employee_availability(employee_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_shifts_day ON shifts(day_of_week);
