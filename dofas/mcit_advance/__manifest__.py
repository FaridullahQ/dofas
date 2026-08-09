{
    "name": "MCIT Donor Mgmt - Advances & Liquidation",
    "version": "17.0.1.5.0",
    "summary": "Region/employee cash advances with liquidation, real-journal settlement (return or "
               "reimbursement), and outstanding tracking by employee/department/position.",
    "description": "HQ issues advances to zones/provinces or staff (who become debtors), tracks "
                   "sent / reported / outstanding / cash balance, and clears them through a "
                   "reviewed liquidation of justified expenses. An employee advance can now be "
                   "linked to an hr.employee record (Department/Position surfaced for reporting), "
                   "and settled through a dedicated wizard that posts a real journal entry via a "
                   "chosen bank/cash journal - either the holder returning unused cash, or being "
                   "reimbursed for having spent more than the advance - gated on a required "
                   "deposit/payment slip attachment. Optionally posts journal entries on issuance "
                   "and liquidation too.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_zone", "mcit_grant", "mcit_expense", "hr", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_advance_rules.xml",
        "data/ir_sequence.xml",
        "views/mcit_advance_views.xml",
        "views/mcit_advance_liquidation_views.xml",
        "views/hr_employee_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "wizards/mcit_advance_settlement_wizard_views.xml",
    ],
    "installable": True,
}
