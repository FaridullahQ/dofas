from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mcit_default_analytic_plan_id = fields.Many2one(
        "account.analytic.plan", string="Default Grant Analytic Plan",
        help="Plan under which an analytic account is created per grant.",
    )
    mcit_budget_warn_threshold = fields.Float(
        string="Budget Warning Threshold (%)", default=80.0)
    mcit_budget_alert_threshold = fields.Float(
        string="Budget Alert Threshold (%)", default=90.0)
    mcit_currency_rate_policy = fields.Selection(
        [("transaction", "Transaction date rate"),
         ("inception", "Grant inception (fixed) rate")],
        string="Grant Currency Rate Policy", default="transaction")
    mcit_expense_journal_id = fields.Many2one(
        "account.journal", string="Expense Journal",
        help="Journal used to book grant expense entries.")
    mcit_expense_clearing_account_id = fields.Many2one(
        "account.account", string="Expense Clearing Account",
        help="Counterpart account credited when an expense is posted.")
