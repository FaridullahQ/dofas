from odoo import _, fields, models
from odoo.exceptions import UserError


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    reimbursement_claim_ids = fields.One2many(
        "arcs.reimbursement.claim", "grant_id", string="Reimbursement Claims")
    reimbursement_claim_count = fields.Integer(compute="_compute_reimbursement_counts")
    reimbursement_claimed_total = fields.Monetary(
        compute="_compute_reimbursement_counts", currency_field="currency_id")

    def _compute_reimbursement_counts(self):
        for g in self:
            claims = g.reimbursement_claim_ids.filtered(lambda c: c.state != "cancelled")
            g.reimbursement_claim_count = len(g.reimbursement_claim_ids)
            g.reimbursement_claimed_total = sum(claims.mapped("claimed_amount"))

    def action_view_reimbursement_claims(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reimbursement Claims"),
            "res_model": "arcs.reimbursement.claim",
            "view_mode": "tree,form",
            "domain": [("grant_id", "=", self.id)],
            "context": {"default_grant_id": self.id},
        }

    # --------------------------------------------------- funding-model hook
    def _funding_model_check_closure_allowed(self):
        self.ensure_one()
        if self.funding_model != "reimbursement":
            return super()._funding_model_check_closure_allowed()
        open_claims = self.reimbursement_claim_ids.filtered(
            lambda c: c.state not in ("reported", "cancelled"))
        if open_claims:
            raise UserError(_(
                "Cannot close grant '%(g)s': Reimbursement Claim '%(c)s' is still "
                "open (state: %(s)s). Get it funded and reported, or cancel it, "
                "first.",
                g=self.display_name, c=open_claims[0].name, s=dict(
                    open_claims[0]._fields["state"].selection).get(
                    open_claims[0].state, open_claims[0].state)))
        return super()._funding_model_check_closure_allowed()
