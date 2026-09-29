import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.core.config import settings


db_url = os.getenv("DATABASE_URL") or settings.DATABASE_URL

if not db_url:
    raise RuntimeError("DATABASE_URL is not configured.")


# Force the project to use the installed psycopg2 driver.
#
# SQLAlchemy may otherwise resolve a plain postgresql:// URL
# to the psycopg (v3) dialect.
if db_url.startswith("postgresql+psycopg://"):
    db_url = db_url.replace(
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
        1,
    )
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1,
    )


engine = create_engine(
    db_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency yielding a database session
    and closing it on completion.
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
