from odoo import api, fields, models


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    project_id = fields.Many2one("arcs.project", string="Project",
                                 domain="[('grant_id','=',grant_id)]")
    activity_id = fields.Many2one("arcs.activity", string="Activity",
                                  domain="[('project_id','=',project_id)]")

    @api.onchange("activity_id")
    def _onchange_activity(self):
        """Activities no longer carry their own budget_line_id (they get
        their budget context transitively through Project -> Program now) -
        suggest the budget line from the activity's own Program instead,
        the top of that same cascade, when one is configured there."""
        if self.activity_id and not self.budget_line_id:
            program = self.activity_id.project_id.program_id
            if program and program.budget_line_id:
                self.budget_line_id = program.budget_line_id
