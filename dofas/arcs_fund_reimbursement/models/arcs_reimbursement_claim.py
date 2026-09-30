from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsReimbursementClaim(models.Model):
    """A bundle of already-approved/posted expenses submitted together as one
    proof package to the donor for validation (SRS states 2-6: Expenditure
    Initiated + Proof Compilation are merged into one mutable 'Compiling'
    state here, since in practice expenses get added and proofs attached
    together over time before a single submission checkpoint). Approval
    unlocks the real arcs.fund.receipt (state 7: Funds Credited); the
    linked donor report closes the loop (state 8: Reporting Completed).

    State 1 (MoU Signed) is deliberately NOT modeled here - a Reimbursement
    grant is is_restricted by definition, so it already gets
    arcs_grant_governance's Agreement Version gate on grant approval for
    free. Nothing about MoU tracking is duplicated in this module.

    Unlike a revolving cycle, claims are NOT restricted to one open claim
    per grant at a time - a donor's MoU may well allow several claims in
    flight together, so this module does not enforce that constraint.
    """

    _name = "arcs.reimbursement.claim"
    _description = "Reimbursement Claim"
    _inherit = ["arcs.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "grant_id, id"

    name = fields.Char(string="Claim Reference", required=True, copy=False,
                       readonly=True, default=lambda s: _("New"), tracking=True)
    grant_id = fields.Many2one(
        "arcs.grant", string="Grant", required=True, tracking=True, ondelete="restrict",
        domain="[('funding_model', '=', 'reimbursement'), ('state', 'in', ('approved', 'active'))]")
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True, string="Donor")
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)

    expense_ids = fields.One2many(
        "arcs.expense", "reimbursement_claim_id", string="Claimed Expenses")
    expense_count = fields.Integer(compute="_compute_amounts")
    claimed_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Sum of linked expenses that are Approved or Posted. Only these "
             "count toward what's actually being claimed from the donor.")

    fund_receipt_id = fields.Many2one(
        "arcs.fund.receipt", string="Fund Receipt", readonly=True, copy=False,
        help="The donor fund receipt that actually credits ARCS once this claim is approved.")
    donor_report_id = fields.Many2one(
        "arcs.donor.report", string="Final Report", readonly=True, copy=False,
        help="The donor report closing out this claim (SRS state 8: Reporting Completed).")

    validation_date = fields.Date(readonly=True, copy=False)
    validation_notes = fields.Text(
        help="The donor's remarks on validation - reason for rejection, or any "
             "conditions attached to approval.")

    state = fields.Selection(
        [("compiling", "Compiling"), ("submitted", "Submission Pending"),
         ("approved", "Validation Approved"), ("rejected", "Validation Rejected"),
         ("funded", "Funds Credited"), ("reported", "Reporting Completed"),
         ("cancelled", "Cancelled")],
        default="compiling", required=True, tracking=True, copy=False)

    _sql_constraints = [
        ("name_uniq", "unique(name, company_id)",
         "The Claim Reference must be unique per company."),
    ]

    # ---------------------------------------------------------------- compute
    @api.depends("expense_ids.amount", "expense_ids.state")
    def _compute_amounts(self):
        for c in self:
            claimed = c.expense_ids.filtered(lambda e: e.state in ("approved", "posted"))
            c.claimed_amount = sum(claimed.mapped("amount"))
            c.expense_count = len(c.expense_ids)

    # --------------------------------------------------------------- create
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "arcs.reimbursement.claim") or _("New")
        return super().create(vals_list)

    # ---------------------------------------------------------------- actions
    def action_submit(self):
        for c in self:
            if c.state != "compiling":
                raise UserError(_("Only a claim being Compiled can be submitted."))
            if not c.expense_ids:
                raise UserError(_(
                    "Add at least one expense to this claim before submitting it."))
            unresolved = c.expense_ids.filtered(lambda e: e.state not in ("approved", "posted"))
            if unresolved:
                raise UserError(_(
                    "Every linked expense must be Approved or Posted before "
                    "submitting this claim - %(n)d expense(s) are not yet.",
                    n=len(unresolved)))
            if c.claimed_amount <= 0:
                raise UserError(_("The claimed amount must be greater than zero."))
            if not self.env["ir.attachment"].search_count(
                    [("res_model", "=", "arcs.reimbursement.claim"), ("res_id", "=", c.id)]):
                raise UserError(_(
                    "Attach the proof package (receipts, invoices, compliance "
                    "forms) before submitting this claim."))
        res = self._transition("submitted", "submit")
        for c in self:
            c.grant_id._governance_create_verifications("reimbursement_claim_submission", c)
        return res

    def action_validate_approve(self):
        for c in self:
            if c.state != "submitted":
                raise UserError(_("Only a Submission Pending claim can be validated."))
            c.grant_id._governance_check_gate("reimbursement_claim_submission", c)
        self.write({"validation_date": fields.Date.context_today(self)})
        return self._transition("approved", "validate_approve")

    def action_validate_reject(self):
        for c in self:
            if c.state != "submitted":
                raise UserError(_("Only a Submission Pending claim can be validated."))
            if not c.validation_notes or not c.validation_notes.strip():
                raise UserError(_(
                    "Enter the donor's remarks explaining the rejection before "
                    "recording it."))
        self.write({"validation_date": fields.Date.context_today(self)})
        return self._transition("rejected", "validate_reject")

    def action_resubmit(self):
        for c in self:
            if c.state != "rejected":
                raise UserError(_("Only a rejected claim can be reopened for corrections."))
        return self._transition("compiling", "resubmit")

    def action_open_fund_receipt(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Record the fund transfer once validation is Approved."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Fund Transfer"),
            "res_model": "arcs.fund.receipt",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_grant_id": self.grant_id.id,
                "default_amount": self.claimed_amount,
                "default_currency_id": self.currency_id.id,
                "default_reimbursement_claim_id": self.id,
            },
        }

    def action_view_fund_receipt(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "arcs.fund.receipt",
            "res_id": self.fund_receipt_id.id, "view_mode": "form", "target": "current",
        }

    def action_open_final_report(self):
        self.ensure_one()
        if self.state != "funded":
            raise UserError(_("The final report can be prepared once funds are Credited."))
        if self.donor_report_id:
            return {
                "type": "ir.actions.act_window", "res_model": "arcs.donor.report",
                "res_id": self.donor_report_id.id, "view_mode": "form", "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Prepare Final Report"),
            "res_model": "arcs.donor.report",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_grant_id": self.grant_id.id, "default_report_type": "financial",
                "default_reimbursement_claim_id": self.id,
            },
        }

    def action_cancel(self, reason=False):
        for c in self:
            if c.state in ("funded", "reported"):
                raise UserError(_(
                    "A claim that has already been funded cannot be cancelled."))
            if c.claimed_amount:
                raise UserError(_(
                    "Claim '%s' already has approved/posted expenses linked to it "
                    "and cannot be cancelled; detach them first or reject/resubmit "
                    "instead.") % c.name)
        return self._transition("cancelled", "cancel", comment=reason)
