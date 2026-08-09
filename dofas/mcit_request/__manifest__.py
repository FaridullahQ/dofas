{
    "name": "MCIT Donor Mgmt - Acquisitions (Four Form)",
    "version": "17.0.1.11.0",
    "summary": "Four-step pre-acquisition request that reserves budget before expenses, with "
               "insufficient-funds recovery, and an employee cash-advance/settlement cycle "
               "on approval.",
    "description": "Implements the 'Four Form' workflow: Programs drafts an acquisition, the budget "
                   "holder submits it, the budget manager commits it (reserving the chosen budget "
                   "line) after confirming the real quoted price, and the authority approves it. "
                   "'Requested By' is now an hr.employee. Once approved, Finance can disburse the "
                   "approved amount to that employee as a real cash advance (mcit_advance); the "
                   "employee spends it, their expense(s) are justified via a liquidation, and any "
                   "difference is settled with a real journal entry through a chosen bank/cash "
                   "journal, gated on a required slip attachment - paid back if they spent less, "
                   "reimbursed if they spent more from their own pocket. An approved acquisition "
                   "can spawn an expense that adopts the reserve instead of re-reserving (or one "
                   "expense per line if the reserve was split). If Finance finds the budget line "
                   "short, the request is routed to a reportable 'Insufficient Funds' state with "
                   "four recovery paths: choose a different budget line, split the approved amount "
                   "across several budget lines, request an internal budget transfer, or request "
                   "supplementary donor funding.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_zone", "mcit_budget", "mcit_program", "mcit_fund", "mcit_advance", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "report/acquisition_voucher_report.xml",
        "views/mcit_spend_request_views.xml",
        "views/mcit_advance_views.xml",
        "views/mcit_expense_views.xml",
        "views/mcit_budget_transfer_views.xml",
        "views/mcit_donor_funding_request_views.xml",
        "wizards/mcit_spend_request_quotation_wizard_views.xml",
        "wizards/mcit_spend_request_reassign_wizard_views.xml",
        "wizards/mcit_spend_request_split_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
