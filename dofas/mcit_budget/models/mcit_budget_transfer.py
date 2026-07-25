from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class McitBudgetTransfer(models.Model):
    """Move planned amount between two budget lines of the same budget
    (i.e. same grant/currency), subject to Finance Manager approval. This
    model is intentionally self-contained and knows nothing about spend
    requests or any other downstream module - it is a reusable primitive
    that other modules (e.g. mcit_request) can extend/link to."""

    _name = "mcit.budget.transfer"
    _description = "Internal Budget Transfer"
    _inherit = ["mcit.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False, readonly=True)
    from_line_id = fields.Many2one(
        "mcit.budget.line", string="From Budget Line", tracking=True,
        domain="[('budget_state', '=', 'approved')]",
        help="Source line to move budget from. Required before submitting.")
    to_line_id = fields.Many2one(
        "mcit.budget.line", string="To Budget Line", required=True, tracking=True,
        domain="[('budget_state', '=', 'approved')]")
    currency_id = fields.Many2one(related="from_line_id.currency_id", readonly=True)
    amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    reason = fields.Text(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"),
         ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)
    company_id = fields.Many2one(related="from_line_id.company_id", store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mcit.budget.transfer") or _("New")
        return super().create(vals_list)

    @api.constrains("amount")
    def _check_amount_positive(self):
        for t in self:
            if t.amount and t.amount <= 0:
                raise ValidationError(_("The transfer amount must be greater than zero."))

    @api.constrains("from_line_id", "to_line_id")
    def _check_lines(self):
        for t in self.filtered(lambda x: x.from_line_id and x.to_line_id):
            if t.from_line_id == t.to_line_id:
                raise ValidationError(_("The source and destination budget lines must be different."))
            if t.from_line_id.budget_id != t.to_line_id.budget_id:
                raise ValidationError(_(
                    "Both budget lines must belong to the same budget (grant/version). "
                    "Cross-grant transfers are not supported."))

    def action_submit(self):
        for t in self:
            if t.state != "draft":
                raise UserError(_("Only draft transfers can be submitted."))
            if not t.from_line_id:
                raise UserError(_("Select the source budget line (From Budget Line) "
                                  "before submitting."))
            if t.amount <= 0:
                raise UserError(_("The transfer amount must be greater than zero."))
        return self._transition("submitted", "submit")

    def action_approve(self):
        if not self.env.user.has_group("mcit_base.group_finance_manager") \
                and not self.env.user.has_group("mcit_base.group_system_admin"):
            raise UserError(_("Only a Finance Manager can approve an internal budget transfer."))
        for t in self:
            if t.state != "submitted":
                raise UserError(_("Only submitted transfers can be approved."))
            rounding = t.currency_id.rounding
            # Lock both lines (consistent order by id to avoid deadlocks) and
            # re-verify under lock, mirroring the reserve() hard-stop pattern.
            lines = (t.from_line_id + t.to_line_id).sorted("id")
            for line in lines:
                line.get_available_locked()
            if float_compare(t.amount, t.from_line_id.planned_amount, precision_rounding=rounding) > 0:
                raise UserError(_(
                    "Cannot transfer %(amt).2f %(cur)s: '%(line)s' is only planned at "
                    "%(planned).2f %(cur)s.") % {
                    "amt": t.amount, "cur": t.currency_id.name or "",
                    "line": t.from_line_id.name, "planned": t.from_line_id.planned_amount})
            t.from_line_id.planned_amount -= t.amount
            t.to_line_id.planned_amount += t.amount
        return self._transition("approved", "approve")

    def action_reject(self):
        return self._transition("rejected", "reject")

    def action_cancel(self):
        for t in self:
            if t.state == "approved":
                raise UserError(_("An approved transfer cannot be cancelled; reverse it "
                                  "with an offsetting transfer instead."))
        return self._transition("cancelled", "cancel")
