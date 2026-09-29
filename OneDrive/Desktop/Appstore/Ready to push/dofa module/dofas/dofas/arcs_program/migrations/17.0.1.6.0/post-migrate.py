"""arcs.activity.budget_line_id is removed: an Activity now gets its
budget-line context transitively through Project -> Program instead of
holding its own direct link - Program is the single top-of-cascade place a
budget line is chosen, and Planned Cost now correctly cascades all the way
down (Program -> Project -> Activity), each level checked against what its
parent has left once sibling records already planned there are accounted
for (see arcs_program.py/arcs_project.py/arcs_activity.py).

For a database that already has arcs_activity.budget_line_id values set,
dropping the column outright would silently lose that information. This
migration instead does a best-effort backfill first: for every Program
that doesn't yet have its own budget_line_id, if every one of its
activities (across all its projects) that HAD a budget_line_id agree on
the exact same one, adopt it as the Program's - preserving that link at
the level it now belongs. Where activities under one program disagree
(different budget lines picked on different activities), there is no
single correct answer to pick automatically - the program is left without
a budget_line_id in that case, same as any new program, and Finance
should set the right one by hand.

Idempotent and safe to run on a database with no such data at all (a
guarded no-op)."""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'arcs_activity' AND column_name = 'budget_line_id'
    """)
    if not cr.fetchone():
        return  # nothing to migrate - fresh install, or already migrated

    cr.execute("""
        SELECT prog.id, array_agg(DISTINCT act.budget_line_id)
        FROM arcs_activity act
        JOIN arcs_project proj ON proj.id = act.project_id
        JOIN arcs_program prog ON prog.id = proj.program_id
        WHERE act.budget_line_id IS NOT NULL
          AND prog.budget_line_id IS NULL
        GROUP BY prog.id
    """)
    for program_id, line_ids in cr.fetchall():
        if len(line_ids) == 1:
            cr.execute(
                "UPDATE arcs_program SET budget_line_id = %s WHERE id = %s",
                (line_ids[0], program_id))

    cr.execute("ALTER TABLE arcs_activity DROP COLUMN budget_line_id")
