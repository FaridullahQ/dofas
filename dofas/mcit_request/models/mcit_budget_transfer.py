from odoo import _, fields, models


class McitBudgetTransfer(models.Model):
    """Link an internal budget transfer back to the acquisition it is
    covering, and resume that acquisition's workflow once Finance approves
    the transfer. Kept in mcit_request (not mcit_budget) so mcit.budget.transfer
    stays a reusable primitive with no knowledge of the acquisition workflow."""

    _inherit = "mcit.budget.transfer"

    spend_request_id = fields.Many2one(
        "mcit.spend.request", string="Related Acquisition", copy=False,
        help="If set, approving this transfer sends the acquisition back to "
             "Finance for another commit attempt.")

    def action_approve(self):
        res = super().action_approve()
        for t in self:
            request = t.spend_request_id
            if request and request.state == "insufficient_funds":
                request.write({"shortfall_amount": 0.0, "insufficient_funds_note": False})
                request._transition("submitted", "budget_transfer_approved", comment=_(
                    "Internal budget transfer %s approved; sent back to Finance.") % t.name)
        return res
