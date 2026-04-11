from urllib.parse import urlparse, unquote

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models import Base

# Supabase Session Pooler uses usernames like "postgres.project_ref".
# SQLAlchemy/psycopg2 URL parsing truncates the dot, so we bypass it
# entirely by constructing psycopg2 connections manually.
_parsed = urlparse(settings.DATABASE_URL)

if _parsed.username and "." in _parsed.username:
    def _create_connection():
        return psycopg2.connect(
            host=_parsed.hostname,
            port=_parsed.port or 5432,
            user=unquote(_parsed.username),
            password=unquote(_parsed.password or ""),
            dbname=_parsed.path.lstrip("/") or "postgres",
        )
    engine = create_engine("postgresql://", creator=_create_connection)
else:
    engine = create_engine(settings.DATABASE_URL)
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
