from odoo import fields, models


class ArcsDonorReport(models.Model):
    _inherit = "arcs.donor.report"

    donor_feedback_state = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"),
         ("clarification_requested", "Clarification Requested"), ("rejected", "Rejected")],
        default="pending", required=True, tracking=True,
        help="What the donor actually said back after receiving this report - "
             "separate from the state above, which tracks ARC's own internal "
             "review before the report is even sent.")
    donor_feedback_date = fields.Date()
    donor_feedback_notes = fields.Text()

    def action_submit(self):
        res = super().action_submit()
        for r in self:
            r.grant_id._governance_create_verifications("report_submission", r)
        return res

    def action_review(self):
        for r in self:
            r.grant_id._governance_check_gate("report_submission", r)
        return super().action_review()
