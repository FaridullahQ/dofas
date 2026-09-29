from odoo import fields, models


class ArcsDonorReport(models.Model):
    _inherit = "arcs.donor.report"

    reimbursement_claim_id = fields.Many2one(
        "arcs.reimbursement.claim", string="Reimbursement Claim", copy=False, tracking=True,
        domain="[('grant_id', '=', grant_id), ('state', '=', 'funded')]")

    def action_approve(self):
        res = super().action_approve()
        for r in self.filtered("reimbursement_claim_id"):
            claim = r.reimbursement_claim_id
            if not claim.donor_report_id:
                claim.write({"donor_report_id": r.id})
            if claim.state == "funded":
                claim._transition("reported", "report_approved")
        return res
