{
    "name": "MCIT Donor Mgmt - Base",
    "version": "17.0.1.3.0",
    "summary": "Foundation: approval mixin, immutable audit log, roles, configuration, and the reason "
               "wizard used by every Reject/Cancel/Reset to Draft button across the suite.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["base", "mail", "account"],
    "data": [
        "security/mcit_security.xml",
        "security/ir.model.access.csv",
        "views/mcit_audit_log_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "report/mcit_voucher_template.xml",
        "wizards/mcit_reason_wizard_views.xml",
    ],
    "application": True,
    "installable": True,
}
