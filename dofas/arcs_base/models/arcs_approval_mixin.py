from odoo import _, models


class ArcsApprovalMixin(models.AbstractModel):
    """Reusable approval workflow. Inheriting models must define a `state` field.
    Every transition is recorded in the immutable arcs.audit.log, and - when a
    comment is given and the model has a chatter (mail.thread) - also posted
    there, so a justification typed through a reason wizard (see
    arcs.reason.action.mixin, inherited below) is visible directly on the
    record, not only in the audit trail."""

    _name = "arcs.approval.mixin"
    _inherit = ["arcs.reason.action.mixin"]
    _description = "ARCS Approval Workflow Helper"

    def _transition(self, to_state, action, comment=False):
        Log = self.env["arcs.audit.log"].sudo()
        for record in self:
            from_state = record.state
            record.state = to_state
            Log.create({
                "res_ref": "%s,%s" % (record._name, record.id),
                "action": action,
                "from_state": from_state,
                "to_state": to_state,
                "comment": comment or False,
            })
            if comment and hasattr(record, "message_post"):
                record.message_post(body=_("Reason: %s") % comment)
        return True
