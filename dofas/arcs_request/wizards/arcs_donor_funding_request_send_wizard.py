from odoo import _, api, models


class ArcsDonorFundingRequestSendWizard(models.TransientModel):
    """When this funding request exists to cover a budget shortfall on an
    acquisition, add that context to the email so the donor sees exactly
    what the supplementary funding is for - without arcs_fund (which knows
    nothing about acquisitions) having to change."""

    _inherit = "arcs.donor.funding.request.send.wizard"

    @api.model
    def _extra_body_html(self, request):
        extra = super()._extra_body_html(request)
        spend_request = request.spend_request_id
        if not spend_request:
            return extra
        shortfall = "{:,.2f} {}".format(
            spend_request.shortfall_amount or 0.0, spend_request.currency_id.name or "")
        acquisition_note = _(
            "<p>This request relates to acquisition <strong>%(ref)s</strong>, currently "
            "short of budget by <strong>%(shortfall)s</strong> on the '%(line)s' budget "
            "line.</p>"
        ) % {
            "ref": spend_request.name,
            "shortfall": shortfall,
            "line": spend_request.budget_line_id.name or "",
        }
        return extra + acquisition_note
