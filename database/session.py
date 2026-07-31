"""
Connects to the Supabase Postgres instance using the DATABASE_URL
environment variable. Never hardcode credentials here.

Importing this module means "I actually want to talk to the database",
so it fails loudly and immediately if DATABASE_URL isn't set, rather than
leaving a None engine that would produce a confusing error later. Code
that only needs the table definitions (e.g. tests against sqlite) should
import from database.models directly instead of importing this module.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill in the "
        "Supabase Postgres connection string."
    )

# pool_pre_ping checks each connection before use -- Supabase's free tier
# can drop idle connections, and this avoids surfacing a stale-connection
# error to an API caller.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency: yields a Session, always closes it afterward."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
