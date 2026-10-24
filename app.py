"""Application factory for the Lúmen store.

Run it with the standard Flask CLI::

    flask --app app init-db
    flask --app app seed
    flask --app app run
"""

import os
from pathlib import Path

import click
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine

from models import db
from routes import main
from security import init_security
from seed import seed_database

DATABASE_FILENAME = "parcial2.db"
SECRET_KEY_ENV = "SECRET_KEY"
DEFAULT_SECRET_KEY = "dev-secret-key-change-me"


def _enable_sqlite_foreign_keys(engine):
    """Enable SQLite foreign key enforcement for a connection."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_app(test_config=None):
    """Build and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    database_path = Path(app.instance_path) / DATABASE_FILENAME
    app.config.from_mapping(
        SECRET_KEY=os.environ.get(SECRET_KEY_ENV, DEFAULT_SECRET_KEY),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", f"sqlite:///{database_path}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    # The override is applied before init_app so tests can swap the database.
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    init_security(app)
    app.register_blueprint(main)

    with app.app_context():
        _enable_sqlite_foreign_keys(db.engine)

    register_cli(app)

    return app


def register_cli(app):
    """Attach the database bootstrap commands to the application."""

    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables."""
        db.create_all()
        click.echo(
            f"Database initialized: {app.config['SQLALCHEMY_DATABASE_URI']}"
        )

    @app.cli.command("seed")
    def seed_command():
        """Insert the original catalog (idempotent)."""
        inserted, skipped = seed_database()
        click.echo(f"Seeding complete: {inserted} inserted, {skipped} skipped.")


app = create_app()
