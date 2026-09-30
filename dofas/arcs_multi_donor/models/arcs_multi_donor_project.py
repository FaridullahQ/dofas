from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class ArcsMultiDonorProject(models.Model):
    """Links several donors' grants together as co-funders of one shared
    project. This model does NOT replace or merge those grants - each keeps
    its own agreement, budget, expenses, reports, and closure. It exists
    solely to hold the agreed percentage split so shared costs can be
    divided across members safely (see arcs.multi.donor.shared.cost)."""

    _name = "arcs.multi.donor.project"
    _description = "Multi-Donor Project"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    description = fields.Text()
    member_ids = fields.One2many(
        "arcs.multi.donor.project.member", "project_id", string="Member Grants")
    shared_cost_ids = fields.One2many(
        "arcs.multi.donor.shared.cost", "project_id", string="Shared Costs")
    member_count = fields.Integer(compute="_compute_counts")
    shared_cost_count = fields.Integer(compute="_compute_counts")
    total_allocation_pct = fields.Float(compute="_compute_counts", string="Total Allocated (%)")

    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft", required=True, tracking=True, copy=False)

    @api.depends("member_ids.allocation_pct", "shared_cost_ids")
    def _compute_counts(self):
        for proj in self:
            proj.member_count = len(proj.member_ids)
            proj.shared_cost_count = len(proj.shared_cost_ids)
            proj.total_allocation_pct = sum(proj.member_ids.mapped("allocation_pct"))

    def action_activate(self):
        for proj in self:
            if proj.state != "draft":
                raise UserError(_("Only a draft project can be activated."))
            if len(proj.member_ids) < 2:
                raise UserError(_(
                    "A Multi-Donor Project needs at least two member grants - "
                    "add them under Member Grants first."))
            if float_compare(proj.total_allocation_pct, 100.0, precision_digits=2) != 0:
                raise UserError(_(
                    "The member percentages must add up to exactly 100%% "
                    "(currently %.2f%%).") % proj.total_allocation_pct)
        return self.write({"state": "active"})

    def action_close(self):
        for proj in self:
            if proj.state != "active":
                raise UserError(_("Only an active project can be closed."))
        return self.write({"state": "closed"})

    def action_reset_draft(self):
        for proj in self:
            if proj.shared_cost_ids:
                raise UserError(_(
                    "Cannot reopen '%s' for editing: it already has shared costs "
                    "recorded against its member percentages. Reopening now would "
                    "let the split key silently drift from what those costs were "
                    "actually divided by.") % proj.name)
        return self.write({"state": "draft"})

    def action_view_shared_costs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Shared Costs"),
            "res_model": "arcs.multi.donor.shared.cost", "view_mode": "tree,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }
