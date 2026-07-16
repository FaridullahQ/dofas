{
    "name": "MCIT Donor Mgmt - Acquisitions (Four Form)",
    "version": "17.0.1.4.1",
    "summary": "Four-step pre-acquisition request that reserves budget before expenses, with "
               "insufficient-funds recovery (reassign line, internal transfer, donor funding).",
    "description": "Implements the 'Four Form' workflow: Programs drafts an acquisition, the budget "
                   "holder submits it, the budget manager commits it (reserving the chosen budget "
                   "line) after confirming the real quoted price, and the authority approves it. "
                   "An approved acquisition can spawn an expense that adopts the reserve instead "
                   "of re-reserving. If Finance finds the budget line short, the request is routed "
                   "to a reportable 'Insufficient Funds' state with three recovery paths: choose a "
                   "different budget line, request an internal budget transfer, or request "
                   "supplementary donor funding.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_zone", "mcit_budget", "mcit_program", "mcit_fund"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/mcit_spend_request_views.xml",
        "views/mcit_expense_views.xml",
        "views/mcit_budget_transfer_views.xml",
        "views/mcit_donor_funding_request_views.xml",
        "wizards/mcit_spend_request_quotation_wizard_views.xml",
        "wizards/mcit_spend_request_reassign_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
