"""
Constraint-Based Intelligent Workforce Scheduling and Fair Workload Optimization System
CSP Scheduling Engine utilizing Google OR-Tools CP-SAT and Pure-Python Backtracking Fallback.
"""

import math
from datetime import datetime, time, timedelta
from typing import Dict, List, Any, Tuple, Optional

# Attempt to import Google OR-Tools CP-SAT
try:
    from ortools.sat.python import cp_model
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False


def parse_time_to_minutes(t_val) -> int:
    """Converts a time string HH:MM or time object to minutes from midnight (0..1439)."""
    if isinstance(t_val, (datetime, time)):
        return t_val.hour * 60 + t_val.minute
    if isinstance(t_val, str):
        parts = t_val.strip().split(':')
        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(parts[1])
    return 0


def time_intervals_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """Checks whether two time intervals overlap on the same day."""
    return max(start1, start2) < min(end1, end2)


def rest_period_violated(day1: int, end1: int, day2: int, start2: int, min_rest_minutes: int) -> bool:
    """
    Checks if consecutive tasks violate the minimum rest period.
    Handles same-day tasks and consecutive-day tasks across midnight.
    """
    total_start1 = day1 * 1440
    total_end1 = total_start1 + end1
    total_start2 = day2 * 1440 + start2

    if total_start2 >= total_end1:
        rest_duration = total_start2 - total_end1
        return rest_duration < min_rest_minutes
    return False


class CSPSchedulingEngine:
    """
    Formal Constraint Satisfaction Problem (CSP) Solver for workforce scheduling.
    
    Variables:
        X[task_id, slot_idx, emp_id] in {0, 1}
        where task_id in Tasks, slot_idx in {0..min_staff-1}, emp_id in Eligible(task_id).
    
    Domains:
        Eligible(task_id) = {
            e in Employees |
            e.is_active == 1 and
            has_required_skill(e, task_id) and
            is_available(e, task_id.day, task_id.start, task_id.end)
        }
    
    Hard Constraints:
        1. Slot Capacity: sum(X[t, s, e] for e) <= 1
        2. No Double-Booking on Same Task: sum(X[t, s, e] for s) <= 1
        3. No Overlapping Tasks: For overlapping tasks t1, t2 on same day, sum(X[t1, *, e]) + sum(X[t2, *, e]) <= 1
        4. Minimum Rest Period: For tasks t1, t2 within min_rest window, e cannot be assigned to both.
        5. Maximum Working Hours: sum(duration(t) * X[t, s, e]) <= max_weekly_hours[e]
    
    Optimization Objective:
        Maximize Task Staffing Fulfillment (weighted by task priority)
        MINIMIZE Workload Deviation: sum(|assigned_hours[e] - target_hours[e]|)
        MINIMIZE Night Shift Variance: fair distribution of night shifts
    """

    def __init__(self, employees: List[Dict], tasks: List[Dict], skills: List[Dict], settings: Optional[Dict] = None):
        self.employees = employees
        self.tasks = tasks
        self.skills = {s['id']: s['name'] for s in skills}
        self.settings = settings or {}

        # Load constraint parameters
        self.min_rest_hours = float(self.settings.get('min_rest_hours_between_shifts', 11.0))
        self.min_rest_minutes = int(self.min_rest_hours * 60)
        self.default_max_hours = float(self.settings.get('default_max_weekly_hours', 40.0))

        # Index employee skills and availability
        self.emp_skills_map = {}
        self.emp_avail_map = {}
        self.emp_by_id = {}

        for emp in self.employees:
            eid = emp['id']
            self.emp_by_id[eid] = emp
            # Skills
            skills_list = emp.get('skills_list') or []
            self.emp_skills_map[eid] = {
                (s['id'] if 'id' in s else s.get('skill_id')): s.get('proficiency_level', 'Standard')
                for s in skills_list
            }
            # Availability by day (0..6)
            self.emp_avail_map[eid] = {}
            for day_idx in range(7):
                avail_info = emp.get('availability', {}).get(day_idx)
                if avail_info and avail_info.get('is_available', 1) == 1:
                    start_m = parse_time_to_minutes(avail_info.get('start_time', '00:00'))
                    end_m = parse_time_to_minutes(avail_info.get('end_time', '23:59'))
                    self.emp_avail_map[eid][day_idx] = (start_m, end_m)

    def is_employee_skill_qualified(self, emp_id: int, required_skill_id: Optional[int]) -> bool:
        """Checks if employee has the required skill."""
        if not required_skill_id:
            return True
        return required_skill_id in self.emp_skills_map.get(emp_id, {})

    def is_employee_available(self, emp_id: int, day: int, start_m: int, end_m: int) -> bool:
        """Checks if employee availability window encompasses the task time on given day."""
        avail_windows = self.emp_avail_map.get(emp_id, {})
        if day not in avail_windows:
            return False
        avail_start, avail_end = avail_windows[day]
        return avail_start <= start_m and end_m <= avail_end

    def solve(self) -> Dict[str, Any]:
        """Runs the CSP solver and returns assignments, unassigned explanations, and workload metrics."""
        if HAS_ORTOOLS:
            return self._solve_ortools()
        return self._solve_backtracking()

    def _solve_ortools(self) -> Dict[str, Any]:
        """Solves the CSP formulation using Google OR-Tools CP-SAT."""
        start_time = datetime.now()
        model = cp_model.CpModel()

        # Build task slots
        task_slots = []
        for t in self.tasks:
            req_staff = max(1, int(t.get('min_staff') or 1))
            for s in range(req_staff):
                task_slots.append((t, s))

        # Variables: X[(t_id, slot_idx, emp_id)] in {0, 1}
        X = {}
        task_emp_vars = {t['id']: [] for t in self.tasks}
        emp_assigned_slots = {e['id']: [] for e in self.employees}
        emp_night_shifts = {e['id']: [] for e in self.employees}

        # Filter Domains
        for t, s in task_slots:
            t_id = t['id']
            req_skill = t.get('required_skill_id')
            t_day = int(t['day_of_week'])
            t_start = parse_time_to_minutes(t['start_time'])
            t_end = parse_time_to_minutes(t['end_time'])
            is_night = t.get('shift_type') == 'Night' or t_start >= 1320 or t_end <= 480

            for emp in self.employees:
                eid = emp['id']
                if emp.get('is_active', 1) != 1:
                    continue
                # Skill domain check
                if not self.is_employee_skill_qualified(eid, req_skill):
                    continue
                # Availability domain check
                if not self.is_employee_available(eid, t_day, t_start, t_end):
                    continue

                var = model.NewBoolVar(f"X_t{t_id}_s{s}_e{eid}")
                X[(t_id, s, eid)] = var
                task_emp_vars[t_id].append((s, eid, var))
                emp_assigned_slots[eid].append((t, var))
                if is_night:
                    emp_night_shifts[eid].append(var)

        # Hard Constraint 1: At most 1 employee assigned to each task slot
        for t, s in task_slots:
            slot_vars = [X[(t['id'], s, e['id'])] for e in self.employees if (t['id'], s, e['id']) in X]
            if slot_vars:
                model.Add(sum(slot_vars) <= 1)

        # Hard Constraint 2: Each employee assigned at most once per task (no duplicate slots)
        for t in self.tasks:
            for emp in self.employees:
                emp_in_task = [X[(t['id'], s, emp['id'])] for s in range(max(1, int(t.get('min_staff', 1)))) if (t['id'], s, emp['id']) in X]
                if len(emp_in_task) > 1:
                    model.Add(sum(emp_in_task) <= 1)

        # Hard Constraint 3: No Overlapping Tasks for the same employee
        for i in range(len(self.tasks)):
            t1 = self.tasks[i]
            day1 = int(t1['day_of_week'])
            start1 = parse_time_to_minutes(t1['start_time'])
            end1 = parse_time_to_minutes(t1['end_time'])

            for j in range(i + 1, len(self.tasks)):
                t2 = self.tasks[j]
                day2 = int(t2['day_of_week'])
                start2 = parse_time_to_minutes(t2['start_time'])
                end2 = parse_time_to_minutes(t2['end_time'])

                if day1 == day2 and time_intervals_overlap(start1, end1, start2, end2):
                    for emp in self.employees:
                        eid = emp['id']
                        v1 = [X[(t1['id'], s, eid)] for s in range(max(1, int(t1.get('min_staff', 1)))) if (t1['id'], s, eid) in X]
                        v2 = [X[(t2['id'], s, eid)] for s in range(max(1, int(t2.get('min_staff', 1)))) if (t2['id'], s, eid) in X]
                        if v1 and v2:
                            model.Add(sum(v1) + sum(v2) <= 1)

        # Hard Constraint 4: Minimum Rest Period Between Consecutive Tasks
        for i in range(len(self.tasks)):
            t1 = self.tasks[i]
            day1 = int(t1['day_of_week'])
            end1 = parse_time_to_minutes(t1['end_time'])

            for j in range(len(self.tasks)):
                if i == j:
                    continue
                t2 = self.tasks[j]
                day2 = int(t2['day_of_week'])
                start2 = parse_time_to_minutes(t2['start_time'])

                if rest_period_violated(day1, end1, day2, start2, self.min_rest_minutes):
                    for emp in self.employees:
                        eid = emp['id']
                        v1 = [X[(t1['id'], s, eid)] for s in range(max(1, int(t1.get('min_staff', 1)))) if (t1['id'], s, eid) in X]
                        v2 = [X[(t2['id'], s, eid)] for s in range(max(1, int(t2.get('min_staff', 1)))) if (t2['id'], s, eid) in X]
                        if v1 and v2:
                            model.Add(sum(v1) + sum(v2) <= 1)

        # Hard Constraint 5: Maximum Weekly Working Hours per employee
        for emp in self.employees:
            eid = emp['id']
            max_h = float(emp.get('max_weekly_hours') or self.default_max_hours)
            # Scale hours by 10 to work with integer CP-SAT model
            max_scaled = int(round(max_h * 10))
            task_terms = []
            for t, var in emp_assigned_slots[eid]:
                dur = float(t.get('duration_hours') or 0.0)
                dur_scaled = int(round(dur * 10))
                task_terms.append(dur_scaled * var)
            if task_terms:
                model.Add(sum(task_terms) <= max_scaled)

        # Multi-Objective Function:
        # 1. Primary: Maximize fulfillment (weighted by task priority: priority * 10000)
        # 2. Workload Spread Minimization: Minimize (max_hours - min_hours) across employees
        # 3. Night Shift Spread Minimization: Balance night shift allocation
        # 4. Target Deviation Minimization: Minimize |assigned - target|
        obj_fulfillment = []
        for (t_id, s, eid), var in X.items():
            t = next(task for task in self.tasks if task['id'] == t_id)
            priority = int(t.get('priority') or 1)
            weight = 10000 * priority
            obj_fulfillment.append(weight * var)

        active_emp_ids = [e['id'] for e in self.employees if e.get('is_active', 1) == 1]
        assigned_vars = {}
        dev_vars = []

        for eid in active_emp_ids:
            task_terms = [int(round(float(t.get('duration_hours', 0.0)) * 10)) * var for t, var in emp_assigned_slots[eid]]
            a_var = model.NewIntVar(0, 1000, f"h_{eid}")
            if task_terms:
                model.Add(a_var == sum(task_terms))
            else:
                model.Add(a_var == 0)
            assigned_vars[eid] = a_var

            # Target deviation
            target_h = float(self.emp_by_id[eid].get('target_weekly_hours') or 35.0)
            target_scaled = int(round(target_h * 10))
            dev = model.NewIntVar(0, 1000, f"dev_{eid}")
            model.Add(dev >= a_var - target_scaled)
            model.Add(dev >= target_scaled - a_var)
            dev_vars.append(dev)

        # Min-Max Workload Spread
        max_assigned = model.NewIntVar(0, 1000, "max_assigned")
        min_assigned = model.NewIntVar(0, 1000, "min_assigned")
        for a_var in assigned_vars.values():
            model.Add(max_assigned >= a_var)
            model.Add(min_assigned <= a_var)
        workload_spread = max_assigned - min_assigned

        # Min-Max Night Shift Spread
        has_night = any(emp_night_shifts[eid] for eid in active_emp_ids)
        night_penalty = None
        if has_night:
            max_night = model.NewIntVar(0, 50, "max_night")
            min_night = model.NewIntVar(0, 50, "min_night")
            for eid in active_emp_ids:
                if emp_night_shifts[eid]:
                    n_sum = sum(emp_night_shifts[eid])
                    model.Add(max_night >= n_sum)
                    model.Add(min_night <= n_sum)
                else:
                    model.Add(min_night <= 0)
            night_penalty = 50 * (max_night - min_night)

        # Combine into single maximization objective
        total_objective = sum(obj_fulfillment) - (20 * workload_spread) - sum(dev_vars)
        if night_penalty is not None:
            total_objective = total_objective - night_penalty

        model.Maximize(total_objective)

        # Solve model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(model)

        solve_duration = (datetime.now() - start_time).total_seconds()
        status_name = solver.StatusName(status)

        # Extract assignments
        assignments = []
        assigned_slots_count = 0
        total_slots_count = len(task_slots)

        for t, s in task_slots:
            assigned_emp_id = None
            for emp in self.employees:
                eid = emp['id']
                if (t['id'], s, eid) in X and solver.Value(X[(t['id'], s, eid)]) == 1:
                    assigned_emp_id = eid
                    assigned_slots_count += 1
                    break

            if assigned_emp_id:
                emp = self.emp_by_id[assigned_emp_id]
                req_skill_id = t.get('required_skill_id')
                skill_name = self.skills.get(req_skill_id, 'General') if req_skill_id else 'None Required'
                prof = self.emp_skills_map.get(assigned_emp_id, {}).get(req_skill_id, 'Standard')

                assignments.append({
                    'task_id': t['id'],
                    'task_code': t.get('task_code') or f"TSK-{t['id']}",
                    'title': t['title'],
                    'slot_index': s,
                    'shift_type': t.get('shift_type', 'Morning'),
                    'day_of_week': int(t['day_of_week']),
                    'start_time': t['start_time'],
                    'end_time': t['end_time'],
                    'duration_hours': float(t.get('duration_hours', 0.0)),
                    'priority': int(t.get('priority', 1)),
                    'employee_id': assigned_emp_id,
                    'employee_name': emp['name'],
                    'employee_code': emp['employee_code'],
                    'employee_role': emp['role'],
                    'matched_skill': skill_name,
                    'proficiency': prof
                })

        # Generate root-cause conflict explanations for unassigned slots
        unassigned_tasks = self._diagnose_unassigned_tasks(assignments)

        # Calculate employee workload statistics
        workload_stats, fairness_score = self._compute_workload_stats(assignments)

        return {
            'solver_engine': 'Google OR-Tools CP-SAT (Constraint Satisfaction)',
            'status': status_name,
            'is_feasible': status in (cp_model.OPTIMAL, cp_model.FEASIBLE),
            'solve_time_seconds': round(solve_duration, 3),
            'total_tasks': len(self.tasks),
            'total_slots': total_slots_count,
            'assigned_slots': assigned_slots_count,
            'unassigned_slots': total_slots_count - assigned_slots_count,
            'fulfillment_rate': round((assigned_slots_count / total_slots_count * 100) if total_slots_count > 0 else 0, 1),
            'fairness_score': fairness_score,
            'assignments': assignments,
            'unassigned_tasks': unassigned_tasks,
            'workload_stats': workload_stats
        }

    def _solve_backtracking(self) -> Dict[str, Any]:
        """Pure-Python CSP backtracking solver with Minimum Remaining Values (MRV) & Forward Checking."""
        start_time = datetime.now()
        task_slots = []
        for t in self.tasks:
            req_staff = max(1, int(t.get('min_staff') or 1))
            for s in range(req_staff):
                task_slots.append((t, s))

        # Filter initial domains
        domains = {}
        for t, s in task_slots:
            key = (t['id'], s)
            req_skill = t.get('required_skill_id')
            t_day = int(t['day_of_week'])
            t_start = parse_time_to_minutes(t['start_time'])
            t_end = parse_time_to_minutes(t['end_time'])

            candidates = []
            for emp in self.employees:
                eid = emp['id']
                if emp.get('is_active', 1) != 1:
                    continue
                if not self.is_employee_skill_qualified(eid, req_skill):
                    continue
                if not self.is_employee_available(eid, t_day, t_start, t_end):
                    continue
                candidates.append(eid)
            domains[key] = candidates

        current_assignments = {}
        emp_hours = {e['id']: 0.0 for e in self.employees}
        emp_tasks = {e['id']: [] for e in self.employees}

        def backtrack(unassigned_keys):
            if not unassigned_keys:
                return True

            # MRV heuristic: choose variable with smallest domain
            var = min(unassigned_keys, key=lambda k: len(domains[k]))
            remaining = [k for k in unassigned_keys if k != var]
            t, s = next((item[0], item[1]) for item in task_slots if (item[0]['id'], item[1]) == var)
            dur = float(t.get('duration_hours') or 0.0)
            day = int(t['day_of_week'])
            start_m = parse_time_to_minutes(t['start_time'])
            end_m = parse_time_to_minutes(t['end_time'])

            # Sort candidate employees by least deviation from target hours (fairness heuristic)
            candidates = sorted(
                domains[var],
                key=lambda eid: abs((emp_hours[eid] + dur) - float(self.emp_by_id[eid].get('target_weekly_hours', 35.0)))
            )

            for eid in candidates:
                emp = self.emp_by_id[eid]
                max_h = float(emp.get('max_weekly_hours') or self.default_max_hours)

                # Check max hours constraint
                if emp_hours[eid] + dur > max_h:
                    continue

                # Check double booking on same task
                already_in_task = any(k[0] == t['id'] and v == eid for k, v in current_assignments.items())
                if already_in_task:
                    continue

                # Check overlap and rest periods with existing assignments for this employee
                conflict = False
                for prev_t in emp_tasks[eid]:
                    p_day = int(prev_t['day_of_week'])
                    p_start = parse_time_to_minutes(prev_t['start_time'])
                    p_end = parse_time_to_minutes(prev_t['end_time'])

                    if p_day == day and time_intervals_overlap(start_m, end_m, p_start, p_end):
                        conflict = True
                        break
                    if rest_period_violated(p_day, p_end, day, start_m, self.min_rest_minutes) or \
                       rest_period_violated(day, end_m, p_day, p_start, self.min_rest_minutes):
                        conflict = True
                        break
                if conflict:
                    continue

                # Assign
                current_assignments[var] = eid
                emp_hours[eid] += dur
                emp_tasks[eid].append(t)

                if backtrack(remaining):
                    return True

                # Undo
                del current_assignments[var]
                emp_hours[eid] -= dur
                emp_tasks[eid].pop()

            return False

        all_keys = [(t['id'], s) for t, s in task_slots]
        backtrack(all_keys)

        solve_duration = (datetime.now() - start_time).total_seconds()
        assignments = []
        for (t_id, s), eid in current_assignments.items():
            t = next(task for task in self.tasks if task['id'] == t_id)
            emp = self.emp_by_id[eid]
            req_skill_id = t.get('required_skill_id')
            skill_name = self.skills.get(req_skill_id, 'General') if req_skill_id else 'None Required'
            prof = self.emp_skills_map.get(eid, {}).get(req_skill_id, 'Standard')

            assignments.append({
                'task_id': t['id'],
                'task_code': t.get('task_code') or f"TSK-{t['id']}",
                'title': t['title'],
                'slot_index': s,
                'shift_type': t.get('shift_type', 'Morning'),
                'day_of_week': int(t['day_of_week']),
                'start_time': t['start_time'],
                'end_time': t['end_time'],
                'duration_hours': float(t.get('duration_hours', 0.0)),
                'priority': int(t.get('priority', 1)),
                'employee_id': eid,
                'employee_name': emp['name'],
                'employee_code': emp['employee_code'],
                'employee_role': emp['role'],
                'matched_skill': skill_name,
                'proficiency': prof
            })

        unassigned_tasks = self._diagnose_unassigned_tasks(assignments)
        workload_stats, fairness_score = self._compute_workload_stats(assignments)

        return {
            'solver_engine': 'Pure-Python CSP Backtracking with MRV & Forward Checking',
            'status': 'COMPLETED',
            'is_feasible': len(assignments) == len(task_slots),
            'solve_time_seconds': round(solve_duration, 3),
            'total_tasks': len(self.tasks),
            'total_slots': len(task_slots),
            'assigned_slots': len(assignments),
            'unassigned_slots': len(task_slots) - len(assignments),
            'fulfillment_rate': round((len(assignments) / len(task_slots) * 100) if task_slots else 0, 1),
            'fairness_score': fairness_score,
            'assignments': assignments,
            'unassigned_tasks': unassigned_tasks,
            'workload_stats': workload_stats
        }

    def _diagnose_unassigned_tasks(self, assignments: List[Dict]) -> List[Dict]:
        """Performs constraint relaxation / root-cause diagnosis for any unfilled task slots."""
        assigned_slot_keys = {(a['task_id'], a['slot_index']) for a in assignments}
        unassigned = []

        for t in self.tasks:
            req_staff = max(1, int(t.get('min_staff') or 1))
            for s in range(req_staff):
                if (t['id'], s) in assigned_slot_keys:
                    continue

                req_skill_id = t.get('required_skill_id')
                skill_name = self.skills.get(req_skill_id, 'None') if req_skill_id else None
                t_day = int(t['day_of_week'])
                t_start = parse_time_to_minutes(t['start_time'])
                t_end = parse_time_to_minutes(t['end_time'])
                t_dur = float(t.get('duration_hours', 0.0))

                reasons = []

                # 1. Check skill qualification
                qualified_emps = [e for e in self.employees if self.is_employee_skill_qualified(e['id'], req_skill_id) and e.get('is_active', 1) == 1]
                if req_skill_id and not qualified_emps:
                    reasons.append(f"Missing Skill: No active employee possesses required skill '{skill_name}'.")
                else:
                    # 2. Check availability among qualified
                    available_emps = [e for e in qualified_emps if self.is_employee_available(e['id'], t_day, t_start, t_end)]
                    if not available_emps:
                        emp_names = ", ".join([e['name'] for e in qualified_emps[:3]])
                        reasons.append(f"Availability Conflict: Qualified employee(s) ({emp_names}) are marked unavailable during {t['start_time']}-{t['end_time']} on day {t_day}.")
                    else:
                        # 3. Check for overlaps, rest periods, or max hours
                        overlap_emps = []
                        rest_emps = []
                        max_hour_emps = []

                        for emp in available_emps:
                            eid = emp['id']
                            max_h = float(emp.get('max_weekly_hours') or self.default_max_hours)
                            cur_hours = sum(a['duration_hours'] for a in assignments if a['employee_id'] == eid)

                            if cur_hours + t_dur > max_h:
                                max_hour_emps.append(emp['name'])

                            for a in assignments:
                                if a['employee_id'] == eid:
                                    a_day = int(a['day_of_week'])
                                    a_start = parse_time_to_minutes(a['start_time'])
                                    a_end = parse_time_to_minutes(a['end_time'])

                                    if a_day == t_day and time_intervals_overlap(t_start, t_end, a_start, a_end):
                                        overlap_emps.append(f"{emp['name']} (assigned to {a['title']})")
                                    if rest_period_violated(a_day, a_end, t_day, t_start, self.min_rest_minutes) or \
                                       rest_period_violated(t_day, t_end, a_day, a_start, self.min_rest_minutes):
                                        rest_emps.append(f"{emp['name']} (insufficient rest after {a['title']})")

                        if overlap_emps:
                            reasons.append(f"Time Overlap: All qualified and available staff have conflicting overlapping assignments: {', '.join(set(overlap_emps[:2]))}.")
                        if rest_emps:
                            reasons.append(f"Rest Period Violation: Violates the mandatory {self.min_rest_hours}h rest window for: {', '.join(set(rest_emps[:2]))}.")
                        if max_hour_emps:
                            reasons.append(f"Max Weekly Hours Exceeded: Staff reached their weekly hour ceiling: {', '.join(set(max_hour_emps[:2]))}.")

                if not reasons:
                    reasons.append("Staff Capacity Constraint: All eligible workers were occupied on higher priority assignments.")

                unassigned.append({
                    'task_id': t['id'],
                    'task_code': t.get('task_code') or f"TSK-{t['id']}",
                    'title': t['title'],
                    'slot_index': s,
                    'shift_type': t.get('shift_type', 'Morning'),
                    'day_of_week': t_day,
                    'start_time': t['start_time'],
                    'end_time': t['end_time'],
                    'duration_hours': t_dur,
                    'priority': int(t.get('priority', 1)),
                    'required_skill': skill_name or 'None',
                    'reasons': reasons
                })

        return unassigned

    def _compute_workload_stats(self, assignments: List[Dict]) -> Tuple[List[Dict], float]:
        """Calculates workload distribution per employee, utilization rates, and fairness score."""
        emp_assigned_hours = {e['id']: 0.0 for e in self.employees}
        emp_task_counts = {e['id']: 0 for e in self.employees}
        emp_night_counts = {e['id']: 0 for e in self.employees}

        for a in assignments:
            eid = a['employee_id']
            emp_assigned_hours[eid] += a['duration_hours']
            emp_task_counts[eid] += 1
            if a.get('shift_type') == 'Night' or parse_time_to_minutes(a['start_time']) >= 1320 or parse_time_to_minutes(a['end_time']) <= 480:
                emp_night_counts[eid] += 1

        stats = []
        hours_list = []

        for emp in self.employees:
            eid = emp['id']
            assigned_h = round(emp_assigned_hours[eid], 1)
            target_h = float(emp.get('target_weekly_hours') or 35.0)
            max_h = float(emp.get('max_weekly_hours') or self.default_max_hours)
            utilization = round((assigned_h / max_h * 100) if max_h > 0 else 0, 1)

            if emp.get('is_active', 1) == 1:
                hours_list.append(assigned_h)

            stats.append({
                'employee_id': eid,
                'employee_name': emp['name'],
                'employee_code': emp['employee_code'],
                'role': emp['role'],
                'assigned_hours': assigned_h,
                'target_hours': target_h,
                'max_hours': max_h,
                'utilization_percent': utilization,
                'assigned_tasks_count': emp_task_counts[eid],
                'night_shifts_count': emp_night_counts[eid],
                'is_active': emp.get('is_active', 1)
            })

        # Calculate Fairness Score: 1.0 - (Normalized Standard Deviation)
        # Score of 100 means completely balanced workload.
        if len(hours_list) > 1 and max(hours_list) > 0:
            mean_h = sum(hours_list) / len(hours_list)
            variance = sum((h - mean_h) ** 2 for h in hours_list) / len(hours_list)
            std_dev = math.sqrt(variance)
            fairness = max(0.0, round(100.0 - (std_dev / (mean_h if mean_h > 0 else 1) * 40.0), 1))
        else:
            fairness = 100.0

        return stats, fairness
