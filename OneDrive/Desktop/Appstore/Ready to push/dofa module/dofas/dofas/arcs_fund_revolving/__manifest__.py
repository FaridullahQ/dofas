{
    "name": "ARCS Donor Mgmt - Revolving Fund",
    "version": "17.0.1.0.0",
    "summary": "Revolving Fund cycle engine: commitment -> transfer -> utilization -> "
               "report -> replenishment -> repeat, for grants on the Revolving "
               "Fund funding model.",
    "description": """
ARCS Revolving Fund
====================
Implements the first ARCS funding-model plug-in: the Revolving Fund cycle
described in the Revolving Fund Workflow SRS.

This module is purely additive. It does not modify the behavior of any
funding model other than Revolving Fund, and it never edits the accounting,
budget, or reporting logic of the modules it builds on - it only
orchestrates them (arcs_fund for cash receipts, arcs_budget/arcs_expense for
spend control, arcs_report for the donor utilization report, arcs_closure
for the final grant close-out).

Designed as the template for future funding-model plug-ins: it relies on two
small, neutral extension hooks added to arcs_grant/arcs_expense core
(_funding_model_check_expense_availability,
_funding_model_check_closure_allowed) rather than embedding
funding-model-specific conditionals in shared code.
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_fund", "arcs_budget", "arcs_expense", "arcs_report"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_revolving_security.xml",
        "data/ir_sequence_data.xml",
        "wizards/arcs_revolving_replenishment_send_wizard_views.xml",
        "views/arcs_revolving_cycle_views.xml",
        "views/arcs_grant_views.xml",
        "views/arcs_expense_views.xml",
        "views/arcs_fund_receipt_views.xml",
        "views/arcs_donor_report_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "auto_install": False,
}
