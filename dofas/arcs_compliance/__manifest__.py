{
    "name": "ARCS Donor Mgmt - Compliance",
    "version": "17.0.1.2.0",
    "summary": "Compliance checklists and mandatory-attachment gating, plus a cross-grant "
               "Compliance Reports overview.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3", "author": "ARCS",
    "depends": ["arcs_fund", "arcs_report"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_compliance_rules.xml",
        "views/arcs_compliance_views.xml",
        "views/arcs_compliance_report_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
