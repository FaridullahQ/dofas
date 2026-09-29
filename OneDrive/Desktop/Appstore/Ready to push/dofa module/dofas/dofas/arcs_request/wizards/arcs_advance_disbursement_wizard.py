from odoo import _, models


class ArcsAdvanceDisbursementWizard(models.TransientModel):
    """When the disbursed advance is linked to an acquisition, also post a
    note there - so the disbursement is visible on the record a Program
    Officer actually watches, not only on the advance itself - without
    arcs_advance (which knows nothing about acquisitions) having to change."""

    _inherit = "arcs.advance.disbursement.wizard"

    def action_confirm(self):
        result = super().action_confirm()
        spend_request = self.advance_id.spend_request_id
        if spend_request:
            spend_request.message_post(body=_(
                "Employee advance %(ref)s disbursed to %(employee)s for %(amount).2f "
                "%(cur)s via %(journal)s."
            ) % {
                "ref": self.advance_id.name,
                "employee": spend_request.requested_by.name,
                "amount": self.amount, "cur": self.currency_id.name or "",
                "journal": self.journal_id.name,
            })
        return result
