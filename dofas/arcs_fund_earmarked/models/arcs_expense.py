from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_submit(self):
        for e in self:
            if e.grant_id.funding_model == "earmarked" and not e.activity_id:
                raise UserError(_(
                    "This grant uses the Earmarked model: select the Activity "
                    "this expense belongs to before submitting it."))
        return super().action_submit()
