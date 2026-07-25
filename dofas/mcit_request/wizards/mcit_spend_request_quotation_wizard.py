from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class McitSpendRequestQuotationWizard(models.TransientModel):
    """Confirm the real price of a submitted acquisition against approved
    supplier quotations, line by line. The resulting total becomes the
    acquisition's approved_amount, which is what gets reserved on the budget
    line (and later posted to the journal) instead of the rough estimate."""

    _name = "mcit.spend.request.quotation.wizard"
    _description = "Confirm Real Price from Quotations"

    request_id = fields.Many2one(
        "mcit.spend.request", string="Acquisition", required=True, readonly=True,
        ondelete="cascade")
    currency_id = fields.Many2one(related="request_id.currency_id", readonly=True)
    estimated_amount = fields.Monetary(related="request_id.estimated_amount", readonly=True)
    vendor_id = fields.Many2one(
        "res.partner", string="Vendor",
        help="Vendor whose quotation this real price is based on. Required before confirming.")
    line_ids = fields.One2many(
        "mcit.spend.request.quotation.line", "wizard_id", string="Quoted Items")
    total_amount = fields.Monetary(
        string="Approved (Quoted) Amount", compute="_compute_total_amount",
        store=True, currency_field="currency_id")
    variance_amount = fields.Monetary(
        string="Variance vs. Estimate", compute="_compute_total_amount",
        store=True, currency_field="currency_id",
        help="Positive means the quoted price is higher than the original estimate; "
             "negative means it came in under budget.")
    quotation_ref = fields.Char(
        string="Quotation Reference",
        help="Reference number of the approved supplier quotation(s). "
             "Required before confirming.")
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Approved Quotations",
        help="At least one approved quotation document is required before confirming.")
    note = fields.Text(string="Notes")

    @api.depends("line_ids.quoted_amount", "estimated_amount")
    def _compute_total_amount(self):
        for w in self:
            w.total_amount = sum(w.line_ids.mapped("quoted_amount"))
            w.variance_amount = w.total_amount - w.estimated_amount

    # ============================================================== defaults
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_request_id") or self.env.context.get("active_id")
        request = self.env["mcit.spend.request"].browse(request_id)
        if request.exists():
            res["request_id"] = request.id
            res["line_ids"] = [(0, 0, {
                "request_line_id": line.id,
                "quoted_unit_price": line.unit_estimate,
            }) for line in request.line_ids]
        return res

    # ================================================================ actions
    def action_confirm(self):
        self.ensure_one()
        if not self.vendor_id:
            raise UserError(_("Select the vendor this quotation is from before confirming."))
        if not self.attachment_ids:
            raise UserError(_(
                "Attach at least one approved quotation document before confirming."))
        if not self.quotation_ref or not self.quotation_ref.strip():
            raise UserError(_("Enter the quotation reference number before confirming."))
        if float_compare(self.total_amount, 0.0,
                         precision_rounding=self.currency_id.rounding or 0.01) <= 0:
            raise UserError(_("Enter a quoted unit price for at least one item."))
        # Re-parent the attachments onto the acquisition so they show in its chatter.
        self.attachment_ids.write({
            "res_model": "mcit.spend.request", "res_id": self.request_id.id,
        })
        self.request_id.write({
            "approved_amount": self.total_amount,
            "quotation_ref": self.quotation_ref,
            "vendor_id": self.vendor_id.id,
        })
        self.request_id.message_post(body=_(
            "Real price confirmed from quotation %(ref)s (vendor: %(vendor)s): "
            "%(amount).2f %(currency)s (estimated was %(est).2f %(currency)s).") % {
            "ref": self.quotation_ref, "vendor": self.vendor_id.name,
            "amount": self.total_amount,
            "currency": self.currency_id.name or "", "est": self.estimated_amount})
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        self.unlink()
        return {"type": "ir.actions.act_window_close"}

    def action_stay(self):
        """Keep the wizard open with everything entered so far, without
        confirming yet - lets the user pause partway through."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class McitSpendRequestQuotationLine(models.TransientModel):
    _name = "mcit.spend.request.quotation.line"
    _description = "Quoted Item"

    wizard_id = fields.Many2one(
        "mcit.spend.request.quotation.wizard", required=True, ondelete="cascade")
    request_line_id = fields.Many2one(
        "mcit.spend.request.line", string="Item", required=True, readonly=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    name = fields.Char(related="request_line_id.name", string="Item", readonly=True)
    quantity = fields.Float(related="request_line_id.quantity", readonly=True)
    unit_estimate = fields.Monetary(
        related="request_line_id.unit_estimate", string="Est. Unit",
        currency_field="currency_id", readonly=True)
    quoted_unit_price = fields.Monetary(
        string="Quoted Unit", currency_field="currency_id", required=True)
    quoted_amount = fields.Monetary(
        string="Quoted Total", compute="_compute_quoted_amount", store=True,
        currency_field="currency_id")

    @api.depends("quantity", "quoted_unit_price")
    def _compute_quoted_amount(self):
        for l in self:
            l.quoted_amount = (l.quantity or 0.0) * (l.quoted_unit_price or 0.0)

    @api.constrains("quoted_unit_price")
    def _check_quoted_unit_price(self):
        for l in self:
            if l.quoted_unit_price < 0:
                raise ValidationError(_("The quoted unit price cannot be negative."))
