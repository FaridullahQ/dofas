from odoo import _, fields, models


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    multi_donor_member_id = fields.Many2one(
        "arcs.multi.donor.project.member", compute="_compute_multi_donor_member",
        string="Multi-Donor Membership")
    multi_donor_project_id = fields.Many2one(
        "arcs.multi.donor.project", compute="_compute_multi_donor_member",
        string="Multi-Donor Project")

    def _compute_multi_donor_member(self):
        Member = self.env["arcs.multi.donor.project.member"]
        for g in self:
            member = Member.search([("grant_id", "=", g.id)], limit=1)
            g.multi_donor_member_id = member
            g.multi_donor_project_id = member.project_id

    def action_view_multi_donor_project(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "arcs.multi.donor.project",
            "res_id": self.multi_donor_project_id.id, "view_mode": "form", "target": "current",
        }
