from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_submit(self):
        for e in self:
            if e.grant_id.funding_model == "donor_multi_project" and not e.project_id:
                raise UserError(_(
                    "This grant uses the One Donor, Multiple Projects model: "
                    "select the Project this expense belongs to before "
                    "submitting it."))
        return super().action_submit()
