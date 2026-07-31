"""
One-off, idempotent migration for the columns/status values the Phase C
dashboard needs that didn't exist when Phase A's schema was first written
(see database/models.py for why each one was added). Like init_db.py, this
is deliberately raw ALTER TABLE, not Alembic -- there's still no migration
history to manage, just one additive change to apply to the already-created
Supabase tables. Safe to run more than once.

Usage:
    python -m database.migrate_phase_c
"""

from sqlalchemy import text

from database.session import engine

STATEMENTS = [
    "ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS requirement_details TEXT",
    "ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS expected_timeline TEXT",
    "ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS budget_range TEXT",
    "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS notes TEXT",
    # Widen status to fit "needs_manual_pricing" (21 chars), then replace
    # the CHECK constraint to allow the two new values (rejected,
    # needs_manual_pricing) alongside the original five.
    "ALTER TABLE quotations ALTER COLUMN status TYPE VARCHAR(21)",
    "ALTER TABLE quotations DROP CONSTRAINT IF EXISTS quotation_status",
    "ALTER TABLE quotations ADD CONSTRAINT quotation_status CHECK "
    "(status IN ('draft', 'sent', 'won', 'lost', 'no_response', 'rejected', 'needs_manual_pricing'))",
    # enquiries.status: "processed" is replaced by quoted/closed_won/
    # closed_lost (see database/models.py's EnquiryStatus docstring). The
    # table was empty when this migration was written, so there's no
    # existing "processed" data to remap -- if that's no longer true, remap
    # it before dropping the old constraint.
    "ALTER TABLE enquiries DROP CONSTRAINT IF EXISTS enquiry_status",
    "ALTER TABLE enquiries ADD CONSTRAINT enquiry_status CHECK "
    "(status IN ('new', 'needs_review', 'quoted', 'closed_won', 'closed_lost'))",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for statement in STATEMENTS:
            print(f"> {statement}")
            conn.execute(text(statement))
    print("Phase C migration applied.")
