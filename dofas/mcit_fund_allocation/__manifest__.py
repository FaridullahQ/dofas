{
    "name": "MCIT Donor Mgmt - Fund Program Allocation",
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "summary": "Allocate donor fund receipts across programs/projects; surfaces the "
               "breakdown on the Thank-You letter and donor acknowledgement email.",
    "description": """
Fund Receipt -> Program Allocation
===================================
Adds a Program Allocation table to Donor Fund Receipts so a single receipt
can be broken down by Program (and optionally Project). The breakdown is
shown on the receipt form, the printed Thank-You letter, and prefilled into
the donor acknowledgement email body.

Kept as a separate module (rather than added into mcit_fund) because
mcit_program depends on mcit_fund indirectly through mcit_expense; mcit_fund
extending mcit_program would create a circular dependency.
""",
    "author": "MCIT",
    "depends": ["mcit_fund", "mcit_program"],
    "data": [
        "security/ir.model.access.csv",
        "views/mcit_fund_receipt_views.xml",
        "report/fund_thanks_report_inherit.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
