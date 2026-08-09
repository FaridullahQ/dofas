{
    "name": "MCIT Donor Mgmt - Program & Projects",
    "version": "17.0.1.3.0",
    "summary": "Program -> Project -> Component -> Activity hierarchy with activity budgeting.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3", "author": "MCIT",
    "depends": ["mcit_budget", "mcit_expense"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_program_security.xml",
        "views/mcit_program_views.xml",
        "views/mcit_expense_views.xml",
        "views/menus.xml",
        "wizards/lifecycle_close_wizard_views.xml",
    ],
    "installable": True,
}
