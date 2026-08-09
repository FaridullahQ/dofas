from odoo import _, fields, models
from odoo.exceptions import UserError


class McitExpense(models.Model):
    _inherit = "mcit.expense"

    request_id = fields.Many2one("mcit.spend.request", string="Acquisition",
                                 readonly=True, copy=False)

    def _matching_request_commitment(self):
        """The reserve on the acquisition that belongs to THIS expense's
        budget line. Looked up by budget line rather than assumed to be the
        request's single `commitment_id`, so this works the same whether the
        acquisition's approved amount was reserved on one line or split
        across several (one commitment per line, one expense per line -
        see mcit.spend.request._action_create_split_expenses)."""
        self.ensure_one()
        if not self.request_id:
            return self.env["mcit.commitment"]
        return self.request_id.commitment_ids.filtered(
            lambda c: c.state == "confirmed" and c.budget_line_id == self.budget_line_id)[:1]

    def action_approve(self):
        """If the expense comes from an approved request with a still-confirmed
        reserve on this expense's own budget line, adopt that commitment
        instead of reserving again; otherwise fall back to the standard
        self-reserve behaviour."""
        adopt = self.browse()
        for e in self:
            if not e.commitment_id and e._matching_request_commitment():
                adopt |= e
        for e in adopt:
            if e.state != "submitted":
                raise UserError(_("Only submitted expenses can be approved."))
            if e.grant_id.state != "active":
                raise UserError(_("Expenses can only be approved against an active grant."))
            e.commitment_id = e._matching_request_commitment().id
        if adopt:
            adopt._transition("approved", "approve")
        rest = self - adopt
        if rest:
            super(McitExpense, rest).action_approve()
        return True
