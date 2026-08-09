{
    "name": "MCIT Donor Mgmt - Fund",
    "version": "17.0.1.6.0",
    "summary": "Donor fund receipts with bank voucher reference, attachment gate, GL posting, donor "
               "thank-you letter, and supplementary funding requests with an email composer and a "
               "bank-receipt attachment gate on recording the donor's approval.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_grant", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/mcit_fund_rules.xml",
        "data/ir_sequence_data.xml",
        "report/fund_thanks_report.xml",
        "report/fund_receipt_voucher_report.xml",
        "wizards/mcit_fund_receipt_send_wizard_views.xml",
        "wizards/mcit_donor_funding_request_send_wizard_views.xml",
        "views/mcit_fund_receipt_views.xml",
        "views/mcit_grant_views.xml",
        "views/mcit_donor_funding_request_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
