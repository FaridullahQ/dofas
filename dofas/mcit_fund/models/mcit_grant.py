from odoo import api, fields, models


class McitGrant(models.Model):
    _inherit = "mcit.grant"

    enforce_cash_availability = fields.Boolean(
        string="Enforce Cash Availability", default=False,
        help="If set (advance-model donors), expenses cannot exceed funds received.")
    fund_receipt_ids = fields.One2many("mcit.fund.receipt", "grant_id", string="Fund Receipts")
    received_total = fields.Monetary(compute="_compute_fund", currency_field="currency_id",
                                     string="Funds Received")

    @api.depends("fund_receipt_ids.amount", "fund_receipt_ids.state")
    def _compute_fund(self):
        Receipt = self.env["mcit.fund.receipt"]
        data = {}
        if self.ids:
            rows = Receipt._read_group(
                [("grant_id", "in", self.ids), ("state", "=", "posted")],
                ["grant_id"], ["amount:sum"])
            data = {g.id: amt for g, amt in rows}
        for grant in self:
            grant.received_total = data.get(grant.id, 0.0)

    def available_cash(self):
        self.ensure_one()
        spent = 0.0
        AAL = self.env["account.analytic.line"]
        if self.analytic_account_id:
            rows = AAL._read_group([("account_id", "=", self.analytic_account_id.id)],
                                   [], ["amount:sum"])
            spent = -(rows[0][0] if rows and rows[0][0] else 0.0)
        return self.received_total - spent
