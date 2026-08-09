from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class McitAdvance(models.Model):
    _name = "mcit.advance"
    _description = "Cash Advance"
    _inherit = ["mcit.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        required=True,
        default=lambda s: _("New"),
        copy=False,
        readonly=True,
        help="Auto-generated reference number assigned when the advance is saved. "
             "Use this code to track and reference this advance in correspondence and reports.",
    )
    advance_type = fields.Selection(
        [("zone", "Region / Province"), ("employee", "Employee / Staff")],
        required=True,
        default="zone",
        tracking=True,
        help="Select the recipient type:\n"
             "• Region / Province – advance issued to a field office or provincial team.\n"
             "• Employee / Staff – advance issued directly to an individual staff member "
             "who becomes the accountable holder (debtor).",
    )
    zone_id = fields.Many2one(
        "mcit.zone",
        string="Region / Province",
        tracking=True,
        help="Select the zone or province that will receive and manage this advance. "
             "The zone manager is automatically suggested as the Holder.",
    )
    holder_user_id = fields.Many2one(
        "res.users",
        string="Holder (Debtor)",
        tracking=True,
        help="The person financially responsible for this advance. "
             "They are obligated to liquidate the full amount through justified expenses "
             "or return the unused cash. For an Employee/Staff advance this is normally "
             "derived automatically from Employee below (kept as its own field because "
             "record-rule and liquidation-ownership checks need a real login to compare "
             "against, which an hr.employee record doesn't guarantee).",
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Employee", tracking=True,
        help="The staff member who holds and is accountable for this advance. "
             "Selecting an employee automatically fills in the Holder (their linked "
             "user, if any) and the debtor Partner below, and surfaces their "
             "Department and Position for reporting.",
    )
    department_id = fields.Many2one(
        related="employee_id.department_id", store=True, string="Department")
    job_id = fields.Many2one(
        related="employee_id.job_id", store=True, string="Position")
    # ── NEW: Partner field for charging / accounting purposes ──────────────────
    partner_id = fields.Many2one(
        "res.partner",
        string="Advance To (Partner)",
        tracking=True,
        help="The partner record linked to this advance for accounting and charging purposes. "
             "For employee advances, this is typically the employee's related partner. "
             "Select the individual or entity that will be debited in the payable/receivable ledger.",
    )
    grant_id = fields.Many2one(
        "mcit.grant",
        string="Grant",
        tracking=True,
        help="The donor grant funding this advance. "
             "Selecting a grant filters the available budget lines to only those belonging to it.",
    )
    budget_line_id = fields.Many2one(
        "mcit.budget.line",
        string="Budget Line",
        domain="[('grant_id','=',grant_id), ('budget_state','=','approved')]",
        help="The specific budget line within the selected grant that will absorb this advance. "
             "Only budget lines on an Approved budget version, belonging to the selected grant, "
             "are shown.",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda s: s.env.company,
        help="Company issuing this advance.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda s: s.env.company.currency_id,
        help="Currency in which the advance is disbursed. "
             "The system will convert to the company's base currency when posting journal entries.",
    )
    amount = fields.Monetary(
        string="Amount Sent",
        currency_field="currency_id",
        tracking=True,
        help="Total cash amount disbursed to the holder. "
             "Must be greater than zero before the advance can be issued.",
    )
    date = fields.Date(
        default=fields.Date.context_today,
        tracking=True,
        help="Date the advance was (or will be) disbursed. "
             "This date is used for currency conversion and journal entry posting.",
    )
    reference = fields.Char(
        help="External reference such as a payment voucher number, cheque number, or "
             "bank transfer reference. Used for reconciliation and audit trail purposes.",
    )
    note = fields.Text(
        help="Free-text remarks about this advance — e.g. purpose, conditions, or instructions "
             "for the holder regarding liquidation deadlines.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("issued", "Issued"), ("closed", "Closed"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        help="Lifecycle of the advance:\n"
             "• Draft – being prepared, not yet disbursed.\n"
             "• Issued – cash has been sent to the holder; liquidation can begin.\n"
             "• Closed – fully liquidated or all outstanding cash returned.\n"
             "• Cancelled – voided before or during issuance (no liquidations allowed).",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Issuance Entry",
        readonly=True,
        copy=False,
        help="Journal entry automatically created when the advance is issued (if ledger booking is enabled in settings).",
    )
    liquidation_ids = fields.One2many(
        "mcit.advance.liquidation",
        "advance_id",
        string="Liquidations",
        help="Liquidation records submitted by the holder to justify expenses against this advance.",
    )
    liquidation_count = fields.Integer(compute="_compute_liquidation_count")
    reported_amount = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Sum of all approved or posted liquidation amounts. "
             "Represents expenses already justified and accepted.",
    )
    returned_amount = fields.Monetary(
        string="Cash Returned",
        currency_field="currency_id",
        tracking=True,
        help="Amount of unspent cash physically returned by the holder to HQ. "
             "Enter this directly, or use the Settle Advance action to record it "
             "together with a real journal entry and a mandatory receipt/slip.",
    )
    reimbursed_amount = fields.Monetary(
        string="Cash Reimbursed to Holder",
        currency_field="currency_id",
        tracking=True,
        help="Amount paid back to the holder because they spent more than this "
             "advance and covered the difference themselves. Only meaningful when "
             "Allow Liquidation Above Advance is enabled below. Set via the "
             "Settle Advance action together with a real journal entry and a "
             "mandatory payment slip.",
    )
    allow_over_liquidation = fields.Boolean(
        string="Allow Liquidation Above Advance", default=False, tracking=True,
        help="Off by default, matching the normal rule that a holder cannot justify "
             "more than what they were given. Switch on for the (unusual but valid) "
             "case where the holder may legitimately spend more than the advance and "
             "front the difference themselves - e.g. an acquisition whose confirmed "
             "price can end up a little higher than the advance issued for it - which "
             "is then paid back to them via Settle Advance instead of being blocked.",
    )
    outstanding_amount = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Amount still to be accounted for: Amount Sent + Reimbursed − Reported − "
             "Returned. Positive means the holder still holds cash or hasn't justified "
             "everything; negative means the holder is owed a reimbursement for having "
             "spent more than the advance (only possible when Allow Liquidation Above "
             "Advance is on). Must reach exactly zero before the advance can be closed.",
    )
    cash_balance = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Remaining cash in the holder's hands: Amount Sent + Reimbursed − Reported "
             "− Returned. Equivalent to Outstanding Amount; positive means the holder "
             "still holds cash, negative means they are owed a reimbursement.",
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends("amount", "returned_amount", "reimbursed_amount",
                "liquidation_ids.amount", "liquidation_ids.state")
    def _compute_amounts(self):
        for a in self:
            reported = sum(
                a.liquidation_ids.filtered(
                    lambda l: l.state in ("approved", "posted")
                ).mapped("amount")
            )
            a.reported_amount = reported
            balance = a.amount + a.reimbursed_amount - reported - a.returned_amount
            a.outstanding_amount = balance
            a.cash_balance = balance

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange("zone_id")
    def _onchange_zone(self):
        """Auto-populate Holder from zone manager; auto-fill partner from user."""
        if self.zone_id and self.zone_id.manager_id and not self.holder_user_id:
            self.holder_user_id = self.zone_id.manager_id
        if self.holder_user_id and not self.partner_id:
            self.partner_id = self.holder_user_id.partner_id

    @api.onchange("employee_id")
    def _onchange_employee(self):
        """Derive the Holder (login) and debtor Partner from the selected
        employee. Both stay editable afterwards in case the employee has no
        linked user or a different partner should be charged."""
        if self.employee_id:
            if self.employee_id.user_id:
                self.holder_user_id = self.employee_id.user_id
            partner = (self.employee_id.user_id.partner_id
                      if self.employee_id.user_id else False)
            if partner:
                self.partner_id = partner

    @api.onchange("holder_user_id")
    def _onchange_holder_user(self):
        """Auto-fill partner from the selected user's linked partner record."""
        if self.holder_user_id and not self.partner_id:
            self.partner_id = self.holder_user_id.partner_id

    @api.onchange("advance_type")
    def _onchange_advance_type(self):
        """Clear type-specific fields when switching advance type."""
        if self.advance_type == "zone":
            self.holder_user_id = False
            self.employee_id = False
        elif self.advance_type == "employee":
            self.zone_id = False

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains("advance_type", "zone_id", "employee_id")
    def _check_holder(self):
        for a in self:
            if a.advance_type == "zone" and not a.zone_id:
                raise ValidationError(_("Please select a Region / Province for a zone advance."))
            if a.advance_type == "employee" and not a.employee_id:
                raise ValidationError(_("Please select the Employee for an employee advance."))

    @api.constrains("amount")
    def _check_amount_positive(self):
        for a in self:
            if a.amount < 0:
                raise ValidationError(_("The advance amount cannot be negative."))

    @api.constrains("returned_amount", "reimbursed_amount")
    def _check_returned_amount(self):
        for a in self:
            if a.returned_amount < 0:
                raise ValidationError(_("The returned cash amount cannot be negative."))
            if a.reimbursed_amount < 0:
                raise ValidationError(_("The reimbursed cash amount cannot be negative."))
            if a.returned_amount > a.amount:
                raise ValidationError(_(
                    "Returned cash (%(ret)s) cannot exceed the total Amount Sent (%(sent)s)."
                ) % {"ret": a.returned_amount, "sent": a.amount})

    @api.constrains("date")
    def _check_date(self):
        for a in self:
            if not a.date:
                raise ValidationError(_("The advance date is required."))

    # ── Sequence ──────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("mcit.advance") or _("New")
                )
            # Auto-fill holder/partner from employee if not provided
            if vals.get("employee_id") and not vals.get("holder_user_id"):
                employee = self.env["hr.employee"].browse(vals["employee_id"])
                if employee.user_id:
                    vals["holder_user_id"] = employee.user_id.id
            # Auto-fill partner from user if not provided
            if vals.get("holder_user_id") and not vals.get("partner_id"):
                user = self.env["res.users"].browse(vals["holder_user_id"])
                if user.partner_id:
                    vals["partner_id"] = user.partner_id.id
        return super().create(vals_list)

    # ── State transitions ─────────────────────────────────────────────────────

    def action_issue(self):
        for a in self:
            if a.state != "draft":
                raise UserError(_("Only draft advances can be issued."))
            if not a.amount or a.amount <= 0:
                raise UserError(_("The advance amount must be greater than zero before issuing."))
            if a.advance_type == "employee" and not a.partner_id:
                raise UserError(_(
                    "Please set the Advance To (Partner) before issuing an employee advance."
                ))
            if a.company_id.mcit_advance_book:
                a.move_id = a._create_issue_move().id
        return self._transition("issued", "issue")

    def action_close(self):
        for a in self:
            if a.state != "issued":
                raise UserError(_("Only issued advances can be closed."))
            if a.currency_id.compare_amounts(a.outstanding_amount, 0.0) != 0:
                if a.outstanding_amount > 0:
                    raise UserError(_(
                        "Advance '%(name)s' still has %(amount).2f %(currency)s outstanding. "
                        "Please liquidate all expenses or record the returned cash first."
                    ) % {
                        "name": a.name,
                        "amount": a.outstanding_amount,
                        "currency": a.currency_id.name or "",
                    })
                else:
                    raise UserError(_(
                        "Advance '%(name)s' still owes the holder %(amount).2f %(currency)s "
                        "in reimbursement. Use Settle Advance to pay it back first."
                    ) % {
                        "name": a.name,
                        "amount": -a.outstanding_amount,
                        "currency": a.currency_id.name or "",
                    })
        return self._transition("closed", "close")

    def action_cancel(self, reason=False):
        for a in self:
            if a.state == "issued" and a.liquidation_ids:
                raise UserError(_(
                    "Cannot cancel advance '%(name)s' because it already has liquidation records. "
                    "Cancel or delete the liquidations first."
                ) % {"name": a.name})
        return self._transition("cancelled", "cancel", comment=reason)

    # ── Journal entry helpers ─────────────────────────────────────────────────

    def _company_amount(self, amount):
        self.ensure_one()
        c = self.company_id
        if self.currency_id and c.currency_id and self.currency_id != c.currency_id:
            return self.currency_id._convert(
                amount, c.currency_id, c, self.date or fields.Date.context_today(self)
            )
        return amount

    def _create_issue_move(self):
        self.ensure_one()
        c = self.company_id
        journal = c.mcit_advance_journal_id
        adv = c.mcit_advance_account_id
        cash = c.mcit_advance_cash_account_id
        if not journal or not adv or not cash:
            raise UserError(_(
                "Please configure the Advance Journal and Accounts under "
                "Settings → MCIT Configuration before issuing advances."
            ))
        amount = self._company_amount(self.amount)
        ref = _("Advance: %s") % self.name
        move_vals = {
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.date,
            "ref": ref,
            "company_id": c.id,
            "line_ids": [
                (0, 0, {
                    "name": ref,
                    "account_id": adv.id,
                    "partner_id": self.partner_id.id if self.partner_id else False,
                    "debit": amount,
                    "credit": 0.0,
                }),
                (0, 0, {
                    "name": ref,
                    "account_id": cash.id,
                    "partner_id": self.partner_id.id if self.partner_id else False,
                    "debit": 0.0,
                    "credit": amount,
                }),
            ],
        }
        move = self.env["account.move"].sudo().create(move_vals)
        move.action_post()
        return move

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }

    def _compute_liquidation_count(self):
        for a in self:
            a.liquidation_count = len(a.liquidation_ids)

    def action_create_liquidation(self):
        self.ensure_one()
        if self.state != "issued":
            raise UserError(_("Only issued advances can be liquidated."))
        return {
            "type": "ir.actions.act_window",
            "name": _("New Liquidation"),
            "res_model": "mcit.advance.liquidation",
            "view_mode": "form",
            "target": "current",
            "context": {"default_advance_id": self.id},
        }

    def action_open_settlement_wizard(self):
        self.ensure_one()
        if self.state != "issued":
            raise UserError(_("Only issued advances can be settled."))
        if self.currency_id.compare_amounts(self.outstanding_amount, 0.0) == 0:
            raise UserError(_(
                "There is nothing to settle - Outstanding is already zero. "
                "You can Close this advance directly."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Settle Advance"),
            "res_model": "mcit.advance.settlement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_advance_id": self.id},
        }

    def action_view_liquidations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Liquidations"),
            "res_model": "mcit.advance.liquidation",
            "view_mode": "tree,form",
            "domain": [("advance_id", "=", self.id)],
            "context": {"default_advance_id": self.id},
        }
