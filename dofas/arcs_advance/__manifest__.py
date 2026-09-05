{
    "name": "ARCS Donor Mgmt - Advances & Liquidation",
    "version": "17.0.1.9.0",
    "summary": "Region/employee cash advances with a mandatory Lock (accrual, holder debited) "
               "step before real-journal disbursement and settlement (return or "
               "reimbursement), liquidation, and outstanding tracking by employee/department/position.",
    "description": "HQ issues advances to zones/provinces or staff (who become debtors), tracks "
                   "sent / reported / outstanding / cash balance, and clears them through a "
                   "reviewed liquidation of justified expenses. An employee advance can now be "
                   "linked to an hr.employee record (Department/Position surfaced for reporting). "
                   "Before any cash can be disbursed, the advance must first be Locked: a real "
                   "accrual journal entry debits the Advance (Receivable) Account and credits a "
                   "dedicated Advances Payable / Clearing Account, formally debiting the holder "
                   "and committing the amount - always posted, regardless of the legacy 'Book "
                   "Advances to the Ledger' toggle. Only once Locked can the advance actually be "
                   "disbursed, which clears that same liability against Cash through a chosen "
                   "bank/cash journal - the net effect across both entries is identical to a "
                   "direct debit-receivable/credit-cash entry, just split into two "
                   "audit-trail-visible, separately-timestamped moves for proper double-entry, "
                   "accrual-based accounting. Both issuing and settling an advance go through "
                   "dedicated wizards that post a real journal entry via a chosen bank/cash "
                   "journal - disbursing cash to the holder, or later either the holder returning "
                   "unused cash or being reimbursed for having spent more than the advance - each "
                   "gated on a required voucher/slip attachment, and always reconciliation-ready "
                   "against that journal's own account.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_zone", "arcs_grant", "arcs_expense", "hr", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_advance_rules.xml",
        "data/ir_sequence.xml",
        "views/arcs_advance_views.xml",
        "views/arcs_advance_liquidation_views.xml",
        "views/hr_employee_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "wizards/arcs_advance_settlement_wizard_views.xml",
        "wizards/arcs_advance_disbursement_wizard_views.xml",
    ],
    "installable": True,
}
