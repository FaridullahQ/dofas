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
        [("zone", "Zone / Province"), ("employee", "Employee / Staff")],
        required=True,
        default="zone",
        tracking=True,
        help="Select the recipient type:\n"
             "• Zone / Province – advance issued to a field office or provincial team.\n"
             "• Employee / Staff – advance issued directly to an individual staff member "
             "who becomes the accountable holder (debtor).",
    )
    zone_id = fields.Many2one(
        "mcit.zone",
        string="Zone / Province",
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
             "or return the unused cash.",
    )
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
        domain="[('grant_id','=',grant_id)]",
        help="The specific budget line within the selected grant that will absorb this advance. "
             "Only budget lines belonging to the selected grant are shown.",
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
             "Enter this when the holder returns leftover funds.",
    )
    outstanding_amount = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Amount still to be accounted for: Amount Sent − Reported − Returned. "
             "Must reach zero before the advance can be closed.",
    )
    cash_balance = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Remaining cash in the holder's hands: Amount Sent − Reported − Returned. "
             "Equivalent to Outstanding Amount; a positive value means the holder still holds cash.",
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends("amount", "returned_amount", "liquidation_ids.amount", "liquidation_ids.state")
    def _compute_amounts(self):
        for a in self:
            reported = sum(
                a.liquidation_ids.filtered(
                    lambda l: l.state in ("approved", "posted")
                ).mapped("amount")
            )
            a.reported_amount = reported
            a.outstanding_amount = a.amount - reported - a.returned_amount
            a.cash_balance = a.amount - reported - a.returned_amount

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange("zone_id")
    def _onchange_zone(self):
        """Auto-populate Holder from zone manager; auto-fill partner from user."""
        if self.zone_id and self.zone_id.manager_id and not self.holder_user_id:
            self.holder_user_id = self.zone_id.manager_id
        if self.holder_user_id and not self.partner_id:
            self.partner_id = self.holder_user_id.partner_id

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
        elif self.advance_type == "employee":
            self.zone_id = False

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains("advance_type", "zone_id", "holder_user_id")
    def _check_holder(self):
        for a in self:
            if a.advance_type == "zone" and not a.zone_id:
                raise ValidationError(_("Please select a Zone / Province for a zone advance."))
            if a.advance_type == "employee" and not a.holder_user_id:
                raise ValidationError(_("Please select the Holder (Debtor) for an employee advance."))

    @api.constrains("amount")
    def _check_amount_positive(self):
        for a in self:
            if a.amount < 0:
                raise ValidationError(_("The advance amount cannot be negative."))

    @api.constrains("returned_amount")
    def _check_returned_amount(self):
        for a in self:
            if a.returned_amount < 0:
                raise ValidationError(_("The returned cash amount cannot be negative."))
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
            if a.outstanding_amount > 0:
                raise UserError(_(
                    "Advance '%(name)s' still has %(amount).2f %(currency)s outstanding. "
                    "Please liquidate all expenses or record the returned cash first."
                ) % {
                    "name": a.name,
                    "amount": a.outstanding_amount,
                    "currency": a.currency_id.name or "",
                })
        return self._transition("closed", "close")

    def action_cancel(self):
        for a in self:
            if a.state == "issued" and a.liquidation_ids:
                raise UserError(_(
                    "Cannot cancel advance '%(name)s' because it already has liquidation records. "
                    "Cancel or delete the liquidations first."
                ) % {"name": a.name})
        return self._transition("cancelled", "cancel")

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
