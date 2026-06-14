"""Alembic migration helpers for programmatic upgrade / downgrade.

Used by tests and by the future startup hook (lifespan startup teardown
will use run_upgrade to bring the DB to the latest migration on boot).

The helpers work with a SQLAlchemy sync Connection obtained from either
a sync or async engine (via engine.sync_engine.connect() or
connection.run_sync).
"""

from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory


def _build_cfg() -> Config:
    """Build an Alembic Config pointing to the backend alembic.ini."""
    import os

    # Discover backend/ from this file: app/db/migrations.py → app/db/ → app/ → backend/
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ini_path = os.path.join(backend_dir, "alembic.ini")
    cfg = Config(ini_path)

    # Inject the database URL so env.py doesn't try to read .env.
    from app.settings import Settings

    cfg.set_main_option("sqlalchemy.url", Settings().database_url)
    return cfg


def run_upgrade(connection, target_revision: str = "head") -> None:
    """Run alembic upgrade to *target_revision* using the provided sync connection.

    Args:
        connection: a SQLAlchemy :class:`~sqlalchemy.engine.Connection`.
        target_revision: migration revision to upgrade to; defaults to ``"head"``.
    """
    cfg = _build_cfg()
    script = ScriptDirectory.from_config(cfg)

    def _upgrade(rev, context):
        return script._upgrade_revs(target_revision, rev)

    env = EnvironmentContext(cfg, script, fn=_upgrade)
    env.configure(connection=connection)
    env.run_migrations()


def run_downgrade(connection, target_revision: str = "-1") -> None:
    """Run alembic downgrade to *target_revision* using the provided sync connection.

    Args:
        connection: a SQLAlchemy :class:`~sqlalchemy.engine.Connection`.
        target_revision: migration revision to downgrade to; defaults to ``"-1"``.
    """
    cfg = _build_cfg()
    script = ScriptDirectory.from_config(cfg)

    def _downgrade(rev, context):
        return script._downgrade_revs(target_revision, rev)

    env = EnvironmentContext(cfg, script, fn=_downgrade)
    env.configure(connection=connection)
    env.run_migrations()
