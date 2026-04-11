from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models import Base

# Supabase Session Pooler uses usernames like "postgres.project_ref".
# SQLAlchemy/psycopg2 can truncate the dot, so we pass the full
# username explicitly via connect_args to prevent that.
_parsed = urlparse(settings.DATABASE_URL)
_connect_args = {}
if _parsed.username and "." in _parsed.username:
    _connect_args["user"] = _parsed.username

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Enable pgvector extension and create tables."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
