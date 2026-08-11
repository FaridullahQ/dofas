from odoo import api, models

# Anchor already present, verbatim, in arcs_fund's default body template.
# Splicing here (instead of adding a hook method upstream in arcs_fund) keeps
# arcs_fund untouched, per the "extend from the consuming module" principle.
_REGARDS_ANCHOR = "<p>Warm regards,<br/>"


class ArcsFundReceiptSendWizard(models.TransientModel):
    _inherit = "arcs.fund.receipt.send.wizard"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        receipt = self.env["arcs.fund.receipt"].browse(res.get("fund_receipt_id"))
        body = res.get("body")
        if receipt.exists() and body and _REGARDS_ANCHOR in body:
            allocation_html = receipt._allocation_email_html()
            if allocation_html:
                res["body"] = body.replace(
                    _REGARDS_ANCHOR, allocation_html + _REGARDS_ANCHOR, 1)
        return res
