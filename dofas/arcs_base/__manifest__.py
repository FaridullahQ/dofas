{
    "name": "ARCS Donor Mgmt - Base",
    "version": "17.0.1.5.0",
    "summary": "Foundation: approval mixin, immutable audit log, roles, configuration, the reason "
               "wizard used by every Reject/Cancel/Reset to Draft button across the suite, and "
               "the suite-wide menu structure (Procurement & Assets, Master Data, Audit & "
               "Compliance, Configuration).",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["base", "base_setup", "mail", "account"],
    "data": [
        "security/arcs_security.xml",
        "security/ir.model.access.csv",
        "views/arcs_audit_log_views.xml",
        "views/arcs_ask_index_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "report/arcs_voucher_template.xml",
        "wizards/arcs_reason_wizard_views.xml",
    ],
    "application": True,
    "installable": True,
}
