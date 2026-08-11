"""requested_by on arcs.spend.request changes from a Many2one to res.users to
a Many2one to hr.employee (the acquisition is now tied to the actual staff
member the approved amount is later disbursed to as a cash advance, not just
their login). Existing values in the requested_by column are res.users ids;
if the ORM's automatic schema management is left to add the new hr.employee
foreign key straight over them, a res.users id and an hr.employee id are
unrelated integer sequences that can coincidentally reference the WRONG
record (or fail the constraint outright). Renaming the raw column out of the
way here, before the new field is set up, preserves every existing value so
post-migrate can safely remap it to the matching hr.employee (by that
employee's linked user) instead of silently losing or corrupting it."""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'arcs_spend_request' AND column_name = 'requested_by'
    """)
    if cr.fetchone():
        cr.execute("""
            ALTER TABLE arcs_spend_request
            RENAME COLUMN requested_by TO requested_by_user_id_old
        """)
