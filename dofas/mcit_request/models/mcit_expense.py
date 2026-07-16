from odoo import _, fields, models
from odoo.exceptions import UserError


class McitExpense(models.Model):
    _inherit = "mcit.expense"

    request_id = fields.Many2one("mcit.spend.request", string="Acquisition",
                                 readonly=True, copy=False)

    def action_approve(self):
        """If the expense comes from an approved request whose reserve is still
        confirmed, adopt that commitment instead of reserving again; otherwise
        fall back to the standard self-reserve behaviour."""
        adopt = self.browse()
        for e in self:
            c = e.request_id.commitment_id if e.request_id else False
            if c and c.state == "confirmed" and not e.commitment_id:
                adopt |= e
        for e in adopt:
            if e.state != "submitted":
                raise UserError(_("Only submitted expenses can be approved."))
            if e.grant_id.state != "active":
                raise UserError(_("Expenses can only be approved against an active grant."))
            e.commitment_id = e.request_id.commitment_id.id
        if adopt:
            adopt._transition("approved", "approve")
        rest = self - adopt
        if rest:
            super(McitExpense, rest).action_approve()
        return True
