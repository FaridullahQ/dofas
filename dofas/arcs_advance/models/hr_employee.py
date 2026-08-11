from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    arcs_advance_count = fields.Integer(compute="_compute_arcs_advance_count")

    def _compute_arcs_advance_count(self):
        Advance = self.env["arcs.advance"]
        for e in self:
            e.arcs_advance_count = Advance.search_count([("employee_id", "=", e.id)])

    def action_view_arcs_advances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Advances - %s") % self.name,
            "res_model": "arcs.advance",
            "view_mode": "tree,form,pivot,graph",
            "domain": [("employee_id", "=", self.id)],
            "context": {"default_employee_id": self.id, "default_advance_type": "employee"},
        }
