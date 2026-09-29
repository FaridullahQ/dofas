from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ArcsMultiDonorProjectMember(models.Model):
    """One participating grant within a Multi-Donor Project, with that
    donor's agreed percentage share of shared costs. Editable only while
    the project is Draft."""

    _name = "arcs.multi.donor.project.member"
    _description = "Multi-Donor Project Member"
    _order = "project_id, allocation_pct desc"

    project_id = fields.Many2one(
        "arcs.multi.donor.project", required=True, ondelete="cascade", index=True)
    project_state = fields.Selection(related="project_id.state", string="Project Status")
    grant_id = fields.Many2one(
        "arcs.grant", required=True, ondelete="restrict",
        domain="[('funding_model', '=', 'multi_donor'), ('state', 'in', ('approved', 'active'))]")
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", readonly=True)
    allocation_pct = fields.Float(
        string="Share (%)", required=True, digits=(5, 2),
        help="This donor's agreed percentage share of shared costs on this project.")

    _sql_constraints = [
        ("project_grant_uniq", "unique(project_id, grant_id)",
         "This grant is already a member of this project."),
        ("allocation_pct_range", "CHECK(allocation_pct > 0 AND allocation_pct <= 100)",
         "The share must be greater than 0% and no more than 100%."),
    ]

    @api.constrains("grant_id", "project_id")
    def _check_grant_not_in_another_open_project(self):
        for m in self:
            other = self.search([
                ("grant_id", "=", m.grant_id.id), ("id", "!=", m.id),
                ("project_id", "!=", m.project_id.id),
                ("project_id.state", "!=", "closed"),
            ])
            if other:
                raise ValidationError(_(
                    "Grant '%(g)s' is already a member of another open Multi-Donor "
                    "Project ('%(p)s'). A grant can only belong to one open "
                    "project's shared-cost split at a time.",
                    g=m.grant_id.display_name, p=other[0].project_id.name))

    def write(self, vals):
        for m in self:
            if m.project_id.state != "draft" and "allocation_pct" in vals:
                raise UserError(_(
                    "'%s' is not Draft - reopen the project first (Reset to Draft) "
                    "before changing member shares.") % m.project_id.name)
        return super().write(vals)

    def unlink(self):
        for m in self:
            if m.project_id.state != "draft":
                raise UserError(_(
                    "'%s' is not Draft - reopen the project first before removing "
                    "a member.") % m.project_id.name)
        return super().unlink()
