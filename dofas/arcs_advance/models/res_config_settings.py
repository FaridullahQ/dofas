from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    arcs_advance_book = fields.Boolean(related="company_id.arcs_advance_book", readonly=False)
    arcs_advance_journal_id = fields.Many2one(
        related="company_id.arcs_advance_journal_id", readonly=False)
    arcs_advance_account_id = fields.Many2one(
        related="company_id.arcs_advance_account_id", readonly=False)
    arcs_advance_cash_account_id = fields.Many2one(
        related="company_id.arcs_advance_cash_account_id", readonly=False)
    arcs_advance_clearing_account_id = fields.Many2one(
        related="company_id.arcs_advance_clearing_account_id", readonly=False)
