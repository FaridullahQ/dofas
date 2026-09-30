from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    revolving_cycle_id = fields.Many2one(
        "arcs.revolving.cycle", string="Revolving Fund Cycle", tracking=True,
        domain="[('grant_id', '=', grant_id), ('state', '=', 'utilizing')]",
        help="Required when the grant uses the Revolving Fund model: the "
             "open cycle this expense is charged against.")
    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_submit(self):
        for e in self:
            if e.grant_id.funding_model == "revolving_fund" and not e.revolving_cycle_id:
                raise UserError(_(
                    "This grant uses the Revolving Fund model: select the "
                    "Revolving Fund Cycle this expense belongs to before "
                    "submitting it."))
        return super().action_submit()
