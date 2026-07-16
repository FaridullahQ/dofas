{
    "name": "MCIT Donor Mgmt - Base",
    "version": "17.0.1.0.0",
    "summary": "Foundation: approval mixin, immutable audit log, roles, configuration.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["base", "mail"],
    "data": [
        "security/mcit_security.xml",
        "security/ir.model.access.csv",
        "views/mcit_audit_log_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
