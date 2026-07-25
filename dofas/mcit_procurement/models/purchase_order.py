from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    mcit_grant_id = fields.Many2one("mcit.grant", string="Grant",
                                    domain="[('state','=','active')]")
    mcit_budget_line_id = fields.Many2one(
        "mcit.budget.line", string="Budget Line",
        domain="[('grant_id','=',mcit_grant_id), ('budget_state','=','approved')]")
    mcit_commitment_id = fields.Many2one("mcit.commitment", string="Budget Commitment",
                                         readonly=True, copy=False)

    def button_confirm(self):
        res = super().button_confirm()
        for order in self:
            if order.mcit_budget_line_id and not order.mcit_commitment_id:
                line = order.mcit_budget_line_id
                amount = order.amount_total
                if order.currency_id and line.currency_id and order.currency_id != line.currency_id:
                    amount = order.currency_id._convert(
                        amount, line.currency_id, order.company_id,
                        (order.date_order or fields.Datetime.now()).date())
                # reserve() applies the concurrency-safe hard stop; raises if insufficient.
                commitment = line.reserve(amount, source_ref="purchase.order,%s" % order.id)
                order.mcit_commitment_id = commitment.id
        return res

    def button_cancel(self):
        res = super().button_cancel()
        for order in self:
            if order.mcit_commitment_id and order.mcit_commitment_id.state == "confirmed":
                order.mcit_commitment_id.action_release()
        return res
