{
    "name": "ARCS Donor Mgmt - Donor",
    "version": "17.0.1.0.0",
    "summary": "Donor master data.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_base", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_donor_rules.xml",
        "views/arcs_donor_views.xml",
        "views/res_users_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
