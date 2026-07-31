"""
One-off script to create the three tables on the real Supabase Postgres
instance. Not Alembic -- there's no migration history to manage yet, and
a solo developer under time pressure doesn't need migration tooling for
a schema that hasn't shipped once. If the schema needs to change after
real data exists in it, that's the point to introduce Alembic; doing it
now would be building for a problem that doesn't exist yet.

Usage:
    python -m database.init_db
"""

from database.models import Base
from database.session import engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print(f"Tables created (or already present) on {engine.url.database}.")
