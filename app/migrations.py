"""Tiny schema upgrader for databases created before new columns existed.

The app uses ``Base.metadata.create_all`` (no Alembic), which creates missing
tables but never adds columns to existing ones. ``add_missing_columns`` adds
any model column that is missing from an existing table, so an old
``dev.db`` keeps working after an upgrade. Only additive changes are handled.
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
