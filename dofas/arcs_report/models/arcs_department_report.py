from odoo import _, models, fields
from odoo.exceptions import UserError


class ArcsDepartmentReport(models.Model):
    _name = "arcs.department.report"
    _description = "Department Report"
    _inherit = ["arcs.approval.mixin", "mail.thread"]
    _order = "create_date desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False)
    grant_id = fields.Many2one("arcs.grant", required=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    period = fields.Char(string="Reporting Period")
    narrative = fields.Html()
    achievements = fields.Text()
    challenges = fields.Text()
    lessons_learned = fields.Text()
    outputs = fields.Text()
    outcomes = fields.Text()
    remaining_budget = fields.Monetary(currency_field="currency_id")
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("reviewed", "Reviewed"),
         ("approved", "Approved")], default="draft", required=True, tracking=True, copy=False)

    def _require_support(self):
        for r in self:
            count = self.env["ir.attachment"].search_count(
                [("res_model", "=", "arcs.department.report"), ("res_id", "=", r.id)])
            if not count:
                raise UserError(_("Attach supporting documents before submitting the report."))

    def action_submit(self):
        self._require_support()
        return self._transition("submitted", "submit")

    def action_review(self):
        return self._transition("reviewed", "review")

    def action_approve(self):
        return self._transition("approved", "approve")
