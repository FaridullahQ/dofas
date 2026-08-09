from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    mcit_advance_count = fields.Integer(compute="_compute_mcit_advance_count")

    def _compute_mcit_advance_count(self):
        Advance = self.env["mcit.advance"]
        for e in self:
            e.mcit_advance_count = Advance.search_count([("employee_id", "=", e.id)])

    def action_view_mcit_advances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Advances - %s") % self.name,
            "res_model": "mcit.advance",
            "view_mode": "tree,form,pivot,graph",
            "domain": [("employee_id", "=", self.id)],
            "context": {"default_employee_id": self.id, "default_advance_type": "employee"},
        }
