{
    "name": "MCIT Donor Mgmt - Expense",
    "version": "17.0.1.2.0",
    "summary": "Grant expenditure: encumber on approval, book analytic actual on posting.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_budget", "mcit_fund", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_expense_security.xml",
        "data/ir_sequence_data.xml",
        "report/expense_voucher_report.xml",
        "views/mcit_expense_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
