import unittest
import os
import json
from pathlib import Path
import importlib.util

ROOT_DIR = Path(__file__).resolve().parent.parent
app_py_path = ROOT_DIR / 'app.py'
spec = importlib.util.spec_from_file_location("root_app_module_scheduler", str(app_py_path))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

class TasksAndSchedulerTestCase(unittest.TestCase):
    def setUp(self):
        """Set up test client and isolated test database."""
        self.app = app_module.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        self.test_db_path = Path(__file__).resolve().parent / 'test_scheduler_integration.db'
        app_module.DATABASE_PATH = self.test_db_path

        with self.app.app_context():
            app_module.init_db()
            db = app_module.get_db()
            skills = [
                ('Customer Service', 'Handles client interactions and checkout'),
                ('Inventory Management', 'Stock management and inventory audits'),
                ('Shift Supervision', 'Team leadership and floor coordination'),
                ('Technical Support', 'Hardware and systems maintenance'),
                ('Python', 'Python programming'),
                ('SQL', 'Database query and schema management'),
                ('Java', 'Java enterprise applications'),
                ('Testing', 'Quality assurance and software testing')
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

    def test_task_crud_lifecycle(self):
        """Verify Task creation, listing, editing, and deletion."""
        # 1. Create task
        task_data = {
            'task_code': 'TSK-999',
            'title': 'System Integration Testing',
            'shift_type': 'Morning',
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',
            'duration_hours': '8.0',
            'required_skill_id': '4',
            'min_staff': '1',
            'priority': '2'
        }
        res = self.client.post('/tasks/new', data=task_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        content = res.data.decode('utf-8')
        self.assertIn("System Integration Testing", content)
        self.assertIn("TSK-999", content)

        # 2. List tasks API
        api_res = self.client.get('/api/tasks')
        self.assertEqual(api_res.status_code, 200)
        data = json.loads(api_res.data)
        self.assertGreaterEqual(data['count'], 1)
        created_task = next(t for t in data['tasks'] if t['task_code'] == 'TSK-999')
        task_id = created_task['id']

        # 3. Edit task
        edit_data = {
            'task_code': 'TSK-999',
            'title': 'Updated System Integration Testing',
            'shift_type': 'Afternoon',
            'day_of_week': '1',
            'start_time': '16:00',
            'end_time': '23:59',
            'duration_hours': '8.0',
            'required_skill_id': '4',
            'min_staff': '2',
            'priority': '3'
        }
        edit_res = self.client.post(f'/tasks/{task_id}/edit', data=edit_data, follow_redirects=True)
        self.assertEqual(edit_res.status_code, 200)
        self.assertIn("Updated System Integration Testing", edit_res.data.decode('utf-8'))

        # 4. Delete task
        del_res = self.client.post(f'/tasks/{task_id}/delete', follow_redirects=True)
        self.assertEqual(del_res.status_code, 200)
        del_html = del_res.data.decode('utf-8')
        self.assertIn("deleted successfully", del_html)
        self.assertIn("Showing 0 shift definitions", del_html)

    def test_presets_loading_and_scheduler_generation(self):
        """Verify loading 5-employee preset and generating schedule with persistence."""
        # 1. Load 5 employees preset
        p1_res = self.client.post('/bulk-entry/presets/5_employees', follow_redirects=True)
        self.assertEqual(p1_res.status_code, 200)

        # 2. Load standard tasks preset
        p2_res = self.client.post('/bulk-entry/presets/standard_tasks', follow_redirects=True)
        self.assertEqual(p2_res.status_code, 200)

        # 3. Generate schedule
        gen_res = self.client.post('/scheduler/generate', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)
        gen_content = gen_res.data.decode('utf-8')
        self.assertIn("Generated Work Assignments", gen_content)
        self.assertIn("Employee Workload", gen_content)

        # 4. Verify DB records
        with self.app.app_context():
            db = app_module.get_db()
            sched_count = db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
            assign_count = db.execute("SELECT COUNT(*) FROM shift_assignments").fetchone()[0]
            self.assertEqual(sched_count, 1)
            self.assertGreater(assign_count, 0)

            # Verify no employee has overlapping tasks in the DB
            assignments = db.execute("""
                SELECT sa.employee_id, s.day_of_week, sa.start_time, sa.end_time
                FROM shift_assignments sa
                JOIN shifts s ON sa.shift_id = s.id
                ORDER BY sa.employee_id, s.day_of_week, sa.start_time
            """).fetchall()

            for i in range(len(assignments)):
                for j in range(i + 1, len(assignments)):
                    a1 = assignments[i]
                    a2 = assignments[j]
                    if a1['employee_id'] == a2['employee_id'] and a1['day_of_week'] == a2['day_of_week']:
                        s1 = int(a1['start_time'].split(':')[0]) * 60 + int(a1['start_time'].split(':')[1])
                        e1 = int(a1['end_time'].split(':')[0]) * 60 + int(a1['end_time'].split(':')[1])
                        s2 = int(a2['start_time'].split(':')[0]) * 60 + int(a2['start_time'].split(':')[1])
                        e2 = int(a2['end_time'].split(':')[0]) * 60 + int(a2['end_time'].split(':')[1])
                        self.assertFalse(max(s1, s2) < min(e1, e2), f"Overlap detected for emp {a1['employee_id']}")

        # 5. Verify CSV export
        with self.app.app_context():
            db = app_module.get_db()
            latest_id = db.execute("SELECT id FROM schedules LIMIT 1").fetchone()[0]
        csv_res = self.client.get(f'/scheduler/export/{latest_id}')
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn('text/csv', csv_res.headers.get('Content-Type', ''))
        self.assertIn("Task Code", csv_res.data.decode('utf-8'))

        # 6. Verify Weekly Roster view
        roster_res = self.client.get('/roster')
        self.assertEqual(roster_res.status_code, 200)
        self.assertIn("Weekly Shift Schedule Matrix", roster_res.data.decode('utf-8'))

    def test_conflict_preset_produces_transparent_explanations(self):
        """Verify that impossible tasks are diagnosed and reported with conflict reasons."""
        # 1. Load 5 employees
        self.client.post('/bulk-entry/presets/5_employees', follow_redirects=True)
        # 2. Load conflict stress-test tasks
        self.client.post('/bulk-entry/presets/conflict_tasks', follow_redirects=True)

        # 3. Generate schedule
        gen_res = self.client.post('/scheduler/generate', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)
        content = gen_res.data.decode('utf-8')
        self.assertIn("Unassigned Tasks & Conflict Root-Cause Explanations", content)

        # 4. Check unfilled records in DB
        with self.app.app_context():
            db = app_module.get_db()
            unfilled_count = db.execute("SELECT COUNT(*) FROM unfilled_shift_records").fetchone()[0]
            self.assertGreater(unfilled_count, 0)
            reasons = db.execute("SELECT reason, details FROM unfilled_shift_records").fetchall()
            all_reasons_str = " ".join([f"{r['reason']} {r['details']}" for r in reasons])
            self.assertTrue(
                "Missing Skill" in all_reasons_str or
                "Availability Conflict" in all_reasons_str or
                "Time Overlap" in all_reasons_str
            )

    def test_user_scenario_5_employees_skills_and_tasks(self):
        """
        Verify the exact scenario requested by the user:
        Employees:
          - Arun (Python, SQL), Mon-Fri 09:00-17:00, max 40h
          - Priya (Java, Testing), Mon-Fri 09:00-17:00, max 40h
          - Kumar (Python, Testing), Mon-Fri 09:00-17:00, max 40h
          - Deepa (SQL), Mon-Fri 09:00-17:00, max 40h
          - Manoj (Java), Mon-Fri 09:00-17:00, max 40h
        Tasks:
          - T001: Develop Login Module (Python), Mon 10:00-12:00, 2h, req 1
          - T002: Database Testing (SQL), Mon 11:00-13:00, 2h, req 1
          - T003: UI Testing (Testing), Mon 14:00-16:00, 2h, req 1
          - T004: Backend API (Java), Mon 10:00-12:00, 2h, req 1
          - T005: Cloud DevOps (DevOps - unassigned skill), Mon 10:00-12:00, 2h, req 1
        """
        with self.app.app_context():
            db = app_module.get_db()
            # Clear existing data for clean run
            db.execute("DELETE FROM shifts")
            db.execute("DELETE FROM employee_skills")
            db.execute("DELETE FROM employee_availability")
            db.execute("DELETE FROM employees")
            
            # Ensure skills
            db.execute("INSERT OR IGNORE INTO skills (name) VALUES ('DevOps')")
            db.commit()

            skill_map = {r['name']: r['id'] for r in db.execute("SELECT id, name FROM skills").fetchall()}

            # Create 5 employees
            user_emps = [
                ('EMP-101', 'Arun', 'arun@workforce.local', 'Supervisor', 40.0, ['Python', 'SQL']),
                ('EMP-102', 'Priya', 'priya@workforce.local', 'Specialist', 40.0, ['Java', 'Testing']),
                ('EMP-103', 'Kumar', 'kumar@workforce.local', 'Staff', 40.0, ['Python', 'Testing']),
                ('EMP-104', 'Deepa', 'deepa@workforce.local', 'Staff', 40.0, ['SQL']),
                ('EMP-105', 'Manoj', 'manoj@workforce.local', 'Staff', 40.0, ['Java'])
            ]

            for code, name, email, role, max_h, sk_list in user_emps:
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO employees (employee_code, name, email, role, max_weekly_hours, target_weekly_hours, is_active)
                    VALUES (?, ?, ?, ?, ?, 35.0, 1)
                """, (code, name, email, role, max_h))
                eid = cur.lastrowid
                for sk in sk_list:
                    db.execute("INSERT INTO employee_skills (employee_id, skill_id, proficiency_level) VALUES (?, ?, 'Expert')", (eid, skill_map[sk]))
                for d in range(7):
                    is_av = 1 if d <= 4 else 0
                    db.execute("INSERT INTO employee_availability (employee_id, day_of_week, start_time, end_time, is_available) VALUES (?, ?, '09:00', '17:00', ?)", (eid, d, is_av))

            # Create tasks
            user_tasks = [
                ('T001', 'Develop Login Module', 'Morning', 0, '10:00', '12:00', 2.0, skill_map['Python'], 1, 2),
                ('T002', 'Database Testing', 'Morning', 0, '11:00', '13:00', 2.0, skill_map['SQL'], 1, 2),
                ('T003', 'UI Testing', 'Morning', 0, '14:00', '16:00', 2.0, skill_map['Testing'], 1, 2),
                ('T004', 'Backend API', 'Morning', 0, '10:00', '12:00', 2.0, skill_map['Java'], 1, 2),
                ('T005', 'Cloud DevOps', 'Morning', 0, '10:00', '12:00', 2.0, skill_map['DevOps'], 1, 2),
            ]

            db.executemany("""
                INSERT INTO shifts (task_code, title, shift_type, day_of_week, start_time, end_time, duration_hours, required_skill_id, min_staff, priority, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, user_tasks)
            db.commit()

        # Run scheduler generate
        res = self.client.post('/scheduler/generate', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        page_html = res.data.decode('utf-8')

        # Verify:
        # 1. 4 tasks are assigned, 1 task (Cloud DevOps) is unassigned due to missing DevOps skill
        self.assertIn("Slots Assigned", page_html)
        self.assertIn("Cloud DevOps", page_html)
        self.assertIn("Missing Skill", page_html)

        with self.app.app_context():
            db = app_module.get_db()
            assignments = db.execute("""
                SELECT sa.*, s.task_code, e.name AS employee_name
                FROM shift_assignments sa
                JOIN shifts s ON sa.shift_id = s.id
                JOIN employees e ON sa.employee_id = e.id
            """).fetchall()

            self.assertEqual(len(assignments), 4)
            assigned_codes = {a['task_code'] for a in assignments}
            self.assertEqual(assigned_codes, {'T001', 'T002', 'T003', 'T004'})

            unassigned = db.execute("SELECT * FROM unfilled_shift_records").fetchall()
            self.assertEqual(len(unassigned), 1)

if __name__ == '__main__':
    unittest.main()
