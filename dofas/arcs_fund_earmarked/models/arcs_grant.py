from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    earmarked_project_ids = fields.Many2many(
        "arcs.project", compute="_compute_earmarked_projects", string="Projects")
    earmarked_project_count = fields.Integer(compute="_compute_earmarked_projects")
    earmarked_activity_count = fields.Integer(compute="_compute_earmarked_projects")

    def _compute_earmarked_projects(self):
        Project = self.env["arcs.project"]
        for g in self:
            projects = Project.search([("grant_id", "=", g.id)])
            g.earmarked_project_ids = projects
            g.earmarked_project_count = len(projects)
            g.earmarked_activity_count = sum(len(p.activity_ids) for p in projects)

    def action_view_earmarked_projects(self):
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
        if self.funding_model != "earmarked":
            return super()._funding_model_check_expense_availability(expense)
        activity = expense.activity_id
        if not activity:
            raise UserError(_(
                "This grant uses the Earmarked model: every expense must specify "
                "which Activity it belongs to before it can be approved - the "
                "donor's funds are restricted to that named activity."))
        if activity.project_id.grant_id != self:
            raise UserError(_(
                "Activity '%(a)s' belongs to a different grant than this expense "
                "('%(g)s'). Pick an activity under one of this grant's own projects.",
                a=activity.display_name, g=self.display_name))
        available = activity.get_available_locked()
        if float_compare(expense.amount, available,
                         precision_rounding=self.currency_id.rounding) > 0:
            raise UserError(_(
                "Insufficient funds on Activity '%(a)s'. Available: %(av).2f "
                "%(cur)s - requested: %(r).2f %(cur)s. On an Earmarked grant, "
                "spending can never exceed what the donor allocated to this "
                "specific activity, regardless of what the wider budget line "
                "or project still has left.",
                a=activity.display_name, av=available, r=expense.amount,
                cur=self.currency_id.name))
        return True

    def _funding_model_check_closure_allowed(self):
        self.ensure_one()
        if self.funding_model != "earmarked":
            return super()._funding_model_check_closure_allowed()
        open_projects = self.earmarked_project_ids.filtered(lambda p: p.state != "closed")
        if open_projects:
            raise UserError(_(
                "Cannot close grant '%(g)s': Project '%(p)s' is not Closed yet "
                "(closing a project also requires all of its own activities to "
                "be Closed first).",
                g=self.display_name, p=open_projects[0].name))
        return super()._funding_model_check_closure_allowed()
