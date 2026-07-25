from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mcit_default_analytic_plan_id = fields.Many2one(
        related="company_id.mcit_default_analytic_plan_id", readonly=False)
    mcit_budget_warn_threshold = fields.Float(
        related="company_id.mcit_budget_warn_threshold", readonly=False)
    mcit_budget_alert_threshold = fields.Float(
        related="company_id.mcit_budget_alert_threshold", readonly=False)
    mcit_currency_rate_policy = fields.Selection(
        related="company_id.mcit_currency_rate_policy", readonly=False)
    mcit_expense_journal_id = fields.Many2one(
        related="company_id.mcit_expense_journal_id", readonly=False)
    mcit_expense_clearing_account_id = fields.Many2one(
        related="company_id.mcit_expense_clearing_account_id", readonly=False)
    mcit_demo_data_enabled = fields.Boolean(
        related="company_id.mcit_demo_data_enabled", readonly=False)
