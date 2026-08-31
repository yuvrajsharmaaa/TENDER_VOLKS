import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import settings

# Initialize SQL engine and SessionLocal
db_url = os.getenv("DATABASE_URL") or settings.database_url
engine = create_engine(db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    FastAPI dependency yielding a database session and closing it on completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
