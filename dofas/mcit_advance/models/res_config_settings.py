from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mcit_advance_book = fields.Boolean(related="company_id.mcit_advance_book", readonly=False)
    mcit_advance_journal_id = fields.Many2one(
        related="company_id.mcit_advance_journal_id", readonly=False)
    mcit_advance_account_id = fields.Many2one(
        related="company_id.mcit_advance_account_id", readonly=False)
    mcit_advance_cash_account_id = fields.Many2one(
        related="company_id.mcit_advance_cash_account_id", readonly=False)
    mcit_advance_clearing_account_id = fields.Many2one(
        related="company_id.mcit_advance_clearing_account_id", readonly=False)
