from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ArcsDonorFundingRequest(models.Model):
    """Ask a grant's donor for supplementary funding above what has already
    been received. Self-contained: knows nothing about spend requests or any
    other downstream module. The donor's decision is recorded by a Finance
    user (donors are not system users); once approved, Finance still has to
    action the actual budget increase (a planned_amount edit or an
    arcs.budget.transfer) — this model does not touch the budget itself, to
    keep financial control changes explicit and auditable.

    Two related but distinct actions live alongside the state machine:
    - Send Email (action_open_send_wizard): composes and actually delivers
      the ask to the donor's inbox, once the request has been formally
      logged as sent (state='requested'). "Send to Donor" itself only
      records that decision internally and locks the request; it does not
      by itself send anything - mirroring arcs.fund.receipt's
      post-then-email pattern in this same module.
    - Recording the donor's approval requires proof: a bank receipt
      attachment plus the amount that receipt actually confirms (which can
      differ from what was requested), mirroring arcs.fund.receipt's
      voucher-attachment gate on posting.
    """

    _name = "arcs.donor.funding.request"
    _description = "Donor Supplementary Funding Request"
    _inherit = ["arcs.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False, readonly=True)
    grant_id = fields.Many2one("arcs.grant", string="Grant", required=True, tracking=True)
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
    amount_approved = fields.Monetary(
        string="Amount Confirmed", currency_field="currency_id", copy=False, tracking=True,
        help="The amount actually confirmed by the donor's bank receipt - it can differ "
             "from Requested (bank fees, partial funding, exchange differences). Seeded "
             "from Requested when the request is sent, but stays editable until approval "
             "is recorded, together with the receipt attachment, as proof of what was "
             "really received.")
    company_id = fields.Many2one(related="grant_id.company_id", store=True, readonly=True)

    # --- donor communication email ---
    email_sent = fields.Boolean(string="Email Sent", readonly=True, copy=False, tracking=True)
    email_sent_date = fields.Datetime(string="Emailed On", readonly=True, copy=False)

    # --- bank receipt attachment gate ---
    attachment_count = fields.Integer(compute="_compute_attachment_count")
    bank_receipt_attached = fields.Boolean(
        compute="_compute_attachment_count", string="Bank Receipt Attached")

    @api.constrains("amount_requested")
    def _check_amount_positive(self):
        for r in self:
            if r.amount_requested and r.amount_requested <= 0:
                raise ValidationError(_("The requested amount must be greater than zero."))

    def _compute_attachment_count(self):
        Att = self.env["ir.attachment"]
        for r in self:
            cnt = Att.search_count([
                ("res_model", "=", r._name), ("res_id", "=", r.id)]) if r.id else 0
            r.attachment_count = cnt
            r.bank_receipt_attached = cnt > 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "arcs.donor.funding.request") or _("New")
        return super().create(vals_list)

    def action_request(self):
        for r in self:
            if r.state != "draft":
                raise UserError(_("Only draft requests can be sent to the donor."))
            if r.amount_requested <= 0:
                raise UserError(_("The requested amount must be greater than zero."))
            if not r.amount_approved:
                # Seed a starting suggestion equal to what's being asked for;
                # Finance overwrites it with what the bank receipt actually
                # confirms when recording the donor's decision.
                r.amount_approved = r.amount_requested
        return self._transition("requested", "request")

    def action_donor_reject_wizard(self):
        return self._open_reason_wizard("action_donor_reject", _("Record Donor Rejection"))

    def action_open_send_wizard(self):
        self.ensure_one()
        if self.state != "requested":
            raise UserError(_(
                "Use 'Send to Donor' first to log this request as sent before emailing it."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Funding Request Email"),
            "res_model": "arcs.donor.funding.request.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_funding_request_id": self.id},
        }

    def action_donor_approve(self):
        self.ensure_one()
        if not self.env.user.has_group("arcs_base.group_finance_officer") \
                and not self.env.user.has_group("arcs_base.group_finance_manager") \
                and not self.env.user.has_group("arcs_base.group_system_admin"):
            raise UserError(_("Only a Finance user can record the donor's decision."))
        if self.state != "requested":
            raise UserError(_("Only requests already sent to the donor can be recorded as approved."))
        if self.amount_approved <= 0:
            raise UserError(_(
                "Enter the amount confirmed by the donor's bank receipt (Amount Confirmed) "
                "before recording approval."))
        if not self.bank_receipt_attached:
            raise UserError(_(
                "You must attach the donor's bank receipt before recording approval.\n\n"
                "Use the paperclip in the chatter to attach the document, then try again."))
        self.write({"decision_date": fields.Date.context_today(self)})
        return self._transition("approved", "donor_approve", comment=self.decision_note)

    def action_donor_reject(self, reason=False):
        self.ensure_one()
        if not self.env.user.has_group("arcs_base.group_finance_officer") \
                and not self.env.user.has_group("arcs_base.group_finance_manager") \
                and not self.env.user.has_group("arcs_base.group_system_admin"):
            raise UserError(_("Only a Finance user can record the donor's decision."))
        if self.state != "requested":
            raise UserError(_("Only requests already sent to the donor can be recorded as rejected."))
        self.write({"decision_date": fields.Date.context_today(self)})
        return self._transition("rejected", "donor_reject", comment=reason or self.decision_note)

    def action_cancel(self, reason=False):
        for r in self:
            if r.state == "approved":
                raise UserError(_("An approved donor funding request cannot be cancelled."))
        return self._transition("cancelled", "cancel", comment=reason)
