{
    "name": "MCIT Donor Mgmt - Grant",
    "version": "17.0.1.3.0",
    "summary": "Grant / donor agreements with analytic accounts and lifecycle.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_donor", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_grant_security.xml",
        "data/ir_sequence_data.xml",
        "views/mcit_donor_views.xml",
        "views/mcit_grant_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
