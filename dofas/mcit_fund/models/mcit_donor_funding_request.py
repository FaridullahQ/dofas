from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class McitDonorFundingRequest(models.Model):
    """Ask a grant's donor for supplementary funding above what has already
    been received. Self-contained: knows nothing about spend requests or any
    other downstream module. The donor's decision is recorded by a Finance
    user (donors are not system users); once approved, Finance still has to
    action the actual budget increase (a planned_amount edit or an
    mcit.budget.transfer) — this model does not touch the budget itself, to
    keep financial control changes explicit and auditable."""

    _name = "mcit.donor.funding.request"
    _description = "Donor Supplementary Funding Request"
    _inherit = ["mcit.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False, readonly=True)
    grant_id = fields.Many2one("mcit.grant", string="Grant", required=True, tracking=True)
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", readonly=True)
    amount_requested = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    reason = fields.Text(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("requested", "Requested from Donor"),
         ("approved", "Donor Approved"), ("rejected", "Donor Rejected"),
         ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)
    decision_date = fields.Date(readonly=True, copy=False)
    decision_note = fields.Text(copy=False)
    company_id = fields.Many2one(related="grant_id.company_id", store=True, readonly=True)

    @api.constrains("amount_requested")
    def _check_amount_positive(self):
        for r in self:
            if r.amount_requested and r.amount_requested <= 0:
                raise ValidationError(_("The requested amount must be greater than zero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mcit.donor.funding.request") or _("New")
        return super().create(vals_list)

    def action_request(self):
        for r in self:
            if r.state != "draft":
                raise UserError(_("Only draft requests can be sent to the donor."))
            if r.amount_requested <= 0:
                raise UserError(_("The requested amount must be greater than zero."))
        return self._transition("requested", "request")

    def action_donor_approve(self):
        self.ensure_one()
        if not self.env.user.has_group("mcit_base.group_finance_officer") \
                and not self.env.user.has_group("mcit_base.group_finance_manager") \
                and not self.env.user.has_group("mcit_base.group_system_admin"):
            raise UserError(_("Only a Finance user can record the donor's decision."))
        if self.state != "requested":
            raise UserError(_("Only requests already sent to the donor can be recorded as approved."))
        self.write({"decision_date": fields.Date.context_today(self)})
        return self._transition("approved", "donor_approve", comment=self.decision_note)

    def action_donor_reject(self):
        self.ensure_one()
        if not self.env.user.has_group("mcit_base.group_finance_officer") \
                and not self.env.user.has_group("mcit_base.group_finance_manager") \
                and not self.env.user.has_group("mcit_base.group_system_admin"):
            raise UserError(_("Only a Finance user can record the donor's decision."))
        if self.state != "requested":
            raise UserError(_("Only requests already sent to the donor can be recorded as rejected."))
        self.write({"decision_date": fields.Date.context_today(self)})
        return self._transition("rejected", "donor_reject", comment=self.decision_note)

    def action_cancel(self):
        for r in self:
            if r.state == "approved":
                raise UserError(_("An approved donor funding request cannot be cancelled."))
        return self._transition("cancelled", "cancel")
