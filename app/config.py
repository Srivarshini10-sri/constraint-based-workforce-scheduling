import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-workforce-scheduler-secret-key-2026')
    
    # SQLite Database location
    DATA_DIR = BASE_DIR / 'data'
    DATABASE_PATH = DATA_DIR / 'workforce.db'
    SCHEMA_PATH = DATA_DIR / 'schema.sql'

    # Default Constraint-Based Scheduling Rules
    DEFAULT_MIN_REST_HOURS = 11.0
    DEFAULT_MAX_WEEKLY_HOURS = 40.0
    DEFAULT_MAX_CONSECUTIVE_DAYS = 6

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    DATABASE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'test_workforce.db'

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
