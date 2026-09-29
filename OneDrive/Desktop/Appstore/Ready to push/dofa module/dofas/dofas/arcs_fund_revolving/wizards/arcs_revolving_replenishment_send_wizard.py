from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsRevolvingReplenishmentSendWizard(models.TransientModel):
    """Compose and send the email asking a grant's donor to replenish a
    Revolving Fund cycle, once its utilization report has been approved.
    Mirrors arcs_fund's own send-wizard pattern: a pre-filled, editable
    composer that only records the decision to send when actually sent -
    it never sends silently on a state change."""

    _name = "arcs.revolving.replenishment.send.wizard"
    _description = "Send Revolving Fund Replenishment Request"

    cycle_id = fields.Many2one(
        "arcs.revolving.cycle", string="Revolving Fund Cycle", required=True,
        readonly=True, ondelete="cascade")

    donor_id = fields.Many2one(related="cycle_id.donor_id", readonly=True)
    grant_id = fields.Many2one(related="cycle_id.grant_id", readonly=True)
    currency_id = fields.Many2one(related="cycle_id.currency_id", readonly=True)
    amount_spent = fields.Monetary(related="cycle_id.amount_spent", readonly=True)
    replenishment_amount_requested = fields.Monetary(
        related="cycle_id.replenishment_amount_requested", readonly=True)

    email_to = fields.Char(string="Recipient Email", required=True)
    subject = fields.Char(required=True)
    body = fields.Html(required=True, sanitize_style=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="Attach the utilization report before sending (e.g. its "
             "printed PDF, or the receipts/photos already on it).")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        cycle_id = self.env.context.get("default_cycle_id") or self.env.context.get("active_id")
        cycle = self.env["arcs.revolving.cycle"].browse(cycle_id)
        if cycle.exists():
            donor = cycle.donor_id
            res.update({
                "cycle_id": cycle.id,
                "email_to": donor.email or "",
                "subject": self._default_subject(cycle),
                "body": self._default_body(cycle, donor),
            })
            report = cycle.donor_report_id
            if report:
                atts = self.env["ir.attachment"].search([
                    ("res_model", "=", "arcs.donor.report"), ("res_id", "=", report.id)])
                if atts:
                    res["attachment_ids"] = [(6, 0, atts.ids)]
        return res

    @api.model
    def _default_subject(self, cycle):
        return _("Request for Fund Replenishment - %(grant)s (%(ref)s)") % {
            "grant": cycle.grant_id.name or "", "ref": cycle.name}

    @api.model
    def _default_body(self, cycle, donor):
        user = self.env.user
        company = cycle.company_id.name or self.env.company.name
        amount = "{:,.2f} {}".format(
            cycle.replenishment_amount_requested or cycle.amount_spent or 0.0,
            cycle.currency_id.name or "")
        job = user.partner_id.function or ""
        return _(
            "<p>Dear %(donor)s,</p>"
            "<p>On behalf of %(company)s, we are pleased to report on the "
            "utilization of funds transferred under grant "
            "<strong>%(grant)s</strong>, Revolving Fund cycle "
            "<strong>%(ref)s</strong>.</p>"
            "<p>Please find attached the utilization report and supporting "
            "documentation. To continue the project without interruption, we "
            "kindly request replenishment of <strong>%(amount)s</strong> "
            "against this revolving fund arrangement.</p>"
            "<p>We remain available for any further information you may "
            "need.</p>"
            "<p>Warm regards,<br/>%(user)s%(job)s<br/>%(company)s</p>"
        ) % {
            "donor": donor.name or _("Valued Partner"), "company": company,
            "grant": cycle.grant_id.name or "", "ref": cycle.name, "amount": amount,
            "user": user.name, "job": ("<br/>%s" % job) if job else "",
        }

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
        self.cycle_id.message_post(
            body=_("Replenishment request email sent to %s.") % self.email_to,
            subject=self.subject, attachment_ids=self.attachment_ids.ids,
        )
        self.cycle_id.write({
            "email_sent": True, "email_sent_date": fields.Datetime.now(),
        })
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        return {"type": "ir.actions.act_window_close"}

    def action_stay(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "view_mode": "form", "target": "new",
        }
