from odoo import _, models


class ArcsReasonActionMixin(models.AbstractModel):
    """Adds wizard-opening variants of the three action verbs almost every
    approval-style model in this suite exposes - Reject, Cancel, Reset to
    Draft - so a person always has to type a justification before any of
    them fires, and that justification lands on the record's own chatter
    (not just the internal audit log) for anyone reviewing the record later.

    A model doesn't need to override anything here: as long as it defines
    `action_reject`/`action_cancel`/`action_reset_draft` (accepting an
    optional `reason=False` keyword and threading it through to
    `arcs.approval.mixin._transition`'s `comment`, or posting it to the
    chatter directly if it doesn't use that mixin), pointing its buttons at
    `action_reject_wizard` / `action_cancel_wizard` / `action_reset_draft_wizard`
    instead of the raw action is all that's needed. `arcs.approval.mixin`
    already inherits this, so most models get it for free.

    A method name that doesn't exist on the target model is only ever an
    error path (arcs.reason.wizard.action_confirm raises a clear UserError)
    - never a way to reach code the button-clicking user couldn't already
    reach directly, since the wizard runs the call as that same user with
    their normal access rights."""

    _name = "arcs.reason.action.mixin"
    _description = "Reason-Wizard Openers for Reject / Cancel / Reset to Draft"

    def _open_reason_wizard(self, target_action, title):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "arcs.reason.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_res_model": self._name,
                "default_res_id": self.id,
                "default_target_action": target_action,
                "default_title": title,
            },
        }

    def action_reject_wizard(self):
        return self._open_reason_wizard("action_reject", _("Reject"))

    def action_cancel_wizard(self):
        return self._open_reason_wizard("action_cancel", _("Cancel"))

    def action_reset_draft_wizard(self):
        return self._open_reason_wizard("action_reset_draft", _("Reset to Draft"))
