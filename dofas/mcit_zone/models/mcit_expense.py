from odoo import fields, models


class McitExpense(models.Model):
    _inherit = "mcit.expense"

    zone_id = fields.Many2one("mcit.zone", string="Zone / Province", index=True)
    department_id = fields.Many2one("mcit.department", string="Department", index=True)
