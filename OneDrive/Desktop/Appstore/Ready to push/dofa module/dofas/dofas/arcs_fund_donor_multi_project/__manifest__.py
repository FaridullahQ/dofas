{
    "name": "ARCS Donor Mgmt - One Donor, Multiple Projects",
    "version": "17.0.1.0.0",
    "summary": "Coordinates multiple projects funded under one donor's single grant, so "
               "their combined plans can never exceed what that donor actually approved.",
    "description": """
ARCS One Donor, Multiple Projects
====================================
Implements the fifth ARCS funding-model plug-in: One Donor, Multiple
Projects, where a single donor signs one grant/framework agreement that
funds SEVERAL separate, distinct projects (as opposed to Multi-Donor
Project, which is the mirror image - several donors co-funding ONE shared
project).

Deep-dive finding this module is built around: arcs_program already lets
several arcs.project records share one arcs.grant (grant_id has never been
unique per grant), and already enforces that sibling projects sharing one
arcs.program can never together plan more than that program's own Planned
Cost. But that sharing check only fires when a program_id is actually set -
there was no check at all ensuring that projects placed DIRECTLY under one
grant (the common case for this funding model, where a shared cross-grant
Program often isn't relevant) stay within that grant's own Approved Amount.

This module adds exactly that, as an independent, additional check specific
to funding_model == 'donor_multi_project' - it does not touch, weaken, or
duplicate the existing Program-level sharing logic, which keeps working
unchanged for any project that also happens to have a program_id set.

Also, exactly like arcs_fund_earmarked:
- Requires every expense on such a grant to specify which Project it
  belongs to (arcs.expense.project_id already existed, added by
  arcs_program, and stays optional for every other grant).
- Calls the existing arcs.project.get_available_locked() at expense
  approval time, unconditionally for this funding model.
- Blocks closing the grant while any of its projects isn't Closed yet
  (reusing arcs.project.action_close()'s own existing cascade to its
  activities, unchanged).

No new database tables. Only two hook overrides, one new project-level
constraint, one expense-submit validation, and one optional field (linking
a donor report to a specific project, for donors who want per-project
reporting under their one overall agreement).
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_budget", "arcs_expense", "arcs_program", "arcs_report"],
    "data": [
        "views/arcs_grant_views.xml",
        "views/arcs_expense_views.xml",
        "views/arcs_donor_report_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
