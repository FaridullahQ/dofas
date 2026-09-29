from odoo import _, api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ArcsSpendRequestActivityWarningWizard(models.TransientModel):
    _name = "arcs.spend.request.activity.warning.wizard"
    _description = "Activity Insufficient Funds Warning"

    request_id = fields.Many2one("arcs.spend.request", string="Acquisition", required=True, readonly=True)
    activity_available_amount = fields.Monetary(
        string="Available Amount",
        currency_field="currency_id",
        readonly=True
    )
    estimated_amount = fields.Monetary(
        string="Estimated Amount",
        currency_field="currency_id",
        readonly=True
    )
    shortfall = fields.Monetary(
        string="Shortfall",
        currency_field="currency_id",
        readonly=True,
        compute="_compute_shortfall"
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="request_id.currency_id",
        readonly=True
    )
    activity_id = fields.Many2one(
        "arcs.activity",
        related="request_id.activity_id",
        readonly=True
    )

    @api.depends("activity_available_amount", "estimated_amount")
    def _compute_shortfall(self):
        for wizard in self:
            wizard.shortfall = wizard.estimated_amount - wizard.activity_available_amount

    def action_force_submit(self):
        """Force submit the request despite insufficient activity funds."""
        self.ensure_one()

        if not self.request_id:
            raise UserError(_("No acquisition linked to this wizard."))

        _logger.info(f"=== FORCE SUBMIT clicked for request {self.request_id.name} ===")

        try:
            # Call the force submit method on the request
            self.request_id.action_force_submit_ignore_activity()
            _logger.info(f"=== Force submit completed, state: {self.request_id.state} ===")
        except Exception as e:
            _logger.error(f"=== Force submit error: {e} ===")
            raise

        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Cancel the warning and keep request in draft."""
        _logger.info("=== Cancel clicked, closing wizard ===")
        return {'type': 'ir.actions.act_window_close'}
