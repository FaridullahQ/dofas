from odoo import api, fields, models


class McitExpense(models.Model):
    _inherit = "mcit.expense"

    project_id = fields.Many2one("mcit.project", string="Project",
                                 domain="[('grant_id','=',grant_id)]")
    activity_id = fields.Many2one("mcit.activity", string="Activity",
                                  domain="[('project_id','=',project_id)]")

    @api.onchange("activity_id")
    def _onchange_activity(self):
        if self.activity_id and self.activity_id.budget_line_id and not self.budget_line_id:
            self.budget_line_id = self.activity_id.budget_line_id
