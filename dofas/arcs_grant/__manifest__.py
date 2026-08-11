{
    "name": "ARCS Donor Mgmt - Grant",
    "version": "17.0.1.3.0",
    "summary": "Grant / donor agreements with analytic accounts and lifecycle.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_donor", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_grant_security.xml",
        "data/ir_sequence_data.xml",
        "views/arcs_donor_views.xml",
        "views/arcs_grant_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
