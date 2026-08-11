from odoo import api, fields, models


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    project_id = fields.Many2one("arcs.project", string="Project",
                                 domain="[('grant_id','=',grant_id)]")
    activity_id = fields.Many2one("arcs.activity", string="Activity",
                                  domain="[('project_id','=',project_id)]")

    @api.onchange("activity_id")
    def _onchange_activity(self):
        if self.activity_id and self.activity_id.budget_line_id and not self.budget_line_id:
            self.budget_line_id = self.activity_id.budget_line_id
