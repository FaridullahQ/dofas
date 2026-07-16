from odoo import _, api, fields, models
from odoo.exceptions import UserError


class McitBudget(models.Model):
    _name = "mcit.budget"
    _description = "Grant Budget (Versioned)"
    _inherit = ["mcit.approval.mixin", "mail.thread"]
    _order = "grant_id, version desc"

    grant_id = fields.Many2one("mcit.grant", required=True, ondelete="cascade", index=True)
    version = fields.Integer(default=1, readonly=True, copy=False)
    name = fields.Char(compute="_compute_name", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    line_ids = fields.One2many("mcit.budget.line", "budget_id", string="Budget Lines")
    planned_total = fields.Monetary(compute="_compute_planned_total", store=True, currency_field="currency_id")
    available_total = fields.Monetary(compute="_compute_available_total", currency_field="currency_id")
    state = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("superseded", "Superseded")],
        default="draft", required=True, tracking=True, copy=False)

    @api.depends("grant_id.grant_number", "version")
    def _compute_name(self):
        for b in self:
            b.name = _("%(g)s - Budget v%(v)s") % {"g": b.grant_id.grant_number or _("New"), "v": b.version}

    @api.depends("line_ids.planned_amount")
    def _compute_planned_total(self):
        for b in self:
            b.planned_total = sum(b.line_ids.mapped("planned_amount"))

    @api.depends("line_ids.available_amount")
    def _compute_available_total(self):
        for b in self:
            b.available_total = sum(b.line_ids.mapped("available_amount"))

    def action_approve(self):
        for b in self:
            if b.state != "draft":
                raise UserError(_("Only draft budgets can be approved."))
            prev = b.grant_id.budget_ids.filtered(lambda x: x.state == "approved" and x.id != b.id)
            prev._transition("superseded", "supersede")
        return self._transition("approved", "approve")

    def action_create_revision(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved budget can be revised."))
        new = self.copy({"version": self.version + 1, "state": "draft"})
        for line in self.line_ids:
            line.copy({"budget_id": new.id})
        return {"type": "ir.actions.act_window", "res_model": "mcit.budget",
                "res_id": new.id, "view_mode": "form"}
