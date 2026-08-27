from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsSpendRequestInsufficientFundsWizard(models.TransientModel):
    """Single entry point for every Insufficient Funds recovery path, opened
    from one prominent button on the acquisition instead of a scattered row
    of header buttons. Whichever axis actually triggered the shortfall
    (budget line or Activity/Project/Program), every recovery tool is
    offered together - Finance decides which one actually fits the real
    situation, the system doesn't gate it by axis. Each button here is a
    thin delegate to the acquisition's own existing action method (no
    logic duplicated here at all); clicking one closes this router and
    opens that specific wizard/record in its place."""

    _name = "arcs.spend.request.insufficient.funds.wizard"
    _description = "Resolve Insufficient Funds"

    request_id = fields.Many2one(
        "arcs.spend.request", string="Acquisition", required=True, readonly=True,
        ondelete="cascade")
    currency_id = fields.Many2one(related="request_id.currency_id", readonly=True)
    shortfall_type = fields.Selection(related="request_id.shortfall_type", readonly=True)
    shortfall_amount = fields.Monetary(related="request_id.shortfall_amount", readonly=True)
    insufficient_funds_note = fields.Char(
        related="request_id.insufficient_funds_note", readonly=True)
    activity_id = fields.Many2one(related="request_id.activity_id", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_request_id") or self.env.context.get("active_id")
        request = self.env["arcs.spend.request"].browse(request_id)
        if request.exists():
            if request.state != "insufficient_funds":
                raise UserError(_(
                    "This is only available on requests flagged Insufficient Funds."))
            res["request_id"] = request.id
        return res

    def _delegate(self, method_name):
        self.ensure_one()
        method = getattr(self.request_id, method_name)
        return method()

    def action_choose_different_budget_line(self):
        return self._delegate("action_choose_different_budget_line")

    def action_open_split_wizard(self):
        return self._delegate("action_open_split_wizard")

    def action_request_budget_transfer(self):
        return self._delegate("action_request_budget_transfer")

    def action_request_donor_funding(self):
        return self._delegate("action_request_donor_funding")

    def action_choose_different_activity(self):
        return self._delegate("action_choose_different_activity")

    def action_open_activity_split_wizard(self):
        return self._delegate("action_open_activity_split_wizard")

    def action_reset_draft_wizard(self):
        return self._delegate("action_reset_draft_wizard")

    def action_discard(self):
        return {"type": "ir.actions.act_window_close"}
