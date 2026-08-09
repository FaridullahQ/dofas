{
    "name": "MCIT Donor Mgmt - Compliance",
    "version": "17.0.1.1.0",
    "summary": "Compliance checklists and mandatory-attachment gating.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3", "author": "MCIT",
    "depends": ["mcit_fund"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_compliance_rules.xml",
        "views/mcit_compliance_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
