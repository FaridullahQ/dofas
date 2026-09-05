{
    "name": "ARCS Donor Mgmt - Budget",
    "version": "17.0.1.9.0",
    "summary": "Versioned grant budgets, the concurrency-safe encumbrance engine, and internal budget "
               "transfers that never overwrite a line's originally approved Planned amount.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_budget_security.xml",
        "data/ir_sequence.xml",
        "views/arcs_budget_views.xml",
        "views/arcs_budget_transfer_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
