import unittest
import os
import json
import sqlite3
from pathlib import Path

import importlib.util

# Explicitly load root app.py file
ROOT_DIR = Path(__file__).resolve().parent.parent
app_py_path = ROOT_DIR / 'app.py'
spec = importlib.util.spec_from_file_location("root_app_module", str(app_py_path))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

class EmployeeManagementTestCase(unittest.TestCase):
    def setUp(self):
        """Set up test client and isolated test database."""
        self.app = app_module.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Point to an isolated test database
        self.test_db_path = Path(__file__).resolve().parent / 'test_employees.db'
        app_module.DATABASE_PATH = self.test_db_path
        
        with self.app.app_context():
            app_module.init_db()
            db = app_module.get_db()
            # Seed skills
            skills = [
                ('Customer Service', 'Handles client interactions and checkout'),
                ('Inventory Management', 'Stock management and inventory audits'),
                ('Shift Supervision', 'Team leadership and floor coordination'),
                ('Technical Support', 'Hardware and systems maintenance')
            ]
            db.executemany("INSERT OR IGNORE INTO skills (name, description) VALUES (?, ?)", skills)
            db.commit()

    def tearDown(self):
        """Clean up test database."""
        if self.test_db_path.exists():
            try:
                os.remove(self.test_db_path)
            except PermissionError:
                pass

    def test_employee_directory_empty_or_listed(self):
        """Verify the employee directory route returns 200."""
        response = self.client.get('/employees')
        self.assertEqual(response.status_code, 200)
        self.assertIn("Employee Directory", response.data.decode('utf-8'))

    def test_create_employee_with_skills_and_availability(self):
        """Test creating an employee with skills and 7-day availability matrix."""
        form_data = {
            'employee_code': 'EMP-201',
            'name': 'Sarah Connor',
            'email': 'sarah.connor@workforce.local',
            'phone': '555-9001',
            'role': 'Supervisor',
            'max_weekly_hours': '40.0',
            'target_weekly_hours': '36.0',
            'is_active': '1',
            'skills': ['1', '3'],  # Customer Service & Shift Supervision
            'proficiency_1': 'Standard',
            'proficiency_3': 'Expert',
            'avail_day_0': '1',
            'avail_start_0': '08:00',
            'avail_end_0': '16:00',
            'avail_day_1': '1',
            'avail_start_1': '08:00',
            'avail_end_1': '16:00',
            'avail_day_2': '1',
            'avail_start_2': '08:00',
            'avail_end_2': '16:00',
            'avail_day_3': '1',
            'avail_start_3': '08:00',
            'avail_end_3': '16:00',
            'avail_day_4': '1',
            'avail_start_4': '08:00',
            'avail_end_4': '16:00',
            # Day 5 and 6 left unchecked (unavailable)
        }
        response = self.client.post('/employees/new', data=form_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn("Sarah Connor", content)
        self.assertIn("EMP-201", content)

        # Verify DB records
        with self.app.app_context():
            db = app_module.get_db()
            emp = db.execute("SELECT * FROM employees WHERE employee_code = 'EMP-201'").fetchone()
            self.assertIsNotNone(emp)
            self.assertEqual(emp['name'], 'Sarah Connor')
            self.assertEqual(emp['role'], 'Supervisor')
            self.assertEqual(emp['max_weekly_hours'], 40.0)

            # Check skills
            emp_skills = db.execute("SELECT * FROM employee_skills WHERE employee_id = ?", (emp['id'],)).fetchall()
            self.assertEqual(len(emp_skills), 2)

            # Check availability
            avail_rows = db.execute("SELECT * FROM employee_availability WHERE employee_id = ? AND is_available = 1", (emp['id'],)).fetchall()
            self.assertEqual(len(avail_rows), 5)

    def test_validation_rejects_duplicate_code_and_email(self):
        """Verify unique constraints on employee_code and email are enforced."""
        form_data = {
            'employee_code': 'EMP-202',
            'name': 'John Doe',
            'email': 'john.doe@workforce.local',
            'role': 'Staff Associate',
            'max_weekly_hours': '40.0',
            'target_weekly_hours': '35.0',
            'is_active': '1'
        }
        res1 = self.client.post('/employees/new', data=form_data, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)

        # Attempt duplicate code
        form_data_dup_code = dict(form_data, email='another.email@workforce.local', name='John Two')
        res2 = self.client.post('/employees/new', data=form_data_dup_code, follow_redirects=True)
        self.assertIn("already exists", res2.data.decode('utf-8'))

        # Attempt duplicate email
        form_data_dup_email = dict(form_data, employee_code='EMP-203', name='John Three')
        res3 = self.client.post('/employees/new', data=form_data_dup_email, follow_redirects=True)
        self.assertIn("already registered", res3.data.decode('utf-8'))

    def test_validation_rejects_non_positive_hours(self):
        """Verify negative or zero hours are rejected."""
        form_data = {
            'employee_code': 'EMP-204',
            'name': 'Zero Hours',
            'email': 'zero@workforce.local',
            'role': 'Staff Associate',
            'max_weekly_hours': '0',
            'target_weekly_hours': '-5.0',
            'is_active': '1'
        }
        response = self.client.post('/employees/new', data=form_data, follow_redirects=True)
        self.assertIn("greater than zero", response.data.decode('utf-8'))

    def test_edit_employee(self):
        """Verify editing employee details, role, and max hours."""
        # Create initial employee
        with self.app.app_context():
            db = app_module.get_db()
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO employees (employee_code, name, email, role, max_weekly_hours, target_weekly_hours, is_active)
                VALUES ('EMP-205', 'Original Name', 'orig@workforce.local', 'Staff Associate', 30.0, 25.0, 1)
            """)
            emp_id = cursor.lastrowid
            db.commit()

        edit_data = {
            'employee_code': 'EMP-205',
            'name': 'Updated Name',
            'email': 'updated@workforce.local',
            'phone': '555-8888',
            'role': 'Manager',
            'max_weekly_hours': '45.0',
            'target_weekly_hours': '40.0',
            'is_active': '1',
            'skills': ['2'],
            'proficiency_2': 'Advanced',
            'avail_day_0': '1',
            'avail_start_0': '09:00',
            'avail_end_0': '18:00'
        }
        response = self.client.post(f'/employees/{emp_id}/edit', data=edit_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            db = app_module.get_db()
            updated = db.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
            self.assertEqual(updated['name'], 'Updated Name')
            self.assertEqual(updated['email'], 'updated@workforce.local')
            self.assertEqual(updated['role'], 'Manager')
            self.assertEqual(updated['max_weekly_hours'], 45.0)

    def test_toggle_status_and_delete(self):
        """Verify toggling active status and permanent deletion."""
        with self.app.app_context():
            db = app_module.get_db()
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO employees (employee_code, name, email, role, max_weekly_hours, target_weekly_hours, is_active)
                VALUES ('EMP-206', 'Temporary User', 'temp@workforce.local', 'Staff Associate', 30.0, 25.0, 1)
            """)
            emp_id = cursor.lastrowid
            db.commit()

        # Toggle to inactive
        res1 = self.client.post(f'/employees/{emp_id}/toggle-status', follow_redirects=True)
        self.assertEqual(res1.status_code, 200)
        with self.app.app_context():
            db = app_module.get_db()
            emp = db.execute("SELECT is_active FROM employees WHERE id = ?", (emp_id,)).fetchone()
            self.assertEqual(emp['is_active'], 0)

        # Delete
        res2 = self.client.post(f'/employees/{emp_id}/delete', follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        with self.app.app_context():
            db = app_module.get_db()
            deleted = db.execute("SELECT id FROM employees WHERE id = ?", (emp_id,)).fetchone()
            self.assertIsNone(deleted)

    def test_api_employees_endpoint(self):
        """Verify /api/employees returns valid JSON payload."""
        response = self.client.get('/api/employees')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('count', data)
        self.assertIn('employees', data)
        self.assertIsInstance(data['employees'], list)

if __name__ == '__main__':
    unittest.main()
