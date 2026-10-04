import unittest
import importlib.util
from pathlib import Path

# Load csp_solver
solver_path = Path(__file__).resolve().parent.parent / 'app' / 'csp_solver.py'
spec = importlib.util.spec_from_file_location("csp_solver_module", str(solver_path))
csp_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csp_module)
CSPSchedulingEngine = csp_module.CSPSchedulingEngine

class CSPSchedulingEngineTestCase(unittest.TestCase):
    def setUp(self):
        """Set up standard skills catalog for tests."""
        self.skills = [
            {'id': 1, 'name': 'Customer Service'},
            {'id': 2, 'name': 'Inventory Management'},
            {'id': 3, 'name': 'Shift Supervision'},
            {'id': 4, 'name': 'Technical Support'}
        ]
        self.settings = {
            'min_rest_hours_between_shifts': 11.0,
            'default_max_weekly_hours': 40.0
        }

    def _build_standard_availability(self, days=(0, 1, 2, 3, 4), start="08:00", end="17:00"):
        """Helper to build 7-day availability mapping."""
        avail = {}
        for d in range(7):
            if d in days:
                avail[d] = {'is_available': 1, 'start_time': start, 'end_time': end}
            else:
                avail[d] = {'is_available': 0, 'start_time': '00:00', 'end_time': '00:00'}
        return avail

    def test_5_employees_scenario(self):
        """Test scheduling 5 employees with diverse skills and tasks."""
        employees = [
            {
                'id': 1, 'name': 'Alice Supervisor', 'employee_code': 'EMP-01', 'role': 'Supervisor',
                'max_weekly_hours': 40.0, 'target_weekly_hours': 35.0, 'is_active': 1,
                'skills_list': [{'id': 3, 'proficiency_level': 'Expert'}, {'id': 1, 'proficiency_level': 'Standard'}],
                'availability': self._build_standard_availability(days=(0, 1, 2, 3, 4), start="07:00", end="23:00")
            },
            {
                'id': 2, 'name': 'Bob Inventory', 'employee_code': 'EMP-02', 'role': 'Specialist',
                'max_weekly_hours': 40.0, 'target_weekly_hours': 35.0, 'is_active': 1,
                'skills_list': [{'id': 2, 'proficiency_level': 'Expert'}],
                'availability': self._build_standard_availability(days=(0, 1, 2, 3, 4), start="08:00", end="17:00")
            },
            {
                'id': 3, 'name': 'Charlie Tech', 'employee_code': 'EMP-03', 'role': 'Technician',
                'max_weekly_hours': 35.0, 'target_weekly_hours': 30.0, 'is_active': 1,
                'skills_list': [{'id': 4, 'proficiency_level': 'Advanced'}, {'id': 1, 'proficiency_level': 'Standard'}],
                'availability': self._build_standard_availability(days=(0, 1, 2, 3, 4), start="08:00", end="20:00")
            },
            {
                'id': 4, 'name': 'Diana Support', 'employee_code': 'EMP-04', 'role': 'Support',
                'max_weekly_hours': 30.0, 'target_weekly_hours': 25.0, 'is_active': 1,
                'skills_list': [{'id': 1, 'proficiency_level': 'Expert'}],
                'availability': self._build_standard_availability(days=(0, 1, 2, 3, 4, 5), start="08:00", end="18:00")
            },
            {
                'id': 5, 'name': 'Evan Associate', 'employee_code': 'EMP-05', 'role': 'Associate',
                'max_weekly_hours': 40.0, 'target_weekly_hours': 35.0, 'is_active': 1,
                'skills_list': [{'id': 1, 'proficiency_level': 'Standard'}, {'id': 2, 'proficiency_level': 'Standard'}],
                'availability': self._build_standard_availability(days=(0, 1, 2, 3, 4, 5, 6), start="07:00", end="22:00")
            }
        ]

        tasks = [
            {'id': 101, 'task_code': 'TSK-01', 'title': 'Monday Floor Supervision', 'day_of_week': 0, 'start_time': '08:00', 'end_time': '16:00', 'duration_hours': 8.0, 'required_skill_id': 3, 'min_staff': 1, 'priority': 2},
            {'id': 102, 'task_code': 'TSK-02', 'title': 'Monday Inventory Audit', 'day_of_week': 0, 'start_time': '09:00', 'end_time': '14:00', 'duration_hours': 5.0, 'required_skill_id': 2, 'min_staff': 1, 'priority': 1},
            {'id': 103, 'task_code': 'TSK-03', 'title': 'Monday Customer Helpdesk', 'day_of_week': 0, 'start_time': '10:00', 'end_time': '18:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 2, 'priority': 2},
            {'id': 104, 'task_code': 'TSK-04', 'title': 'Tuesday IT Infrastructure', 'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'duration_hours': 8.0, 'required_skill_id': 4, 'min_staff': 1, 'priority': 2},
            {'id': 105, 'task_code': 'TSK-05', 'title': 'Tuesday Team Coordination', 'day_of_week': 1, 'start_time': '08:00', 'end_time': '16:00', 'duration_hours': 8.0, 'required_skill_id': 3, 'min_staff': 1, 'priority': 2}
        ]

        engine = CSPSchedulingEngine(employees, tasks, self.skills, self.settings)
        result = engine.solve()

        self.assertTrue(result['is_feasible'])
        self.assertEqual(result['unassigned_slots'], 0)
        self.assertEqual(result['assigned_slots'], 6)  # 5 tasks, one requires 2 staff = 6 slots

        # Verify no employee has overlapping assignments
        emp_assignments = {}
        for a in result['assignments']:
            emp_assignments.setdefault(a['employee_id'], []).append(a)

        for eid, assign_list in emp_assignments.items():
            for i in range(len(assign_list)):
                for j in range(i + 1, len(assign_list)):
                    a1 = assign_list[i]
                    a2 = assign_list[j]
                    if a1['day_of_week'] == a2['day_of_week']:
                        # Must not overlap
                        s1 = int(a1['start_time'].split(':')[0]) * 60 + int(a1['start_time'].split(':')[1])
                        e1 = int(a1['end_time'].split(':')[0]) * 60 + int(a1['end_time'].split(':')[1])
                        s2 = int(a2['start_time'].split(':')[0]) * 60 + int(a2['start_time'].split(':')[1])
                        e2 = int(a2['end_time'].split(':')[0]) * 60 + int(a2['end_time'].split(':')[1])
                        self.assertFalse(max(s1, s2) < min(e1, e2), f"Overlap found for employee {eid} between {a1['title']} and {a2['title']}")

    def test_missing_skill_explains_unassigned_task(self):
        """Verify that a task requiring an unavailable skill is flagged with a clear conflict explanation."""
        employees = [
            {
                'id': 1, 'name': 'Support Only', 'employee_code': 'EMP-01', 'role': 'Associate',
                'max_weekly_hours': 40.0, 'target_weekly_hours': 35.0, 'is_active': 1,
                'skills_list': [{'id': 1, 'proficiency_level': 'Standard'}],
                'availability': self._build_standard_availability()
            }
        ]
        tasks = [
            # Requires skill id 4 (Technical Support), which employee doesn't have
            {'id': 201, 'task_code': 'TSK-TECH', 'title': 'Server Recovery', 'day_of_week': 0, 'start_time': '09:00', 'end_time': '17:00', 'duration_hours': 8.0, 'required_skill_id': 4, 'min_staff': 1, 'priority': 3}
        ]

        engine = CSPSchedulingEngine(employees, tasks, self.skills, self.settings)
        result = engine.solve()

        self.assertEqual(result['assigned_slots'], 0)
        self.assertEqual(result['unassigned_slots'], 1)
        self.assertEqual(len(result['unassigned_tasks']), 1)
        unassigned_info = result['unassigned_tasks'][0]
        self.assertTrue(any('Missing Skill' in reason for reason in unassigned_info['reasons']))

    def test_overlapping_shifts_conflict_handled(self):
        """Verify that two simultaneous shifts cannot both be assigned to the only qualified worker."""
        employees = [
            {
                'id': 1, 'name': 'Solo Specialist', 'employee_code': 'EMP-SOLO', 'role': 'Specialist',
                'max_weekly_hours': 40.0, 'target_weekly_hours': 35.0, 'is_active': 1,
                'skills_list': [{'id': 2, 'proficiency_level': 'Expert'}],
                'availability': self._build_standard_availability(days=(0,), start="08:00", end="18:00")
            }
        ]
        tasks = [
            {'id': 301, 'task_code': 'TSK-A', 'title': 'Inventory Front', 'day_of_week': 0, 'start_time': '09:00', 'end_time': '13:00', 'duration_hours': 4.0, 'required_skill_id': 2, 'min_staff': 1, 'priority': 2},
            {'id': 302, 'task_code': 'TSK-B', 'title': 'Inventory Back', 'day_of_week': 0, 'start_time': '10:00', 'end_time': '14:00', 'duration_hours': 4.0, 'required_skill_id': 2, 'min_staff': 1, 'priority': 1}
        ]

        engine = CSPSchedulingEngine(employees, tasks, self.skills, self.settings)
        result = engine.solve()

        # Exactly 1 can be assigned, the other must be unassigned due to overlap
        self.assertEqual(result['assigned_slots'], 1)
        self.assertEqual(result['unassigned_slots'], 1)
        # Higher priority (priority 2) should be assigned
        self.assertEqual(result['assignments'][0]['task_id'], 301)
        self.assertTrue(any('Time Overlap' in r or 'Staff Capacity' in r for r in result['unassigned_tasks'][0]['reasons']))

    def test_max_hours_limit_enforced(self):
        """Verify that an employee is not assigned tasks exceeding their max weekly hours limit."""
        employees = [
            {
                'id': 1, 'name': 'Part Timer', 'employee_code': 'EMP-PT', 'role': 'Associate',
                'max_weekly_hours': 10.0, 'target_weekly_hours': 10.0, 'is_active': 1,
                'skills_list': [{'id': 1, 'proficiency_level': 'Standard'}],
                'availability': self._build_standard_availability(days=(0, 1, 2), start="08:00", end="18:00")
            }
        ]
        # Three 8-hour shifts on separate days (24 hours total, but employee max is 10.0)
        tasks = [
            {'id': 401, 'task_code': 'TSK-D1', 'title': 'Shift Mon', 'day_of_week': 0, 'start_time': '09:00', 'end_time': '17:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 2},
            {'id': 402, 'task_code': 'TSK-D2', 'title': 'Shift Tue', 'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 2},
            {'id': 403, 'task_code': 'TSK-D3', 'title': 'Shift Wed', 'day_of_week': 2, 'start_time': '09:00', 'end_time': '17:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 2}
        ]

        engine = CSPSchedulingEngine(employees, tasks, self.skills, self.settings)
        result = engine.solve()

        # Employee can only take 1 shift (8h <= 10h); second shift would be 16h > 10h
        self.assertEqual(result['assigned_slots'], 1)
        self.assertEqual(result['unassigned_slots'], 2)
        total_hours = sum(a['duration_hours'] for a in result['assignments'])
        self.assertLessEqual(total_hours, 10.0)

    def test_minimum_rest_period_enforced(self):
        """Verify that an employee finishing an evening/night shift cannot work a morning shift within 11 hours."""
        employees = [
            {
                'id': 1, 'name': 'Night Worker', 'employee_code': 'EMP-N', 'role': 'Staff',
                'max_weekly_hours': 40.0, 'target_weekly_hours': 35.0, 'is_active': 1,
                'skills_list': [{'id': 1, 'proficiency_level': 'Standard'}],
                'availability': self._build_standard_availability(days=(0, 1), start="00:00", end="23:59")
            }
        ]
        # Task 1: Monday evening ending at 23:00 (day 0)
        # Task 2: Tuesday morning starting at 07:00 (day 1) -> only 8 hours rest, violation of 11h minimum!
        tasks = [
            {'id': 501, 'task_code': 'TSK-EVN', 'title': 'Monday Late Shift', 'day_of_week': 0, 'start_time': '15:00', 'end_time': '23:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 2},
            {'id': 502, 'task_code': 'TSK-MRN', 'title': 'Tuesday Early Shift', 'day_of_week': 1, 'start_time': '07:00', 'end_time': '15:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 2}
        ]

        engine = CSPSchedulingEngine(employees, tasks, self.skills, self.settings)
        result = engine.solve()

        # Cannot assign both to the same employee due to rest period violation
        self.assertEqual(result['assigned_slots'], 1)
        self.assertEqual(result['unassigned_slots'], 1)

    def test_10_employees_scenario_with_fairness(self):
        """Test scheduling 10 employees across Morning, Afternoon, and Night shifts with fair distribution."""
        employees = []
        for i in range(1, 11):
            employees.append({
                'id': i,
                'name': f"Employee {i}",
                'employee_code': f"EMP-{100 + i}",
                'role': 'Supervisor' if i <= 2 else ('Specialist' if i <= 5 else 'Staff Associate'),
                'max_weekly_hours': 40.0,
                'target_weekly_hours': 32.0,
                'is_active': 1,
                'skills_list': [
                    {'id': 1, 'proficiency_level': 'Standard'},
                    {'id': 2 if i % 2 == 0 else 3, 'proficiency_level': 'Standard'},
                    {'id': 4 if i % 3 == 0 else 1, 'proficiency_level': 'Standard'}
                ],
                'availability': self._build_standard_availability(days=(0, 1, 2, 3, 4, 5, 6), start="00:00", end="23:59")
            })

        tasks = []
        task_id = 600
        # Create shifts for Monday through Friday: Morning (08-16), Afternoon (16-00), Night (00-08)
        for day in range(5):
            tasks.append({'id': task_id + 1, 'task_code': f"TSK-M-D{day}", 'title': f"Morning Day {day}", 'shift_type': 'Morning', 'day_of_week': day, 'start_time': '08:00', 'end_time': '16:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 2, 'priority': 2})
            tasks.append({'id': task_id + 2, 'task_code': f"TSK-A-D{day}", 'title': f"Afternoon Day {day}", 'shift_type': 'Afternoon', 'day_of_week': day, 'start_time': '16:00', 'end_time': '23:59', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 1})
            tasks.append({'id': task_id + 3, 'task_code': f"TSK-N-D{day}", 'title': f"Night Day {day}", 'shift_type': 'Night', 'day_of_week': day, 'start_time': '00:00', 'end_time': '08:00', 'duration_hours': 8.0, 'required_skill_id': 1, 'min_staff': 1, 'priority': 2})
            task_id += 3

        engine = CSPSchedulingEngine(employees, tasks, self.skills, self.settings)
        result = engine.solve()

        self.assertTrue(result['is_feasible'])
        self.assertEqual(result['unassigned_slots'], 0)
        self.assertGreater(result['fairness_score'], 70.0)

        # Verify night shift distribution is balanced (no single employee bears all night shifts)
        night_counts = [w['night_shifts_count'] for w in result['workload_stats']]
        self.assertLessEqual(max(night_counts) - min(night_counts), 3)

if __name__ == '__main__':
    unittest.main()
