from odoo import _, models
from odoo.exceptions import UserError


class McitFundReceipt(models.Model):
    _inherit = "mcit.fund.receipt"

    def action_post(self):
        # Gate: a bank advice attachment is required before posting.
        for r in self:
            if r.state == "draft":
                count = self.env["ir.attachment"].search_count(
                    [("res_model", "=", "mcit.fund.receipt"), ("res_id", "=", r.id)])
                if not count:
                    raise UserError(_(
                        "Attach the bank advice before posting receipt '%s'.", r.name))
        return super().action_post()
