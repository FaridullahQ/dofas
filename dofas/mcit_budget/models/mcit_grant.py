from odoo import api, fields, models


class McitGrant(models.Model):
    _inherit = "mcit.grant"

    budget_ids = fields.One2many("mcit.budget", "grant_id", string="Budget Versions")
    active_budget_id = fields.Many2one("mcit.budget", string="Active Budget",
                                       compute="_compute_active_budget", store=True)

    @api.depends("budget_ids.state", "budget_ids.version")
    def _compute_active_budget(self):
        for grant in self:
            grant.active_budget_id = grant.budget_ids.filtered(
                lambda b: b.state == "approved").sorted("version", reverse=True)[:1]
