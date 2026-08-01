"""
One-off, idempotent migration adding customers.contact_title -- see
database/models.py's Customer.contact_title docstring for why this exists
(a human-selected salutation, kept separate from contact_person, instead
of the quotation letter guessing a title from a name). Same raw
ALTER-TABLE approach as migrate_phase_c.py: no Alembic, just one additive
change to apply to the already-created Supabase tables. Safe to run more
than once.

Usage:
    python -m database.migrate_phase_d
"""

from sqlalchemy import text

from database.session import engine

STATEMENTS = [
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS contact_title TEXT",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for statement in STATEMENTS:
            print(f"> {statement}")
            conn.execute(text(statement))
    print("Phase D migration applied.")
