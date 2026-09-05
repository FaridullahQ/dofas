{
    "name": "ARCS Donor Mgmt - Fund",
    "version": "17.0.1.8.0",
    "summary": "Donor fund receipts with bank voucher reference, attachment gate, GL posting, donor "
               "thank-you letter, and supplementary funding requests with an email composer and a "
               "bank-receipt attachment gate on recording the donor's approval.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/arcs_fund_rules.xml",
        "data/ir_sequence_data.xml",
        "report/fund_thanks_report.xml",
        "report/fund_receipt_voucher_report.xml",
        "wizards/arcs_fund_receipt_send_wizard_views.xml",
        "wizards/arcs_donor_funding_request_send_wizard_views.xml",
        "views/arcs_fund_receipt_views.xml",
        "views/arcs_grant_views.xml",
        "views/arcs_donor_funding_request_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
