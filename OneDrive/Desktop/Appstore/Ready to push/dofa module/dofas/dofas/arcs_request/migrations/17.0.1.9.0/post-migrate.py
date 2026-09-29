"""Remap the preserved old requested_by (a res.users id, saved off by
pre-migrate) to the matching hr.employee - found by that employee's own
linked user - then drop the old column. An acquisition whose requester has
no hr.employee record at all (e.g. this deployment never linked users to
employees before this upgrade) is left with an empty Requested By: there is
no reliable way to invent an employee record for them, and it needs the same
manual follow-up either way. Check 'Requested By' on older acquisitions
after this upgrade if the company hasn't been using the Employees app."""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'arcs_spend_request' AND column_name = 'requested_by_user_id_old'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE arcs_spend_request AS r
        SET requested_by = e.id
        FROM hr_employee AS e
        WHERE e.user_id = r.requested_by_user_id_old
          AND r.requested_by IS NULL
    """)
    cr.execute("ALTER TABLE arcs_spend_request DROP COLUMN requested_by_user_id_old")
