from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mcit_advance_book = fields.Boolean(
        string="Book Advances to the Ledger", default=False,
        help="When enabled, issuing and liquidating advances posts journal entries.")
    mcit_advance_journal_id = fields.Many2one("account.journal", string="Advance Journal")
    mcit_advance_account_id = fields.Many2one(
        "account.account", string="Advance (Receivable) Account",
        help="Debited when an advance is issued; the holder becomes a debtor.")
    mcit_advance_cash_account_id = fields.Many2one(
        "account.account", string="Advance Cash/Bank Account",
        help="Credited when an advance is issued (the cash leaving HQ).")
    mcit_advance_clearing_account_id = fields.Many2one(
        "account.account", string="Advance Clearing Account",
        help="Debited on liquidation to clear the advance receivable as expenses are justified.")
