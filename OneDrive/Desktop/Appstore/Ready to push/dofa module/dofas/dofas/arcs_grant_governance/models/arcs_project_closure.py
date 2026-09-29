from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsProjectClosure(models.Model):
    _inherit = "arcs.project.closure"

    final_report_id = fields.Many2one(
        "arcs.donor.report", string="Final Donor Report",
        domain="[('grant_id', '=', grant_id), ('state', '=', 'approved')]",
        help="The report ARC is treating as the final one to this donor for "
             "this grant. Required for restricted grants before closure can "
             "be approved, and its Donor Feedback must show Approved.")
    donor_feedback_state = fields.Selection(
        related="final_report_id.donor_feedback_state", readonly=True)
    grant_is_restricted = fields.Boolean(related="grant_id.is_restricted", readonly=True)
    grant_unresolved_count = fields.Integer(
        related="grant_id.compliance_unresolved_count", readonly=True)

    def action_verify(self):
        for c in self.filtered("grant_is_restricted"):
            if c.grant_unresolved_count:
                raise UserError(_(
                    "Cannot verify closure: grant '%(g)s' has %(n)d unresolved "
                    "flagged/rejected compliance item(s). Resolve, pass, or "
                    "waive them (with a reason) before verifying closure.",
                    g=c.grant_id.display_name, n=c.grant_unresolved_count))
        return super().action_verify()

    def action_approve(self):
        for c in self.filtered("grant_is_restricted"):
            if not c.final_report_id:
                raise UserError(_(
                    "Select the Final Donor Report before approving closure of a "
                    "restricted grant (SRS: mark closed only after donor "
                    "acceptance)."))
            if c.final_report_id.donor_feedback_state != "approved":
                raise UserError(_(
                    "The Final Donor Report's Donor Feedback must be Approved "
                    "before closure can be approved (currently: %s).") % dict(
                    c.final_report_id._fields["donor_feedback_state"].selection
                ).get(c.final_report_id.donor_feedback_state))
        return super().action_approve()
