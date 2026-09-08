"""arcs.fund.receipt.allocation gains an Activity level and is now
auto-generated (Program -> Project -> Activity, each with its own Planned
Cost) instead of hand-entered as a flat Program/Project split - see
arcs_fund_receipt.py's _build_allocation_vals/action_refresh_program_
allocation. Two schema changes need help from a migration:

1. `level` is a new REQUIRED field. Odoo's own schema update only adds the
   NOT NULL constraint for a required field - it does not backfill
   existing rows with a sensible value first (there's no static default
   that would be correct here; it depends on whether project_id was set).
   Running this as a PRE-migrate (before the module's own _auto_init
   enforces NOT NULL) adds the column and backfills it from existing data,
   so by the time the real schema update runs, every row already has a
   valid value and the NOT NULL constraint applies cleanly.

2. The old `amount_positive` CHECK(amount > 0) constraint no longer
   applies - a Program/Project/Activity that hasn't been planned yet
   legitimately has a Planned Cost of 0, and the auto-generator includes
   it anyway (for full transparency: "all the programs, relevant
   projects, and relevant activities", not just the ones already costed).
   Removing an entry from `_sql_constraints` in Python does not drop the
   constraint Odoo already created in the database - that has to be done
   explicitly.

Idempotent and safe to run on a fresh install (both guarded).
"""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'arcs_fund_receipt_allocation' AND column_name = 'level'
    """)
    if not cr.fetchone():
        cr.execute("ALTER TABLE arcs_fund_receipt_allocation ADD COLUMN level VARCHAR")
        cr.execute("""
            UPDATE arcs_fund_receipt_allocation
            SET level = CASE WHEN project_id IS NOT NULL THEN 'project' ELSE 'program' END
            WHERE level IS NULL
        """)

    cr.execute("""
        ALTER TABLE arcs_fund_receipt_allocation
        DROP CONSTRAINT IF EXISTS arcs_fund_receipt_allocation_amount_positive
    """)
