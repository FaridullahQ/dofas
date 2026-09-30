from odoo import fields, models


class ArcsDonorReport(models.Model):
    _inherit = "arcs.donor.report"

    project_id = fields.Many2one(
        "arcs.project", string="Project", domain="[('grant_id', '=', grant_id)]",
        help="Optional: if this donor wants per-project reports under their "
             "overall agreement, link this report to the specific project it "
             "covers. Leave blank for a report covering the whole grant.")
