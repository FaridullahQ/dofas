{
    "name": "MCIT Donor Mgmt - Donor",
    "version": "17.0.1.0.0",
    "summary": "Donor master data.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_base", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_donor_rules.xml",
        "views/mcit_donor_views.xml",
        "views/res_users_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
