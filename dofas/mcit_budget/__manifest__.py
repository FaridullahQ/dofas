{
    "name": "MCIT Donor Mgmt - Budget",
    "version": "17.0.1.4.0",
    "summary": "Versioned grant budgets, the concurrency-safe encumbrance engine, and internal budget transfers.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_grant", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_budget_security.xml",
        "data/ir_sequence.xml",
        "views/mcit_budget_views.xml",
        "views/mcit_budget_transfer_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
