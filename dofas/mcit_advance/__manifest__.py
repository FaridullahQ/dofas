{
    "name": "MCIT Donor Mgmt - Advances & Liquidation",
    "version": "17.0.1.3.0",
    "summary": "Region/employee cash advances with liquidation and outstanding tracking.",
    "description": "HQ issues advances to zones/provinces or staff (who become debtors), tracks "
                   "sent / reported / outstanding / cash balance, and clears them through a "
                   "reviewed liquidation of justified expenses. Optionally posts journal entries.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_zone", "mcit_grant", "mcit_expense", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_advance_rules.xml",
        "data/ir_sequence.xml",
        "views/mcit_advance_views.xml",
        "views/mcit_advance_liquidation_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
