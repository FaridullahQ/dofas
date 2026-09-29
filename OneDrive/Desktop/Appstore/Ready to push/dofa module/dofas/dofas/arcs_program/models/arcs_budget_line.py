from odoo import fields, models


class ArcsBudgetLine(models.Model):
    _inherit = "arcs.budget.line"

    project_id = fields.Many2one("arcs.project", string="Project")
    activity_id = fields.Many2one("arcs.activity", string="Activity")
