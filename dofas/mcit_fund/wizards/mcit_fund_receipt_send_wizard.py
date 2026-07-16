import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class McitFundReceiptSendWizard(models.TransientModel):
    """Compose and send the donor acknowledgement email for a posted fund
    receipt. Pre-filled with a greeting to the donor and a closing signed by
    the current user; everything stays editable. At least one attachment
    (defaults to the Thank-You letter) is required before sending."""

    _name = "mcit.fund.receipt.send.wizard"
    _description = "Send Donor Acknowledgement Email"

    fund_receipt_id = fields.Many2one(
        "mcit.fund.receipt", string="Fund Receipt", required=True, readonly=True,
        ondelete="cascade")

    # ---- sidebar context (read-only, for the composer's reference) --------
    donor_id = fields.Many2one(related="fund_receipt_id.donor_id", readonly=True)
    grant_id = fields.Many2one(related="fund_receipt_id.grant_id", readonly=True)
    amount = fields.Monetary(related="fund_receipt_id.amount", readonly=True)
    currency_id = fields.Many2one(related="fund_receipt_id.currency_id", readonly=True)
    bank_voucher_ref = fields.Char(related="fund_receipt_id.bank_voucher_ref", readonly=True)
    received_date = fields.Date(related="fund_receipt_id.received_date", readonly=True)

    # ---- composer -----------------------------------------------------------
    email_to = fields.Char(string="Recipient Email", required=True,
                           help="Editable recipient address. Defaults to the donor's email.")
    subject = fields.Char(required=True)
    body = fields.Html(required=True, sanitize_style=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="At least one attachment is required. Defaults to the generated "
             "Thank-You letter; you may add or remove files.")

    # ============================================================== defaults
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        receipt_id = self.env.context.get("default_fund_receipt_id") or self.env.context.get("active_id")
        receipt = self.env["mcit.fund.receipt"].browse(receipt_id)
        if receipt.exists():
            donor = receipt.donor_id
            res.update({
                "fund_receipt_id": receipt.id,
                "email_to": donor.email or "",
                "subject": self._default_subject(receipt),
                "body": self._default_body(receipt, donor),
            })
            attachment = receipt._get_or_create_thanks_attachment()
            if attachment:
                res["attachment_ids"] = [(6, 0, attachment.ids)]
        return res

    @api.model
    def _default_subject(self, receipt):
        return _("Acknowledgement of Funds Received - %s") % receipt.name

    @api.model
    def _default_body(self, receipt, donor):
        user = self.env.user
        company = receipt.company_id.name or self.env.company.name
        amount = "{:,.2f} {}".format(receipt.amount or 0.0, receipt.currency_id.name or "")
        job = user.partner_id.function or ""
        return _(
            "<p>Dear %(donor)s,</p>"
            "<p>On behalf of %(company)s, we gratefully acknowledge receipt of your "
            "contribution of <strong>%(amount)s</strong> under grant "
            "<strong>%(grant)s</strong> (Receipt No. %(receipt)s, dated %(date)s).</p>"
            "<p>Please find our official acknowledgement letter attached for your records. "
            "Your continued partnership enables us to deliver vital assistance to the "
            "communities we serve.</p>"
            "<p>Warm regards,<br/>"
            "%(user)s%(job)s<br/>"
            "%(company)s</p>"
        ) % {
            "donor": donor.name or _("Valued Partner"),
            "company": company,
            "amount": amount,
            "grant": receipt.grant_id.name or "",
            "receipt": receipt.name,
            "date": receipt.received_date or "",
            "user": user.name,
            "job": ("<br/>%s" % job) if job else "",
        }

    # ================================================================ actions
    def action_send(self):
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(_(
                "Attach at least one document before sending (e.g. the "
                "Thank-You letter)."))
        if not self.email_to or not self.email_to.strip():
            raise UserError(_("Enter the recipient's email address before sending."))
        if not self.subject or not self.subject.strip():
            raise UserError(_("Enter a subject before sending."))
        mail = self.env["mail.mail"].sudo().create({
            "subject": self.subject,
            "body_html": self.body,
            "email_to": self.email_to,
            "email_from": self.env.user.partner_id.email_formatted
                          or self.env.user.email or self.env.company.email or False,
            "attachment_ids": [(6, 0, self.attachment_ids.ids)],
            "auto_delete": False,
        })
        mail.send()
        self.fund_receipt_id.message_post(
            body=_("Acknowledgement email sent to %s.") % self.email_to,
            subject=self.subject,
            attachment_ids=self.attachment_ids.ids,
        )
        self.fund_receipt_id.write({
            "thanks_email_sent": True,
            "thanks_email_date": fields.Datetime.now(),
        })
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        return {"type": "ir.actions.act_window_close"}

    def action_stay(self):
        """Keep the composer open with everything as entered so far."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
