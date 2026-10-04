import unittest
import os
import json
from pathlib import Path
from app import create_app
from app.database import get_db, init_db, check_db_connection

class WorkforceSchedulerTestCase(unittest.TestCase):
    def setUp(self):
        """Set up test application and isolated test database."""
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Ensure fresh schema for testing
        init_db(self.app)

    def tearDown(self):
        """Tear down test database and pop context."""
        test_db_path = self.app.config['DATABASE_PATH']
        self.app_context.pop()
        
        # Remove test database file
        if Path(test_db_path).exists():
            try:
                os.remove(test_db_path)
            except PermissionError:
                pass

    def test_database_connection_and_tables(self):
        """Verify that SQLite tables are properly initialized."""
        info = check_db_connection()
        self.assertEqual(info['status'], 'connected')
        expected_tables = {
            'system_settings',
            'skills',
            'employees',
            'employee_skills',
            'employee_availability',
            'shifts',
            'schedules',
            'shift_assignments',
            'unfilled_shift_records'
        }
        for table in expected_tables:
            self.assertIn(table, info['tables'], f"Table {table} should exist in database.")

    def test_default_system_settings_populated(self):
        """Verify system default constraints exist in database."""
        db = get_db()
        min_rest = db.execute("SELECT value FROM system_settings WHERE key = 'min_rest_hours_between_shifts'").fetchone()
        self.assertIsNotNone(min_rest)
        self.assertEqual(float(min_rest['value']), 11.0)

    def test_dashboard_route(self):
        """Verify the main dashboard returns 200 and expected markup."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn("Workforce Scheduling & Workload Optimization", content)
        self.assertIn("SQLite Connected", content)

    def test_health_check_endpoint(self):
        """Verify the health check endpoint returns 200 JSON with healthy status."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['database']['status'], 'connected')
        self.assertGreaterEqual(data['database']['table_count'], 7)

    def test_seed_demo_data(self):
        """Verify seeding demo employees and skills works cleanly."""
        response = self.client.post('/seed-demo-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        db = get_db()
        emp_count = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        skill_count = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        self.assertGreater(emp_count, 0)
        self.assertGreater(skill_count, 0)

    def test_404_page(self):
        """Verify customized 404 page for nonexistent routes."""
        response = self.client.get('/nonexistent-route-xyz')
        self.assertEqual(response.status_code, 404)
        self.assertIn("Page Not Found", response.data.decode('utf-8'))

if __name__ == '__main__':
    unittest.main()
