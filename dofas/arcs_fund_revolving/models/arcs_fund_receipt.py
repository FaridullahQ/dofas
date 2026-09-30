from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsFundReceipt(models.Model):
    _inherit = "arcs.fund.receipt"

    revolving_cycle_id = fields.Many2one(
        "arcs.revolving.cycle", string="Revolving Fund Cycle", copy=False, tracking=True,
        domain="[('grant_id', '=', grant_id), ('state', '=', 'committed')]",
        help="If this receipt funds a Revolving Fund cycle, link it here so "
             "the cycle moves to Funded/Utilizing automatically on posting.")
    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_post(self):
        for r in self.filtered("revolving_cycle_id"):
            if r.revolving_cycle_id.state != "committed":
                raise UserError(_(
                    "Revolving Fund Cycle '%(c)s' is not awaiting funds "
                    "(state: %(s)s).",
                    c=r.revolving_cycle_id.name, s=r.revolving_cycle_id.state))
        res = super().action_post()
        for r in self.filtered("revolving_cycle_id"):
            cycle = r.revolving_cycle_id
            cycle.write({"fund_receipt_id": r.id})
            cycle._transition("funded", "fund_received")
            cycle._transition("utilizing", "start_utilization")
        return res

    def action_reset(self):
        for r in self.filtered("revolving_cycle_id"):
            if r.revolving_cycle_id.amount_spent:
                raise UserError(_(
                    "Cannot reset receipt '%(r)s' to draft: its Revolving "
                    "Fund Cycle already has spending recorded against it.",
                    r=r.name))
        res = super().action_reset()
        for r in self.filtered("revolving_cycle_id"):
            cycle = r.revolving_cycle_id
            if cycle.state in ("funded", "utilizing"):
                cycle.write({"fund_receipt_id": False})
                cycle._transition("committed", "fund_reset")
        return res
