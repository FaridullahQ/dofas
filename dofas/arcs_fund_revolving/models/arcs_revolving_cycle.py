from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

# States that count as "the cycle is still doing something" - used to enforce
# that only one cycle per grant is open at a time (SRS: cycles run
# sequentially, the next one starts only once the previous one closes).
OPEN_STATES = ("draft", "committed", "funded", "utilizing", "reporting",
               "replenishment_requested")


class ArcsRevolvingCycle(models.Model):
    """One tranche of a Revolving Fund grant: a donor commitment, the funds
    actually transferred for it, the spending allowed against it, the
    utilization report that closes it out, and the replenishment ask that
    follows - matching the 8-step cycle in the Revolving Fund Workflow SRS.

    This model orchestrates existing engines rather than replacing them:
    - the fund transfer is a real arcs.fund.receipt (GL posting, bank
      voucher gate, analytic tagging all untouched);
    - the spend is real arcs.expense records against the grant's normal
      approved budget lines (budget encumbrance untouched);
    - the utilization report is a real arcs.donor.report of type
      'fund_utilization' (attachment gate, PDF, chatter untouched).

    Creating the *next* arcs.revolving.cycle record is what "the donor
    replenishes and the cycle repeats" means here - there is deliberately no
    separate "replenished" state on this model, since the next cycle's own
    fund receipt being posted is that event.
    """

    _name = "arcs.revolving.cycle"
    _description = "Revolving Fund Cycle"
    _inherit = ["arcs.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "grant_id, sequence_no"

    name = fields.Char(string="Commitment Reference", required=True, copy=False,
                       readonly=True, default=lambda s: _("New"), tracking=True)
    grant_id = fields.Many2one(
        "arcs.grant", string="Grant", required=True, tracking=True, ondelete="restrict",
        domain="[('funding_model', '=', 'revolving_fund'), ('state', 'in', ('approved', 'active'))]",
        help="Only grants using the Revolving Fund funding model are eligible.")
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True, string="Donor")
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    sequence_no = fields.Integer(string="Cycle #", readonly=True, copy=False)

    description = fields.Text(
        string="Description / Compliance Notes",
        help="Compliance notes or special instructions for this tranche "
             "(SRS 3.1: 'description field for compliance notes').")

    percentage_committed = fields.Float(
        string="% of Grant", digits=(5, 4),
        help="Portion of the grant's Approved Amount committed in this cycle "
             "(e.g. 0.25 for 25%). Kept in sync with Amount Committed.")
    amount_committed = fields.Monetary(
        string="Amount Committed", currency_field="currency_id", tracking=True)

    allocation_line_ids = fields.One2many(
        "arcs.revolving.cycle.line", "cycle_id", string="Expense Line Allocation",
        help="The approved budget lines this cycle's committed amount is "
             "earmarked against (SRS 3.1: 'specified expense lines').")
    allocation_total = fields.Monetary(
        compute="_compute_allocation_total", store=True, currency_field="currency_id",
        string="Allocated Total")

    fund_receipt_id = fields.Many2one(
        "arcs.fund.receipt", string="Fund Receipt", readonly=True, copy=False,
        help="The donor fund receipt that transferred this cycle's funds.")
    donor_report_id = fields.Many2one(
        "arcs.donor.report", string="Utilization Report", readonly=True, copy=False,
        help="The Fund Utilization donor report that closes out this cycle's spending.")
    expense_ids = fields.One2many("arcs.expense", "revolving_cycle_id", string="Expenses")
    expense_count = fields.Integer(compute="_compute_expense_count")

    amount_spent = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        string="Amount Spent",
        help="Sum of approved/posted expenses charged to this cycle.")
    amount_available = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        string="Available This Cycle",
        help="Funds received for this cycle minus what has been spent against "
             "it - the hard ceiling for new expenses while the cycle is Utilizing.")
    utilization_pct = fields.Float(
        string="Utilization (%)", compute="_compute_amounts", store=True)

    replenishment_amount_requested = fields.Monetary(
        string="Replenishment Requested", currency_field="currency_id", copy=False,
        help="Amount to ask the donor to top up. Defaults to Amount Spent once "
             "the utilization report is approved; stays editable until sent.")
    replenishment_requested_date = fields.Date(readonly=True, copy=False)
    email_sent = fields.Boolean(string="Replenishment Emailed", readonly=True, copy=False)
    email_sent_date = fields.Datetime(readonly=True, copy=False)

    state = fields.Selection(
        [("draft", "Draft"), ("committed", "Committed"), ("funded", "Funded"),
         ("utilizing", "Utilizing"), ("reporting", "Reporting"),
         ("replenishment_requested", "Replenishment Requested"),
         ("closed", "Closed"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)

    _sql_constraints = [
        ("name_uniq", "unique(name, company_id)",
         "The Commitment Reference must be unique per company."),
        ("percentage_range", "CHECK(percentage_committed >= 0 AND percentage_committed <= 1)",
         "The percentage of grant must be between 0% and 100%."),
        ("amount_committed_non_negative", "CHECK(amount_committed >= 0)",
         "The committed amount cannot be negative."),
    ]

    # ---------------------------------------------------------------- compute
    @api.depends("allocation_line_ids.amount")
    def _compute_allocation_total(self):
        for c in self:
            c.allocation_total = sum(c.allocation_line_ids.mapped("amount"))

    def _compute_expense_count(self):
        for c in self:
            c.expense_count = len(c.expense_ids)

    @api.depends("fund_receipt_id.amount", "fund_receipt_id.state",
                "expense_ids.amount", "expense_ids.state")
    def _compute_amounts(self):
        for c in self:
            received = c.fund_receipt_id.amount if c.fund_receipt_id.state == "posted" else 0.0
            spent = sum(c.expense_ids.filtered(
                lambda e: e.state in ("approved", "posted")).mapped("amount"))
            c.amount_spent = spent
            c.amount_available = received - spent
            c.utilization_pct = (100.0 * spent / received) if received else 0.0

    # ------------------------------------------------------------- onchange
    @api.onchange("percentage_committed")
    def _onchange_percentage_committed(self):
        if self.grant_id and self.grant_id.approved_amount:
            new_amount = self.grant_id.approved_amount * (self.percentage_committed or 0.0)
            rounding = self.currency_id.rounding or 0.01
            if float_compare(new_amount, self.amount_committed or 0.0,
                             precision_rounding=rounding) != 0:
                self.amount_committed = new_amount

    @api.onchange("amount_committed")
    def _onchange_amount_committed(self):
        if self.grant_id and self.grant_id.approved_amount:
            new_pct = (self.amount_committed or 0.0) / self.grant_id.approved_amount
            if float_compare(new_pct, self.percentage_committed or 0.0, precision_digits=4) != 0:
                self.percentage_committed = new_pct

    # --------------------------------------------------------------- create
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "arcs.revolving.cycle") or _("New")
            if vals.get("grant_id") and not vals.get("sequence_no"):
                vals["sequence_no"] = self.search_count(
                    [("grant_id", "=", vals["grant_id"])]) + 1
        return super().create(vals_list)

    # ------------------------------------------------------------ constrains
    @api.constrains("grant_id", "state")
    def _check_single_open_cycle(self):
        for c in self.filtered(lambda x: x.state in OPEN_STATES):
            others = self.search([
                ("grant_id", "=", c.grant_id.id), ("state", "in", list(OPEN_STATES)),
                ("id", "!=", c.id)])
            if others:
                raise ValidationError(_(
                    "Grant '%(g)s' already has an open Revolving Fund Cycle "
                    "(%(o)s). Close or cancel it before opening another - "
                    "cycles run sequentially, not in parallel.",
                    g=c.grant_id.display_name, o=others[0].name))

    @api.constrains("amount_committed", "grant_id", "state")
    def _check_cumulative_commitment(self):
        for c in self.filtered(lambda x: x.state != "cancelled"):
            grant = c.grant_id
            if not grant.approved_amount:
                continue
            siblings = self.search([
                ("grant_id", "=", grant.id), ("state", "!=", "cancelled")])
            total = sum(siblings.mapped("amount_committed"))
            if float_compare(total, grant.approved_amount,
                             precision_rounding=c.currency_id.rounding or 0.01) > 0:
                raise ValidationError(_(
                    "The total committed across all cycles of grant '%(g)s' "
                    "(%(t).2f) would exceed its Approved Amount (%(a).2f).",
                    g=grant.display_name, t=total, a=grant.approved_amount))

    # ---------------------------------------------------------------- actions
    def action_commit(self):
        for c in self:
            if c.state != "draft":
                raise UserError(_("Only a draft cycle can be committed."))
            if c.grant_id.funding_model != "revolving_fund":
                raise UserError(_(
                    "Grant '%s' is not on the Revolving Fund model.") % c.grant_id.display_name)
            if c.amount_committed <= 0:
                raise UserError(_("Enter an amount (or percentage) greater than zero."))
            if not c.allocation_line_ids:
                raise UserError(_(
                    "Allocate this cycle's committed amount across at least one "
                    "budget line before committing."))
            if any(float_compare(l.amount, 0.0, precision_rounding=c.currency_id.rounding or 0.01) <= 0
                  for l in c.allocation_line_ids):
                raise UserError(_(
                    "Every expense-line allocation must have an amount greater "
                    "than zero before committing."))
            if float_compare(c.allocation_total, c.amount_committed,
                             precision_rounding=c.currency_id.rounding or 0.01) != 0:
                raise UserError(_(
                    "The expense-line allocation (%(al).2f) must add up exactly "
                    "to the Amount Committed (%(ac).2f).",
                    al=c.allocation_total, ac=c.amount_committed))
        return self._transition("committed", "commit")

    def action_open_fund_receipt(self):
        self.ensure_one()
        if self.state != "committed":
            raise UserError(_("Record the fund transfer once the cycle is Committed."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Fund Transfer"),
            "res_model": "arcs.fund.receipt",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_grant_id": self.grant_id.id,
                "default_amount": self.amount_committed,
                "default_currency_id": self.currency_id.id,
                "default_revolving_cycle_id": self.id,
            },
        }

    def action_view_fund_receipt(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "arcs.fund.receipt",
            "res_id": self.fund_receipt_id.id, "view_mode": "form", "target": "current",
        }

    def action_open_utilization_report(self):
        self.ensure_one()
        if self.state != "utilizing":
            raise UserError(_(
                "The utilization report can be prepared once the cycle is Utilizing."))
        if self.donor_report_id:
            return {
                "type": "ir.actions.act_window", "res_model": "arcs.donor.report",
                "res_id": self.donor_report_id.id, "view_mode": "form", "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Prepare Utilization Report"),
            "res_model": "arcs.donor.report",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_grant_id": self.grant_id.id,
                "default_report_type": "fund_utilization",
                "default_revolving_cycle_id": self.id,
            },
        }

    def action_request_replenishment(self):
        self.ensure_one()
        if self.state != "reporting":
            raise UserError(_(
                "Submit and approve the utilization report before requesting "
                "replenishment."))
        if not self.donor_report_id or self.donor_report_id.state != "approved":
            raise UserError(_(
                "The utilization report must be Approved before requesting "
                "replenishment."))
        if not self.replenishment_amount_requested:
            self.replenishment_amount_requested = self.amount_spent
        self.write({"replenishment_requested_date": fields.Date.context_today(self)})
        self._transition("replenishment_requested", "request_replenishment")
        return self.action_open_send_wizard()

    def action_open_send_wizard(self):
        self.ensure_one()
        if self.state != "replenishment_requested":
            raise UserError(_(
                "Use 'Request Replenishment' first before emailing the donor."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Replenishment Request"),
            "res_model": "arcs.revolving.replenishment.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_cycle_id": self.id},
        }

    def action_close(self):
        for c in self:
            if c.state != "replenishment_requested":
                raise UserError(_(
                    "Only a cycle whose replenishment has been requested can "
                    "be closed."))
            if not c.donor_report_id or c.donor_report_id.state != "approved":
                raise UserError(_(
                    "The utilization report must be Approved before closing "
                    "this cycle."))
        return self._transition("closed", "close")

    def action_create_next_cycle(self):
        self.ensure_one()
        if self.state not in ("closed", "cancelled"):
            raise UserError(_("Close (or cancel) this cycle before opening the next one."))
        next_lines = [(0, 0, {"budget_line_id": l.budget_line_id.id, "amount": 0.0})
                     for l in self.allocation_line_ids]
        new_cycle = self.copy({
            "amount_committed": 0.0,
            "percentage_committed": 0.0,
            "fund_receipt_id": False,
            "donor_report_id": False,
            "replenishment_amount_requested": 0.0,
            "replenishment_requested_date": False,
            "email_sent": False,
            "email_sent_date": False,
            "state": "draft",
            "allocation_line_ids": next_lines,
        })
        return {
            "type": "ir.actions.act_window", "res_model": "arcs.revolving.cycle",
            "res_id": new_cycle.id, "view_mode": "form", "target": "current",
        }

    def action_cancel(self, reason=False):
        for c in self:
            if c.state == "closed":
                raise UserError(_("A closed cycle cannot be cancelled."))
            if c.amount_spent:
                raise UserError(_(
                    "Cycle '%s' already has spending recorded against it and "
                    "cannot be cancelled; close it instead.") % c.name)
        return self._transition("cancelled", "cancel", comment=reason)
