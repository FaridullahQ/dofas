from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsFundReceipt(models.Model):
    _inherit = "arcs.fund.receipt"

    reimbursement_claim_id = fields.Many2one(
        "arcs.reimbursement.claim", string="Reimbursement Claim", copy=False, tracking=True,
        domain="[('grant_id', '=', grant_id), ('state', '=', 'approved')]",
        help="If this receipt is the donor's reimbursement for an approved "
             "claim, link it here so the claim moves to Funds Credited on posting.")
    grant_funding_model = fields.Selection(
        related="grant_id.funding_model", string="Funding Model", readonly=True)

    def action_post(self):
        for r in self.filtered("reimbursement_claim_id"):
            if r.reimbursement_claim_id.state != "approved":
                raise UserError(_(
                    "Reimbursement Claim '%(c)s' is not awaiting funds (state: %(s)s).",
                    c=r.reimbursement_claim_id.name, s=r.reimbursement_claim_id.state))
        res = super().action_post()
        for r in self.filtered("reimbursement_claim_id"):
            claim = r.reimbursement_claim_id
            claim.write({"fund_receipt_id": r.id})
            claim._transition("funded", "fund_received")
        return res

    def action_reset(self):
        for r in self.filtered("reimbursement_claim_id"):
            if r.reimbursement_claim_id.state == "reported":
                raise UserError(_(
                    "Cannot reset receipt '%(r)s' to draft: its Reimbursement "
                    "Claim has already been reported.", r=r.name))
        res = super().action_reset()
        for r in self.filtered("reimbursement_claim_id"):
            claim = r.reimbursement_claim_id
            if claim.state == "funded":
                claim.write({"fund_receipt_id": False})
                claim._transition("approved", "fund_reset")
        return res
