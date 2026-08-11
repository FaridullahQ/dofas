from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    arcs_default_analytic_plan_id = fields.Many2one(
        related="company_id.arcs_default_analytic_plan_id", readonly=False)
    arcs_budget_warn_threshold = fields.Float(
        related="company_id.arcs_budget_warn_threshold", readonly=False)
    arcs_budget_alert_threshold = fields.Float(
        related="company_id.arcs_budget_alert_threshold", readonly=False)
    arcs_currency_rate_policy = fields.Selection(
        related="company_id.arcs_currency_rate_policy", readonly=False)
    arcs_expense_journal_id = fields.Many2one(
        related="company_id.arcs_expense_journal_id", readonly=False)
    arcs_expense_clearing_account_id = fields.Many2one(
        related="company_id.arcs_expense_clearing_account_id", readonly=False)
    arcs_demo_data_enabled = fields.Boolean(
        related="company_id.arcs_demo_data_enabled", readonly=False)
