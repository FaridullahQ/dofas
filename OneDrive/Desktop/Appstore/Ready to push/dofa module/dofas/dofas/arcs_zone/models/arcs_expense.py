from odoo import fields, models


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    zone_id = fields.Many2one("arcs.zone", string="Region / Province", index=True)
    department_id = fields.Many2one("hr.department", string="Department", index=True)
