{
    "name": "ARCS Donor Mgmt - Earmarked",
    "version": "17.0.1.0.0",
    "summary": "Wires up the existing (but previously unconnected) Activity-level ceiling "
               "check as a mandatory guarantee for grants on the Earmarked funding "
               "model - the donor's money can only ever be spent on the named activity.",
    "description": """
ARCS Earmarked
================
Implements the fourth ARCS funding-model plug-in (after Revolving Fund,
Reimbursement, and Multi-Donor Project): Earmarked funding, where the donor
restricts use of funds to a specific, named activity or purpose - the
strictest ("hard") form of restriction, as distinct from a Grant Based
grant's broader agreement-level conditions.

Deep-dive finding this module is built around: arcs_program already ships
almost the entire mechanism this needs. arcs.activity (and arcs.project,
arcs.program above it) already have their own Planned Cost ceiling and a
concurrency-safe get_available_locked() method, and a company-wide setting
(arcs_enforce_program_ceilings) already exists to gate whether that ceiling
is checked. What was missing: nothing in arcs_budget or arcs_expense ever
actually CALLS get_available_locked() - the setting and the availability
math were built, but never wired to anything, and even if they had been,
enforcement would be a global, optional, all-grants-or-none toggle, not a
guarantee specific to grants that actually promised a donor hard earmarking.

This module deliberately does NOT rebuild any of that - it only:
- Requires every expense on an Earmarked grant to specify an Activity
  (arcs.expense.activity_id already existed, added by arcs_program, and was
  optional for every OTHER grant; it stays optional for them - this module
  only makes it required when funding_model == 'earmarked').
- Calls the EXISTING arcs.activity.get_available_locked() at expense
  approval time for Earmarked grants specifically, UNCONDITIONALLY -
  regardless of the global arcs_enforce_program_ceilings setting, since for
  this funding model the ceiling isn't an optional nice-to-have, it's the
  donor's actual condition. Every other funding model's behavior around
  that global setting is completely unchanged.
- Blocks closing an Earmarked grant while any of its arcs.project records
  isn't Closed yet (which itself already correctly cascades to requiring
  every one of that project's activities be Closed too - unchanged,
  reused verbatim from arcs_program).

No new database tables. No changes to arcs_program, arcs_budget, or
arcs_expense's own files - only two hook overrides (reusing the extension
points already sitting in arcs_grant core since Revolving Fund) and one
expense-submit validation.
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_budget", "arcs_expense", "arcs_program"],
    "data": [
        "views/arcs_expense_views.xml",
        "views/arcs_grant_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
