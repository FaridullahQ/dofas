"""arcs.department (a standalone geo/org model owned entirely by arcs_zone)
is replaced by a first-class hr.department extension (zone_id + code added
directly onto the real HR model) - hr.department, not a parallel model, is
now the single source of truth for departments, matching how every other
DoFAS dimension already reuses a real Odoo model (arcs.zone reuses nothing
new here, but the acquisition workflow already reuses hr.employee for
'Requested By' the same way) instead of reinventing one.

For a database that already has arcs.department records, dropping the old
model out from under them would silently orphan every arcs.expense and
arcs.spend.request that pointed at one. This migration instead:

  1. Creates one hr.department row per surviving arcs.department row,
     carrying over name/code/company_id/zone_id/active. manager_id is
     remapped from the old res.users manager to that user's hr.employee
     record - the same res.users -> hr.employee remap
     arcs_request/migrations/17.0.1.9.0 already used for 'Requested By';
     there is no other reliable mapping, and a manager with no matching
     hr.employee is simply left blank (same fallback as that migration).
  2. Repoints every arcs_expense.department_id and arcs_spend_request.
     department_id foreign key from the old arcs_department.id to the new
     hr_department.id.
  3. Drops the now-empty arcs_department table, together with its own
     ir.model / ir.model.fields / ir.model.data bookkeeping, so nothing in
     the registry keeps tracking a model no longer declared by any module.

Idempotent and safe to run on a database with no arcs.department data at
all, or one already migrated (every step is a guarded no-op in that case)."""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.tables WHERE table_name = 'arcs_department'
    """)
    if not cr.fetchone():
        return  # nothing to migrate - fresh install, or already migrated

    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_department' AND column_name IN ('zone_id', 'code')
    """)
    if len(cr.fetchall()) < 2:
        # The new columns aren't there yet - this migration must run after
        # the ORM's own schema update for this module. Bail out rather than
        # guess; nothing destructive has happened yet either way.
        return

    cr.execute("""
        SELECT id, name, code, company_id, zone_id, manager_id, active
        FROM arcs_department
    """)
    old_rows = cr.fetchall()

    id_map = {}  # old arcs_department.id -> new hr_department.id
    for old_id, name, code, company_id, zone_id, manager_id, active in old_rows:
        employee_id = None
        if manager_id:
            cr.execute("SELECT id FROM hr_employee WHERE user_id = %s LIMIT 1", (manager_id,))
            row = cr.fetchone()
            employee_id = row[0] if row else None
        cr.execute("""
            INSERT INTO hr_department (name, code, company_id, zone_id, manager_id, active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, code, company_id, zone_id, employee_id, active))
        id_map[old_id] = cr.fetchone()[0]

    for old_id, new_id in id_map.items():
        cr.execute("UPDATE arcs_expense SET department_id = %s WHERE department_id = %s",
                   (new_id, old_id))
        cr.execute("""
            SELECT 1 FROM information_schema.tables WHERE table_name = 'arcs_spend_request'
        """)
        if cr.fetchone():
            cr.execute(
                "UPDATE arcs_spend_request SET department_id = %s WHERE department_id = %s",
                (new_id, old_id))

    # Clean up the old model's registry bookkeeping before dropping its
    # table, so a later module update never trips over a dangling ir.model /
    # ir.model.fields entry for a model no longer declared anywhere.
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE (model = 'ir.model' AND res_id IN (
                  SELECT id FROM ir_model WHERE model = 'arcs.department'))
           OR (model = 'ir.model.fields' AND res_id IN (
                  SELECT id FROM ir_model_fields WHERE model = 'arcs.department'))
           OR (model = 'arcs.department')
    """)
    cr.execute("DELETE FROM ir_model_fields WHERE model = 'arcs.department'")
    cr.execute("DELETE FROM ir_model WHERE model = 'arcs.department'")
    cr.execute("DROP TABLE IF EXISTS arcs_department CASCADE")
