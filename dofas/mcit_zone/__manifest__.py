{
    "name": "MCIT Donor Mgmt - Zones & Departments",
    "version": "17.0.1.2.0",
    "summary": "Zone/Province and Department dimensions for HQ + field tracking.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_base", "mcit_expense"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_zone_rules.xml",
        "views/mcit_zone_views.xml",
        "views/mcit_department_views.xml",
        "views/mcit_expense_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
