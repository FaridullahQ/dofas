{
    "name": "ARCS Donor Mgmt - Zones & Departments",
    "version": "17.0.1.3.0",
    "summary": "Region/Province and Department dimensions for HQ + field tracking.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_base", "arcs_expense"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_zone_rules.xml",
        "views/arcs_zone_views.xml",
        "views/arcs_department_views.xml",
        "views/arcs_expense_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
