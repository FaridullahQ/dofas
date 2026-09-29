from odoo import fields, models


class ArcsComplianceChecklistLine(models.Model):
    _inherit = "arcs.compliance.checklist.line"

    verification_trigger = fields.Selection(
        [("manual", "Manual Only"), ("expense_approval", "On Expense Approval"),
         ("report_submission", "On Donor Report Submission")],
        string="Auto-Raise On", default="manual", required=True,
        help="When set to Manual Only, this requirement is informational and "
             "shown on the grant/report only. Any other value automatically "
             "raises a Compliance Verification record at that moment for every "
             "grant using this checklist.")
    enforcement = fields.Selection(
        [("advisory", "Advisory (flag only)"), ("gate", "Hard Gate (block until resolved)")],
        default="advisory", required=True,
        help="Advisory: a raised item never blocks the expense/report that raised "
             "it - it only blocks that grant's closure verification if left "
             "Flagged. Gate: the NEXT step (expense Approval, or report Review) "
             "is blocked until every Gate item raised at Submit is Passed or "
             "Waived. Defaults to Advisory everywhere, so existing checklists "
             "are completely unaffected until a line is deliberately switched "
             "to Gate.")
