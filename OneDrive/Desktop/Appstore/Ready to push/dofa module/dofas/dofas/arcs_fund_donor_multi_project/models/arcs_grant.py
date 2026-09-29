from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    dmp_project_ids = fields.Many2many(
        "arcs.project", compute="_compute_dmp_projects", string="Projects")
    dmp_project_count = fields.Integer(compute="_compute_dmp_projects")
    dmp_planned_total = fields.Monetary(
        compute="_compute_dmp_projects", currency_field="currency_id",
        string="Total Planned Across Projects")

    def _compute_dmp_projects(self):
        Project = self.env["arcs.project"]
        for g in self:
            projects = Project.search([("grant_id", "=", g.id)])
            g.dmp_project_ids = projects
            g.dmp_project_count = len(projects)
            g.dmp_planned_total = sum(projects.mapped("planned_cost"))

    def action_view_dmp_projects(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Projects"),
            "res_model": "arcs.project", "view_mode": "tree,form",
            "domain": [("grant_id", "=", self.id)],
            "context": {"default_grant_id": self.id},
        }

    # --------------------------------------------------- funding-model hooks
    def _funding_model_check_expense_availability(self, expense):
        self.ensure_one()
        if self.funding_model != "donor_multi_project":
            return super()._funding_model_check_expense_availability(expense)
        project = expense.project_id
        if not project:
            raise UserError(_(
                "This grant uses the One Donor, Multiple Projects model: every "
                "expense must specify which Project it belongs to before it can "
                "be approved."))
        if project.grant_id != self:
            raise UserError(_(
                "Project '%(p)s' belongs to a different grant than this expense "
                "('%(g)s'). Pick a project under this grant.",
                p=project.display_name, g=self.display_name))
        available = project.get_available_locked()
        if float_compare(expense.amount, available,
                         precision_rounding=self.currency_id.rounding) > 0:
            raise UserError(_(
                "Insufficient funds on Project '%(p)s'. Available: %(av).2f "
                "%(cur)s - requested: %(r).2f %(cur)s. On a One Donor, Multiple "
                "Projects grant, spending against a project can never exceed "
                "that project's own Planned Cost, regardless of what the wider "
                "budget line still has left.",
                p=project.display_name, av=available, r=expense.amount,
                cur=self.currency_id.name))
        return True

    def _funding_model_check_closure_allowed(self):
        self.ensure_one()
        if self.funding_model != "donor_multi_project":
            return super()._funding_model_check_closure_allowed()
        open_projects = self.dmp_project_ids.filtered(lambda p: p.state != "closed")
        if open_projects:
            raise UserError(_(
                "Cannot close grant '%(g)s': Project '%(p)s' is not Closed yet "
                "(closing a project also requires all of its own activities to "
                "be Closed first).",
                g=self.display_name, p=open_projects[0].name))
        return super()._funding_model_check_closure_allowed()
