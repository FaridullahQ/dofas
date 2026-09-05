{
    "name": "ARCS Donor Mgmt - Program & Projects",
    "version": "17.0.1.6.0",
    "summary": "Program -> Project -> Activity hierarchy, each level's Planned Cost ceiling "
               "correctly shared among siblings (two programs on one budget line, two "
               "projects on one program, two activities on one project can never together "
               "plan more than their parent actually has).",
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
