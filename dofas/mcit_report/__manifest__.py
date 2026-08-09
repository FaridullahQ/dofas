{
    "name": "MCIT Donor Mgmt - Reporting",
    "version": "17.0.1.3.0",
    "summary": "Department and donor reports, templates, PDF output, reporting calendar.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3", "author": "MCIT",
    "depends": ["mcit_expense"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_report_rules.xml",
        "data/ir_cron_data.xml",
        "views/mcit_report_views.xml",
        "report/mcit_donor_report_templates.xml",
        "report/mcit_donor_report_actions.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
