from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    reimbursement_claim_id = fields.Many2one(
        "arcs.reimbursement.claim", string="Reimbursement Claim", tracking=True,
        domain="[('grant_id', '=', grant_id), ('state', '=', 'compiling')]",
        help="Required when the grant uses the Reimbursement model: the claim "
             "package this expense will be submitted to the donor under.")
    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_submit(self):
        for e in self:
            if e.grant_id.funding_model == "reimbursement" and not e.reimbursement_claim_id:
                raise UserError(_(
                    "This grant uses the Reimbursement model: select the "
                    "Reimbursement Claim this expense belongs to before "
                    "submitting it."))
        return super().action_submit()
