from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsDonorFundingRequestSendWizard(models.TransientModel):
    """Compose and send the email asking the grant's donor for supplementary
    funding. Pre-filled with all the request's details (grant, amount,
    reason) so nothing has to be re-typed; everything stays editable before
    sending. Unlike arcs.fund.receipt's acknowledgement email, an attachment
    here is optional (e.g. a quotation or shortfall note) rather than
    mandatory - the email body itself IS the formal ask, there is no
    generated certificate that has to be attached for it to be complete."""

    _name = "arcs.donor.funding.request.send.wizard"
    _description = "Send Donor Funding Request Email"

    funding_request_id = fields.Many2one(
        "arcs.donor.funding.request", string="Funding Request", required=True,
        readonly=True, ondelete="cascade")

    # ---- sidebar context (read-only, for the composer's reference) --------
    donor_id = fields.Many2one(related="funding_request_id.donor_id", readonly=True)
    grant_id = fields.Many2one(related="funding_request_id.grant_id", readonly=True)
    amount_requested = fields.Monetary(related="funding_request_id.amount_requested", readonly=True)
    currency_id = fields.Many2one(related="funding_request_id.currency_id", readonly=True)
    reason = fields.Text(related="funding_request_id.reason", readonly=True)

    # ---- composer -----------------------------------------------------------
    email_to = fields.Char(string="Recipient Email", required=True,
                           help="Editable recipient address. Defaults to the donor's email.")
    subject = fields.Char(required=True)
    body = fields.Html(required=True, sanitize_style=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="Optional supporting documents (e.g. a quotation or shortfall justification).")

    # ============================================================== defaults
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_funding_request_id") or self.env.context.get("active_id")
        request = self.env["arcs.donor.funding.request"].browse(request_id)
        if request.exists():
            donor = request.donor_id
            res.update({
                "funding_request_id": request.id,
                "email_to": donor.email or "",
                "subject": self._default_subject(request),
                "body": self._default_body(request, donor),
            })
        return res

    @api.model
    def _default_subject(self, request):
        return _("Request for Supplementary Funding - %(grant)s (%(ref)s)") % {
            "grant": request.grant_id.name or "", "ref": request.name}

    @api.model
    def _extra_body_html(self, request):
        """Extension point: downstream modules (e.g. arcs_request, when this
        request exists to cover a budget shortfall on an acquisition) add
        extra context here without needing to touch this method or
        duplicate the whole template - see arcs_request's override."""
        return ""

    @api.model
    def _default_body(self, request, donor):
        user = self.env.user
        company = request.company_id.name or self.env.company.name
        amount = "{:,.2f} {}".format(request.amount_requested or 0.0, request.currency_id.name or "")
        job = user.partner_id.function or ""
        return _(
            "<p>Dear %(donor)s,</p>"
            "<p>On behalf of %(company)s, we would like to request supplementary funding "
            "of <strong>%(amount)s</strong> under grant <strong>%(grant)s</strong> "
            "(Reference %(ref)s).</p>"
            "<p><strong>Reason:</strong> %(reason)s</p>"
            "%(extra)s"
            "<p>We would be grateful for your consideration and remain available for any "
            "further information you may need.</p>"
            "<p>Warm regards,<br/>"
            "%(user)s%(job)s<br/>"
            "%(company)s</p>"
        ) % {
            "donor": donor.name or _("Valued Partner"),
            "company": company,
            "amount": amount,
            "grant": request.grant_id.name or "",
            "ref": request.name,
            "reason": request.reason or "",
            "extra": self._extra_body_html(request),
            "user": user.name,
            "job": ("<br/>%s" % job) if job else "",
        }

    # ================================================================ actions
    def action_send(self):
        self.ensure_one()
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
        self.funding_request_id.message_post(
            body=_("Funding request email sent to %s.") % self.email_to,
            subject=self.subject,
            attachment_ids=self.attachment_ids.ids,
        )
        self.funding_request_id.write({
            "email_sent": True,
            "email_sent_date": fields.Datetime.now(),
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
