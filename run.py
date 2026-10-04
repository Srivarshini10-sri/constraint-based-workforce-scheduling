import os
import sys
from pathlib import Path
import importlib.util

BASE_DIR = Path(__file__).resolve().parent
app_py_path = BASE_DIR / 'app.py'
spec = importlib.util.spec_from_file_location("main_app_entry", str(app_py_path))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app

if __name__ == '__main__':
    print("=" * 70)
    print(" Constraint-Based Intelligent Workforce Scheduling")
    print(" and Fair Workload Optimization System")
    print("=" * 70)
    print(" Running on http://127.0.0.1:5000")
    print(" Database: SQLite 3")
    print("=" * 70)
    app.run(host='127.0.0.1', port=5000, debug=True)
