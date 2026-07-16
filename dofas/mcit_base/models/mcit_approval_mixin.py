from odoo import models


class McitApprovalMixin(models.AbstractModel):
    """Reusable approval workflow. Inheriting models must define a `state` field.
    Every transition is recorded in the immutable mcit.audit.log."""

    _name = "mcit.approval.mixin"
    _description = "MCIT Approval Workflow Helper"

    def _transition(self, to_state, action, comment=False):
        Log = self.env["mcit.audit.log"].sudo()
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
        return True
