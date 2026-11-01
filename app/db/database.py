from urllib.parse import urlparse, unquote

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models import Base


# SQLAlchemy 2.1 changed the default DBAPI for the bare "postgresql://" scheme
# from psycopg2 to psycopg (v3). We ship psycopg2-binary, so name the driver
# explicitly to keep behaviour identical on both 2.0 and 2.1.
def _with_psycopg2(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


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
            sslmode="require",
        )
    engine = create_engine("postgresql+psycopg2://", creator=_create_connection)
else:
    engine = create_engine(_with_psycopg2(settings.DATABASE_URL))
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
