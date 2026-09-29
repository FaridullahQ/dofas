from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    arcs_advance_book = fields.Boolean(
        string="Book Advances to the Ledger", default=False,
        help="When enabled, issuing and liquidating advances posts journal entries.")
    arcs_advance_journal_id = fields.Many2one("account.journal", string="Advance Journal")
    arcs_advance_account_id = fields.Many2one(
        "account.account", string="Advance (Receivable) Account",
        help="Debited when an advance is locked; the holder becomes a debtor at that "
             "point, before any cash has actually moved.")
    arcs_advance_payable_account_id = fields.Many2one(
        "account.account", string="Advances Payable / Clearing Account",
        help="Liability account credited when an advance is locked (the amount is "
             "committed and the employee already debited, but cash hasn't moved yet) "
             "and debited when the advance is actually disbursed - clearing that "
             "liability as the cash leaves. Must be configured before any advance can "
             "be locked or disbursed.")
    arcs_advance_cash_account_id = fields.Many2one(
        "account.account", string="Advance Cash/Bank Account",
        help="Credited when an advance is issued (the cash leaving HQ).")
    arcs_advance_clearing_account_id = fields.Many2one(
        "account.account", string="Advance Clearing Account",
        help="Debited on liquidation to clear the advance receivable as expenses are justified.")
