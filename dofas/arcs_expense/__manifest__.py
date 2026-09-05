{
    "name": "ARCS Donor Mgmt - Expense",
    "version": "17.0.1.4.0",
    "summary": "Grant expenditure: encumber on approval, book analytic actual on posting.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_budget", "arcs_fund", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_expense_security.xml",
        "data/ir_sequence_data.xml",
        "report/expense_voucher_report.xml",
        "views/arcs_expense_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
