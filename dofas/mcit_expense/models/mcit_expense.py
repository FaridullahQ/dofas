from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class McitExpense(models.Model):
    _name = "mcit.expense"
    _description = "Grant Expense"
    _inherit = ["mcit.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Description", required=True, copy=False,
                       default=lambda s: _("New"), tracking=True)
    grant_id = fields.Many2one("mcit.grant", string="Grant", required=True, tracking=True,
                               domain="[('state','=','active')]",
                               help="The active grant this expense is charged against.")
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True)
    budget_line_id = fields.Many2one("mcit.budget.line", string="Budget Line", required=True,
                                     tracking=True, domain="[('grant_id','=',grant_id)]",
                                     help="Select the approved budget category to charge.")
    partner_id = fields.Many2one("res.partner", string="Supplier")
    date = fields.Date(string="Expense Date", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", tracking=True,
                             help="Enter expense amount in the grant currency.")
    account_id = fields.Many2one("account.account", string="Expense Account",
                                 help="Must be one of the budget line cost accounts.")
    commitment_id = fields.Many2one("mcit.commitment", readonly=True, copy=False)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"),
         ("posted", "Posted"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)

    _sql_constraints = [
        ("amount_positive", "CHECK(amount > 0)", "The expense amount must be greater than zero."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mcit.expense") or _("New")
        return super().create(vals_list)

    @api.onchange("budget_line_id")
    def _onchange_budget_line(self):
        if self.budget_line_id:
            self.grant_id = self.budget_line_id.grant_id
            if not self.account_id and self.budget_line_id.account_ids:
                self.account_id = self.budget_line_id.account_ids[:1]

    @api.constrains("date")
    def _check_date_in_grant(self):
        for e in self:
            g = e.grant_id
            if e.date and g.date_start and g.date_end and not (g.date_start <= e.date <= g.date_end):
                raise ValidationError(_(
                    "The expense date must fall within the grant period (%(s)s to %(en)s).",
                    s=g.date_start, en=g.date_end))

    @api.constrains("account_id", "budget_line_id")
    def _check_account(self):
        for e in self:
            accs = e.budget_line_id.account_ids
            if e.account_id and accs and e.account_id not in accs:
                raise ValidationError(_(
                    "The expense account must be one of the cost accounts on budget line '%s'.",
                    e.budget_line_id.name))

    # Workflow
    def action_submit(self):
        for e in self:
            if e.state != "draft":
                raise UserError(_("Only draft expenses can be submitted."))
        return self._transition("submitted", "submit")

    def action_approve(self):
        for e in self:
            if e.state != "submitted":
                raise UserError(_("Only submitted expenses can be approved."))
            if e.grant_id.state != "active":
                raise UserError(_("Expenses can only be approved against an active grant."))
            # Optional cash-availability check (advance-model donors).
            if e.grant_id.enforce_cash_availability:
                if float_compare(e.amount, e.grant_id.available_cash(),
                                 precision_rounding=e.currency_id.rounding) > 0:
                    raise UserError(_(
                        "Insufficient funds received for this grant to cover the expense."))
            # Budget hard stop (encumber).
            commitment = e.budget_line_id.reserve(e.amount, source_ref="%s,%s" % (e._name, e.id))
            e.commitment_id = commitment.id
        return self._transition("approved", "approve")

    def action_post(self):
        for e in self:
            if e.state != "approved":
                raise UserError(_("Only approved expenses can be posted."))
            e.move_id = e._create_actual_move().id
            if e.commitment_id:
                e.commitment_id.action_consume()
        return self._transition("posted", "post")

    def action_reject(self):
        self._release()
        return self._transition("draft", "reject")

    def action_cancel(self):
        for e in self:
            if e.state == "posted":
                raise UserError(_("Posted expenses cannot be cancelled; reverse the entry."))
        self._release()
        return self._transition("cancelled", "cancel")

    def _release(self):
        for e in self:
            if e.commitment_id and e.commitment_id.state == "confirmed":
                e.commitment_id.action_release()

    # Accounting
    def _company_amount(self):
        self.ensure_one()
        c = self.company_id
        if self.currency_id and c.currency_id and self.currency_id != c.currency_id:
            return self.currency_id._convert(self.amount, c.currency_id, c, self.date)
        return self.amount

    def _get_journal(self):
        j = self.company_id.mcit_expense_journal_id
        if not j:
            j = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)], limit=1)
        if not j:
            raise UserError(_("Configure an Expense Journal in MCIT Settings."))
        return j

    def _create_actual_move(self):
        self.ensure_one()
        if not self.account_id:
            raise UserError(_("An expense account is required before posting."))
        clearing = self.company_id.mcit_expense_clearing_account_id
        if not clearing:
            raise UserError(_("Configure an Expense Clearing Account in MCIT Settings."))
        analytic = self.budget_line_id.analytic_account_id
        if not analytic:
            raise UserError(_("The grant has no analytic account."))
        amount = self._company_amount()
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self._get_journal().id,
            "date": self.date,
            "ref": self.name,
            "company_id": self.company_id.id,
            "line_ids": [
                (0, 0, {"name": self.name, "account_id": self.account_id.id,
                        "debit": amount, "credit": 0.0,
                        "partner_id": self.partner_id.id or False,
                        "analytic_distribution": {str(analytic.id): 100}}),
                (0, 0, {"name": self.name, "account_id": clearing.id,
                        "debit": 0.0, "credit": amount,
                        "partner_id": self.partner_id.id or False}),
            ],
        })
        move.action_post()
        return move

    def action_view_move(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move",
                "res_id": self.move_id.id, "view_mode": "form"}
