from odoo import _, fields, models


class McitLifecycleCloseWizard(models.TransientModel):
    _name = "mcit.lifecycle.close.wizard"
    _description = "Force-close confirmation"

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    record_name = fields.Char(readonly=True)
    child_label = fields.Char(readonly=True)        # "projects" / "activities"
    blocker_count = fields.Integer(readonly=True)
    blockers = fields.Text(readonly=True)

    def action_force_close(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id)
        record._force_close()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }