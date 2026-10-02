"""Move Smart Class from SQLite (dev.db) to PostgreSQL.

Run once from the smart-classroom-api folder (with the venv active):

    python scripts/postgres_setup.py

It asks for the password of the PostgreSQL superuser ("postgres", the one
chosen when installing PostgreSQL / used in pgAdmin), then:

1. creates an app user and a database (default: smart_class / smart_classroom),
2. creates all tables,
3. copies every row from dev.db (accounts, courses, classes, attendance...),
4. writes DATABASE_URL for the app user to .env (other .env lines are kept).

Restart the backend afterwards. To go back to SQLite, remove (or comment out)
the DATABASE_URL line in .env and restart.
"""

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402
from sqlalchemy import create_engine, inspect, select, text  # noqa: E402


def load_models():
    """Registers every table on Base.metadata without starting the app."""
    from app.database import Base
    from app.attendance import models as _attendance  # noqa: F401
    from app.auth import models as _auth  # noqa: F401
    from app.campus import models as _campus  # noqa: F401
    from app.classes import models as _classes  # noqa: F401
    from app.courses import models as _courses  # noqa: F401
    from app.participation import models as _participation  # noqa: F401

    return Base.metadata


def create_role_and_database(args, superuser_password: str, app_password: str) -> None:
    conn = psycopg2.connect(
        host=args.host, port=args.port, user=args.superuser, password=superuser_password, dbname="postgres"
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (args.app_user,))
            if cur.fetchone():
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(args.app_user)),
                    (app_password,),
                )
                print(f"- App user '{args.app_user}' exists: password updated")
            else:
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(args.app_user)),
                    (app_password,),
                )
                print(f"- Created app user '{args.app_user}'")
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.database,))
            if cur.fetchone():
                print(f"- Database '{args.database}' already exists")
            else:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                        sql.Identifier(args.database), sql.Identifier(args.app_user)
                    )
                )
                print(f"- Created database '{args.database}'")
    finally:
        conn.close()


def write_env(env_path: Path, url: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    kept = [line for line in lines if not line.strip().startswith("DATABASE_URL=")]
    kept.append(f"DATABASE_URL={url}")
    env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"- Wrote DATABASE_URL to {env_path}")


def copy_sqlite_data(sqlite_path: Path, url: str, force: bool = False) -> dict:
    """Creates the tables in [url] and copies all rows from the SQLite file.
    Returns {table: rows copied}."""
    metadata = load_models()
    target = create_engine(url)
    metadata.create_all(bind=target)

    with target.connect() as conn:
        filled = [t.name for t in metadata.sorted_tables if conn.execute(select(t).limit(1)).first()]
    if filled and not force:
        raise SystemExit(
            f"PostgreSQL already has data in {', '.join(filled)}; nothing copied. "
            "Use --force to empty those tables and copy again."
        )

    source = create_engine(f"sqlite:///{sqlite_path}")
    source_inspector = inspect(source)
    source_tables = set(source_inspector.get_table_names())
    copied: dict[str, int] = {}
    with source.connect() as src, target.begin() as dst:
        if force:
            for table in reversed(metadata.sorted_tables):
                dst.execute(table.delete())
        for table in metadata.sorted_tables:
            if table.name not in source_tables:
                continue
            # Only columns the SQLite file has; newer ones get their defaults.
            present = {c["name"] for c in source_inspector.get_columns(table.name)}
            columns = [c for c in table.columns if c.name in present]
            rows = [dict(r._mapping) for r in src.execute(select(*columns))]
            for i in range(0, len(rows), 500):
                dst.execute(table.insert(), rows[i : i + 500])
            copied[table.name] = len(rows)
        # Continue numbering after the copied ids.
        for table in metadata.sorted_tables:
            if "id" in table.columns and table.columns["id"].primary_key:
                dst.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 1), "
                        f"(SELECT MAX(id) FROM \"{table.name}\") IS NOT NULL)"
                    )
                )
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default="5432")
    parser.add_argument("--superuser", default="postgres")
    parser.add_argument("--database", default="smart_classroom")
    parser.add_argument("--app-user", default="smart_class")
    parser.add_argument("--sqlite", default=str(ROOT / "dev.db"), help="SQLite file to copy from")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--skip-copy", action="store_true", help="Create the database but copy no data")
    parser.add_argument("--force", action="store_true", help="Replace data already in PostgreSQL")
    parser.add_argument(
        "--show-password",
        action="store_true",
        help="Show the password while typing (the normal prompt shows nothing)",
    )
    args = parser.parse_args()

    superuser_password = os.environ.get("PG_SUPERUSER_PASSWORD")
    if not superuser_password:
        prompt = f"Password of PostgreSQL user '{args.superuser}': "
        if args.show_password or not sys.stdin.isatty():
            superuser_password = input(prompt)
        else:
            print("(Nothing appears while you type the password; type it and press Enter.)")
            superuser_password = getpass.getpass(prompt)
    superuser_password = superuser_password.strip("\r\n")
    app_password = secrets.token_urlsafe(18)

    print("Setting up PostgreSQL...")
    try:
        create_role_and_database(args, superuser_password, app_password)
    except psycopg2.OperationalError as e:
        if "password authentication failed" in str(e):
            raise SystemExit(
                f"Wrong password for PostgreSQL user '{args.superuser}'. Use the password you "
                "chose when installing PostgreSQL (the one pgAdmin asks for), then run this again."
            )
        raise SystemExit(f"Could not connect to PostgreSQL on {args.host}:{args.port}: {e}")
    url = (
        f"postgresql+psycopg2://{quote_plus(args.app_user)}:{quote_plus(app_password)}"
        f"@{args.host}:{args.port}/{quote_plus(args.database)}"
    )
    if args.skip_copy:
        load_models().create_all(bind=create_engine(url))
        print("- Created tables (no data copied)")
    else:
        sqlite_path = Path(args.sqlite)
        if not sqlite_path.exists():
            raise SystemExit(f"SQLite file not found: {sqlite_path}")
        copied = copy_sqlite_data(sqlite_path, url, force=args.force)
        print(f"- Copied {sum(copied.values())} rows from {sqlite_path.name}:")
        for name, count in copied.items():
            if count:
                print(f"    {name}: {count}")
    write_env(Path(args.env_file), url)
    print("Done. Restart the backend (uvicorn) to use PostgreSQL.")


if __name__ == "__main__":
    main()
