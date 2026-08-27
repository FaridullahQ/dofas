{
    "name": "ARCS Donor Mgmt - Program & Projects",
    "version": "17.0.1.5.0",
    "summary": "Program -> Project -> Component -> Activity hierarchy, each level with its own "
               "Planned Cost ceiling tracked alongside the budget line.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3", "author": "ARCS",
    "depends": ["arcs_budget", "arcs_expense"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_program_security.xml",
        "views/arcs_program_views.xml",
        "views/arcs_expense_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "wizards/lifecycle_close_wizard_views.xml",
    ],
    "installable": True,
}
