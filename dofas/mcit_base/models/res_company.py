from odoo import _, fields, models
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


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
    mcit_demo_data_enabled = fields.Boolean(
        string="Demo Data Enabled", default=False, copy=False,
        help="Generates a realistic, interconnected demo dataset - donors, grants, "
             "budgets, the full Acquisition Four-Form flow (including an insufficient-"
             "funds recovery), expenses, fund receipts, advances, and assets - to see "
             "every feature in action. Switching this off removes everything it "
             "created, and only what it created; nothing you've entered yourself "
             "is touched.")

    def write(self, vals):
        if "mcit_demo_data_enabled" in vals:
            _logger.info("MCIT demo data toggle write() fired: vals=%s", vals["mcit_demo_data_enabled"])
            turning_on = bool(vals["mcit_demo_data_enabled"])
            to_generate = self.filtered(lambda c: turning_on and not c.mcit_demo_data_enabled)
            to_clear = self.filtered(lambda c: not turning_on and c.mcit_demo_data_enabled)
            res = super().write(vals)
            if to_generate or to_clear:
                if "mcit.demo.data" not in self.env:
                    raise UserError(_(
                        "The demo data generator model (mcit.demo.data) isn't available. "
                        "This means the 'mcit_donor_management' module either isn't "
                        "installed, or hasn't been Upgraded since it was updated to include "
                        "it. Go to Apps, search for 'MCIT Donor Management', and click "
                        "Upgrade (not just Install/refresh), then try the toggle again."))
                if to_generate:
                    _logger.info("MCIT demo data: generating for company %s", to_generate[0].name)
                    self.env["mcit.demo.data"]._generate(to_generate[0])
                    _logger.info("MCIT demo data: generation finished.")
                if to_clear:
                    _logger.info("MCIT demo data: clearing demo records.")
                    self.env["mcit.demo.data"]._clear()
                    _logger.info("MCIT demo data: clear finished.")
            return res
        return super().write(vals)
