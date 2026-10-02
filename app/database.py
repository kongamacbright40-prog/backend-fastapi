from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
#the sqlalchemy is how to talk with the datebase
# SQLite (dev.db) by default; PostgreSQL when DATABASE_URL in .env says so,
# e.g. postgresql+psycopg2://user:password@localhost:5432/smart_classroom
is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if is_sqlite else {},
    # Replaces connections the database server closed (restart, idle timeout).
    pool_pre_ping=not is_sqlite,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()