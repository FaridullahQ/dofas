{
    "name": "ARCS Donor Mgmt - Multi-Donor Project",
    "version": "17.0.1.0.0",
    "summary": "Link several donors' grants as co-funders of one project, and split shared "
               "costs across them by a locked-in, audited percentage key.",
    "description": """
ARCS Multi-Donor Project
==========================
Implements the third ARCS funding-model plug-in (after Revolving Fund and
Reimbursement): the Multi-Donor Project model, where several DIFFERENT
donors co-fund one shared project.

Each donor keeps their own arcs.grant - their own agreement, budget,
expenses, reports, and closure, exactly as for every other funding model.
Nothing about that changes. What's missing without this module is a safe
way to record a SHARED cost (something that benefits more than one donor's
portion of the work) without manually guessing each donor's share and
risking the classic multi-donor accounting mistake: the same cost recorded
in full against more than one donor.

This module adds exactly that, and nothing else:
- arcs.multi.donor.project: links several multi_donor-funding-model grants
  together with a locked-in percentage split (must sum to 100% before the
  project can be activated; locked once any shared cost has been split).
- arcs.multi.donor.shared.cost: enter a shared cost's total ONCE; the
  system generates one draft arcs.expense per member grant, each for
  exactly that member's share (which may override the project's default
  split for that specific cost), mapped to that grant's own budget line.
  The split lines are required to sum to exactly the shared cost's total,
  by construction - so the classic double-charge mistake is structurally
  impossible through this tool, not just discouraged.

Deliberately NOT built here:
- No consolidated cross-donor report. Each donor still only ever sees
  their own arcs.donor.report, off their own grant - unchanged.
- No project-level closure gate. Each member grant closes independently
  on its own donor's timeline; a Multi-Donor Project is a shared-cost
  coordination record, not a governance unit of its own.
- No multi-currency conversion logic. A shared cost is entered in one
  currency; splitting across grants in different currencies is a known
  limitation, not attempted here.
- Since a Multi-Donor grant is is_restricted by definition (not
  Unrestricted), it already gets arcs_grant_governance's agreement-version
  and compliance features for free wherever that module is installed -
  no hard dependency on it was needed to achieve that.
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_budget", "arcs_expense"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_multi_donor_security.xml",
        "data/ir_sequence_data.xml",
        "views/arcs_multi_donor_project_views.xml",
        "views/arcs_multi_donor_shared_cost_views.xml",
        "views/arcs_grant_views.xml",
        "views/arcs_expense_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "auto_install": False,
}
