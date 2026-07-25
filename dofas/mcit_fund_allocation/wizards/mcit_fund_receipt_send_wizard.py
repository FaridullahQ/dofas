from odoo import api, models

# Anchor already present, verbatim, in mcit_fund's default body template.
# Splicing here (instead of adding a hook method upstream in mcit_fund) keeps
# mcit_fund untouched, per the "extend from the consuming module" principle.
_REGARDS_ANCHOR = "<p>Warm regards,<br/>"


class McitFundReceiptSendWizard(models.TransientModel):
    _inherit = "mcit.fund.receipt.send.wizard"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        receipt = self.env["mcit.fund.receipt"].browse(res.get("fund_receipt_id"))
        body = res.get("body")
        if receipt.exists() and body and _REGARDS_ANCHOR in body:
            allocation_html = receipt._allocation_email_html()
            if allocation_html:
                res["body"] = body.replace(
                    _REGARDS_ANCHOR, allocation_html + _REGARDS_ANCHOR, 1)
        return res
