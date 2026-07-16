from odoo import _, fields, models


class McitDonorFundingRequest(models.Model):
    """Link a donor supplementary funding request back to the acquisition it
    is covering. Kept in mcit_request so mcit.donor.funding.request stays a
    reusable primitive in mcit_fund with no knowledge of the acquisition
    workflow. Deliberately does NOT auto-resume the acquisition or touch the
    budget on donor approval - Finance must still action the actual budget
    increase (edit the line or raise an mcit.budget.transfer), keeping
    financial control changes explicit and reviewable."""

    _inherit = "mcit.donor.funding.request"

    spend_request_id = fields.Many2one(
        "mcit.spend.request", string="Related Acquisition", copy=False)

    def action_donor_approve(self):
        res = super().action_donor_approve()
        if self.spend_request_id:
            self.spend_request_id.message_post(body=_(
                "Donor approved supplementary funding request %(ref)s (%(amount).2f %(cur)s). "
                "Finance still needs to increase the budget line or raise an internal transfer "
                "before retrying Commit.") % {
                "ref": self.name, "amount": self.amount_requested,
                "cur": self.currency_id.name or ""})
        return res

    def action_donor_reject(self):
        res = super().action_donor_reject()
        if self.spend_request_id:
            self.spend_request_id.message_post(body=_(
                "Donor rejected supplementary funding request %s.") % self.name)
        return res
