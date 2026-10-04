import sqlite3
import os
from flask import g, current_app
from pathlib import Path

def get_db():
    """Opens a new database connection if there is none yet for the current app context."""
    if 'db' not in g:
        db_path = current_app.config['DATABASE_PATH']
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        g.db = sqlite3.connect(
            str(db_path),
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        # Enable dictionary-like row access
        g.db.row_factory = sqlite3.Row
        # Enforce foreign key constraints
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

def close_db(e=None):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app=None):
    """Initializes database tables using data/schema.sql."""
    if app:
        with app.app_context():
            _execute_init_schema()
    else:
        _execute_init_schema()

def _execute_init_schema():
    """Executes the DDL statements from the schema file."""
    db = get_db()
    schema_path = current_app.config['SCHEMA_PATH']
    with open(schema_path, mode='r', encoding='utf-8') as f:
        db.executescript(f.read())
    db.commit()

def check_db_connection():
    """Checks the SQLite database connectivity, returning health metadata."""
    try:
        db = get_db()
        # Query SQLite version
        version = db.execute("SELECT sqlite_version()").fetchone()[0]
        
        # Get list of existing user tables
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        ).fetchall()
        table_names = [row['name'] for row in tables]
        
        # Count employees and shifts if tables exist
        emp_count = 0
        shift_count = 0
        if 'employees' in table_names:
            emp_count = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        if 'shifts' in table_names:
            shift_count = db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
            
        return {
            "status": "connected",
            "sqlite_version": version,
            "database_path": str(current_app.config['DATABASE_PATH']),
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
            "table_count": 0
        }
