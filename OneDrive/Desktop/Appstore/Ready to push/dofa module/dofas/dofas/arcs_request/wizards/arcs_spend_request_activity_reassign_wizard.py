from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsSpendRequestActivityReassignWizard(models.TransientModel):
    """Recovery action for an acquisition flagged Insufficient Funds on the
    Activity/Project/Program axis (shortfall_type='activity'): pick a
    different activity and send it back to Finance for another commit
    attempt. Mirrors arcs.spend.request.reassign.wizard (the budget-line
    equivalent) exactly, one level up - does not touch amounts, only
    re-targets which activity (and, cascading from it, project/program)
    the reserve will be checked and tagged against."""

    _name = "arcs.spend.request.activity.reassign.wizard"
    _description = "Choose a Different Activity"

    request_id = fields.Many2one(
        "arcs.spend.request", string="Acquisition", required=True, readonly=True,
        ondelete="cascade")
    current_activity_id = fields.Many2one(
        related="request_id.activity_id", string="Current Activity", readonly=True)
    new_activity_id = fields.Many2one(
        "arcs.activity", string="New Activity", required=True,
        domain="[('state', '=', 'approved')]")
    note = fields.Char(string="Reason")
    reference = fields.Char(
        string="Reference", required=True,
        help="Supporting document reference (approval memo, justification, etc.) - "
             "required, together with an attachment, before confirming.")
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="At least one attachment is required - the document backing this "
             "reassignment.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_request_id") or self.env.context.get("active_id")
        request = self.env["arcs.spend.request"].browse(request_id)
        if request.exists():
            res["request_id"] = request.id
        return res

    def action_confirm(self):
        self.ensure_one()
        request = self.request_id
        if request.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        if request.shortfall_type != "activity":
            raise UserError(_(
                "This request is short on the budget line, not Activity/Project/Program "
                "Planned Cost."))
        if self.new_activity_id == request.activity_id:
            raise UserError(_("Choose an activity different from the current one."))
        if not self.reference or not self.reference.strip():
            raise UserError(_("Enter a Reference before confirming."))
        if not self.attachment_ids:
            raise UserError(_(
                "Attach the supporting document before confirming this reassignment."))
        old_activity = request.activity_id
        new_activity = self.new_activity_id
        request.write({
            "activity_id": new_activity.id,
            "project_id": new_activity.project_id.id,
            "program_id": new_activity.project_id.program_id.id,
            "shortfall_amount": 0.0,
            "shortfall_type": "budget_line",
            "insufficient_funds_note": False,
        })
        request.message_post(
            body=_("Reassignment reference: %s") % self.reference,
            attachment_ids=self.attachment_ids.ids,
        )
        request._transition("submitted", "reassign_activity", comment=_(
            "Reassigned from activity '%(old)s' to '%(new)s'.%(note)s") % {
            "old": old_activity.name if old_activity else _("(none)"),
            "new": new_activity.name,
            "note": (" " + self.note) if self.note else ""})
        return {"type": "ir.actions.act_window_close"}
