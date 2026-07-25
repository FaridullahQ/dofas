from odoo import _, api, fields, models
from odoo.exceptions import UserError


class McitSpendRequestReassignWizard(models.TransientModel):
    """Recovery action for an acquisition flagged Insufficient Funds: pick a
    different budget line and send it back to Finance for another commit
    attempt. Does not touch amounts - only re-targets the reserve."""

    _name = "mcit.spend.request.reassign.wizard"
    _description = "Choose a Different Budget Line"

    request_id = fields.Many2one(
        "mcit.spend.request", string="Acquisition", required=True, readonly=True,
        ondelete="cascade")
    current_budget_line_id = fields.Many2one(
        related="request_id.budget_line_id", string="Current Budget Line", readonly=True)
    new_budget_line_id = fields.Many2one(
        "mcit.budget.line", string="New Budget Line", required=True,
        domain="[('budget_state', '=', 'approved')]")
    note = fields.Char(string="Reason")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_request_id") or self.env.context.get("active_id")
        request = self.env["mcit.spend.request"].browse(request_id)
        if request.exists():
            res["request_id"] = request.id
        return res

    def action_confirm(self):
        self.ensure_one()
        request = self.request_id
        if request.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        if self.new_budget_line_id == request.budget_line_id:
            raise UserError(_("Choose a budget line different from the current one."))
        old_line = request.budget_line_id
        request.write({
            "budget_line_id": self.new_budget_line_id.id,
            "shortfall_amount": 0.0,
            "insufficient_funds_note": False,
        })
        request._transition("submitted", "reassign_budget_line", comment=_(
            "Reassigned from '%(old)s' to '%(new)s'.%(note)s") % {
            "old": old_line.name, "new": self.new_budget_line_id.name,
            "note": (" " + self.note) if self.note else ""})
        return {"type": "ir.actions.act_window_close"}
