from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsProjectClosure(models.Model):
    _name = "arcs.project.closure"
    _description = "Grant Closure"
    _inherit = ["arcs.approval.mixin", "mail.thread"]
    _order = "create_date desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False)
    grant_id = fields.Many2one("arcs.grant", required=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    all_expenses_posted = fields.Boolean(compute="_compute_checks", store=True)
    all_reports_approved = fields.Boolean(compute="_compute_checks", store=True)
    received_total = fields.Monetary(compute="_compute_balance", currency_field="currency_id")
    actual_total = fields.Monetary(compute="_compute_balance", currency_field="currency_id")
    remaining_balance = fields.Monetary(compute="_compute_balance", currency_field="currency_id")
    returned_amount = fields.Monetary(currency_field="currency_id",
                                      help="Unspent restricted funds returned to the donor.")
    state = fields.Selection(
        [("draft", "Draft"), ("verified", "Verified"), ("approved", "Approved")],
        default="draft", required=True, tracking=True, copy=False)

    def _compute_checks(self):
        Expense = self.env["arcs.expense"]
        Donor = self.env["arcs.donor.report"]
        for c in self:
            pending = Expense.search_count(
                [("grant_id", "=", c.grant_id.id), ("state", "in", ("submitted", "approved"))])
            c.all_expenses_posted = pending == 0
            unapproved = Donor.search_count(
                [("grant_id", "=", c.grant_id.id), ("state", "!=", "approved")])
            c.all_reports_approved = unapproved == 0

    def _compute_balance(self):
        AAL = self.env["account.analytic.line"]
        for c in self:
            received = getattr(c.grant_id, "received_total", 0.0)
            actual = 0.0
            if c.grant_id.analytic_account_id:
                rows = AAL._read_group(
                    [("account_id", "=", c.grant_id.analytic_account_id.id)], [], ["amount:sum"])
                actual = -(rows[0][0] if rows and rows[0][0] else 0.0)
            c.received_total = received
            c.actual_total = actual
            c.remaining_balance = received - actual

    def action_verify(self):
        for c in self:
            if not (c.all_expenses_posted and c.all_reports_approved):
                raise UserError(_(
                    "Cannot verify closure: all expenses must be posted and all "
                    "donor reports approved first."))
        return self._transition("verified", "verify")

    def action_approve(self):
        for c in self:
            if c.state != "verified":
                raise UserError(_("Only a verified closure can be approved."))
            # Returnable unspent balance applies to restricted grants.
            if c.grant_id.is_restricted and not c.returned_amount:
                c.returned_amount = max(c.remaining_balance, 0.0)
            if c.grant_id.state == "active":
                c.grant_id.action_close()
        return self._transition("approved", "approve")
