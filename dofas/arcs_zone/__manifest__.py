{
    "name": "ARCS Donor Mgmt - Zones & Departments",
    "version": "17.0.1.5.0",
    "summary": "Region/Province dimension for HQ + field tracking, with Departments as the "
               "real hr.department model (a Province link added onto it), and a unique "
               "Employee Code added onto hr.employee so employees who share a name are "
               "never picked ambiguously anywhere in the suite.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_base", "arcs_expense", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_zone_rules.xml",
        "views/arcs_zone_views.xml",
        "views/hr_department_views.xml",
        "views/hr_employee_views.xml",
        "views/arcs_expense_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
