from flask import Flask, render_template
from pathlib import Path
from app.config import config_by_name
from app.database import close_db, init_db

def create_app(config_name='default'):
    """Application factory for the workforce scheduling system."""
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Ensure parent directory for database exists
    Path(app.config['DATABASE_PATH']).parent.mkdir(parents=True, exist_ok=True)

    # Register teardown function to close db connections
    app.teardown_appcontext(close_db)

    # CLI command to initialize database manually
    @app.cli.command('init-db')
    def init_db_command():
        """Initialize the database schema."""
        init_db(app)
        print("Database initialized successfully.")

    # Automatically initialize schema if database file does not exist yet
    db_file = Path(app.config['DATABASE_PATH'])
    if not db_file.exists():
        with app.app_context():
            init_db()

    # Register Blueprints
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html', error=str(e)), 500

    return app
