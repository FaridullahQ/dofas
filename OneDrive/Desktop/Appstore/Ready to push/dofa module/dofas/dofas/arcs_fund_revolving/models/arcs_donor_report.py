from odoo import fields, models


class ArcsDonorReport(models.Model):
    _inherit = "arcs.donor.report"

    revolving_cycle_id = fields.Many2one(
        "arcs.revolving.cycle", string="Revolving Fund Cycle", copy=False, tracking=True,
        domain="[('grant_id', '=', grant_id), ('state', 'in', ('utilizing', 'reporting'))]")
    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_submit(self):
        res = super().action_submit()
        for r in self.filtered("revolving_cycle_id"):
            cycle = r.revolving_cycle_id
            if not cycle.donor_report_id:
                cycle.write({"donor_report_id": r.id})
            if cycle.state == "utilizing":
                cycle._transition("reporting", "report_submitted")
        return res

    def action_approve(self):
        res = super().action_approve()
        for r in self.filtered("revolving_cycle_id"):
            cycle = r.revolving_cycle_id
            if not cycle.replenishment_amount_requested:
                cycle.replenishment_amount_requested = cycle.amount_spent
        return res
