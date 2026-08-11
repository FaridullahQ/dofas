{
    "name": "ARCS Donor Mgmt - Reporting",
    "version": "17.0.1.4.0",
    "summary": "Department and donor reports, templates, PDF output, reporting calendar, plus "
               "Budget vs Actual and Project/Activity Reports.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3", "author": "ARCS",
    "depends": ["arcs_expense", "arcs_program"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_report_rules.xml",
        "data/ir_cron_data.xml",
        "views/arcs_report_views.xml",
        "views/arcs_budget_vs_actual_views.xml",
        "views/arcs_activity_report_views.xml",
        "report/arcs_donor_report_templates.xml",
        "report/arcs_donor_report_actions.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
