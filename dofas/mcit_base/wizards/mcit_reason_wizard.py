from odoo import _, fields, models
from odoo.exceptions import UserError


class McitReasonWizard(models.TransientModel):
    """Generic 'confirm this with a reason' popup used by every Reject,
    Cancel, and Reset to Draft button across this suite (opened via
    mcit.reason.action.mixin's action_*_wizard methods rather than the raw
    action). Runs the underlying action as the current user with their
    normal access rights - it is a UI step, not a privilege boundary - and
    forwards the typed reason so the target model can log it (typically via
    mcit.approval.mixin._transition, which also posts it to the chatter)."""

    _name = "mcit.reason.wizard"
    _description = "Confirm Action With Reason"

    res_model = fields.Char(required=True, readonly=True)
    res_id = fields.Integer(required=True, readonly=True)
    target_action = fields.Char(required=True, readonly=True)
    title = fields.Char(readonly=True)
    reason = fields.Text(
        required=True, string="Justification / Reason",
        help="Recorded on the record's own activity log and audit trail.")

    def action_confirm(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_("Enter a justification before confirming."))
        record = self.env[self.res_model].browse(self.res_id)
        if not record.exists():
            raise UserError(_(
                "The record this action was requested on no longer exists."))
        method = getattr(record, self.target_action, None)
        if not callable(method):
            raise UserError(_(
                "'%s' is not available on this record.") % self.target_action)
        method(reason=self.reason)
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        return {"type": "ir.actions.act_window_close"}
