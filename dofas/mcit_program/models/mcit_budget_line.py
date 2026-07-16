from odoo import fields, models


class McitBudgetLine(models.Model):
    _inherit = "mcit.budget.line"

    project_id = fields.Many2one("mcit.project", string="Project")
    activity_id = fields.Many2one("mcit.activity", string="Activity")
