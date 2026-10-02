"""Schema helpers.

PostgreSQL databases are managed with Alembic (``alembic upgrade head``,
migrations in ``alembic/versions``). For SQLite (tests and quick local runs)
the app creates tables with ``create_all`` and ``add_missing_columns`` adds
model columns missing from an existing table (additive changes only).
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.elements import ClauseElement

from app.database import Base


def _column_ddl(engine: Engine, column) -> str:
    col_type = column.type.compile(dialect=engine.dialect)
    ddl = f'"{column.name}" {col_type}'
    default = column.server_default
    if default is not None and hasattr(default, "arg"):
        arg = default.arg
        if hasattr(arg, "text"):
            value = arg.text
        elif isinstance(arg, ClauseElement):
            # e.g. sqlalchemy.true(): "1" on SQLite, "true" on PostgreSQL.
            value = str(arg.compile(dialect=engine.dialect))
        else:
            value = str(arg)
        ddl += f" DEFAULT {value}"
        if not column.nullable:
            ddl += " NOT NULL"
    return ddl


def warn_if_not_migrated(engine: Engine) -> None:
    """Logs a warning when the database is not at the newest Alembic revision
    (run `alembic upgrade head`)."""
    import logging
    from pathlib import Path

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    logger = logging.getLogger("smart_class")
    try:
        root = Path(__file__).resolve().parent.parent
        script = ScriptDirectory.from_config(Config(str(root / "alembic.ini")))
        with engine.connect() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
        if current != set(script.get_heads()):
            logger.warning(
                "Database schema is not up to date (at %s, newest is %s). Run: alembic upgrade head",
                ", ".join(sorted(current)) or "nothing",
                ", ".join(script.get_heads()),
            )
    except Exception as e:  # never block startup because of this check
        logger.warning("Could not check database migrations: %s", e)


def add_missing_columns(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN {_column_ddl(engine, column)}')
                )
                added.append(f"{table.name}.{column.name}")
    return added
