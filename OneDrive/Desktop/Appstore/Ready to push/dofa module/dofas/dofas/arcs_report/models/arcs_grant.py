from odoo import fields, models


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    donor_report_ids = fields.One2many(
        "arcs.donor.report", "grant_id", string="Donor Reports")
    department_report_ids = fields.One2many(
        "arcs.department.report", "grant_id", string="Department Reports")
    donor_report_count = fields.Integer(compute="_compute_report_counts")
    department_report_count = fields.Integer(compute="_compute_report_counts")

    def _compute_report_counts(self):
        for g in self:
            g.donor_report_count = len(g.donor_report_ids)
            g.department_report_count = len(g.department_report_ids)
