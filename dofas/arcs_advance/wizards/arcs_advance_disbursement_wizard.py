from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsAdvanceDisbursementWizard(models.TransientModel):
    """Physically pay the advance amount out to its holder through a chosen
    bank/cash journal, gated on a mandatory attachment (the signed
    disbursement voucher / cash acknowledgement) - the counterpart to
    Settle Advance, and built on the exact same principle: a real amount
    changing hands needs a real, reconciliation-ready journal entry through
    a journal the user actually picks, not a fixed company default that may
    not even be a real bank/cash journal.

    Only reachable once the advance is LOCKED (see arcs.advance.action_lock):
    the holder must already have been debited via a real accrual entry
    before any cash moves - this wizard only ever clears that already-booked
    liability, it never touches the Advance (Receivable) account itself.

    Works on any locked arcs.advance, whichever menu it came from - the
    generic 'Advances' list, or one auto-locked by an acquisition's
    'Disburse Advance' button in arcs_request. This module knows nothing
    about acquisitions; arcs_request only ever points this wizard at an
    advance_id it already created and locked, exactly like it does for
    Settle Advance."""

    _name = "arcs.advance.disbursement.wizard"
    _description = "Disburse Advance"

    advance_id = fields.Many2one(
        "arcs.advance", string="Advance", required=True, readonly=True, ondelete="cascade")
    currency_id = fields.Many2one(related="advance_id.currency_id", readonly=True)
    employee_id = fields.Many2one(related="advance_id.employee_id", readonly=True)
    zone_id = fields.Many2one(related="advance_id.zone_id", readonly=True)
    partner_id = fields.Many2one(related="advance_id.partner_id", readonly=True)
    amount = fields.Monetary(related="advance_id.amount", readonly=True)
    journal_id = fields.Many2one(
        "account.journal", string="Bank/Cash Journal", required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="The journal the cash actually moves through - its own default account "
             "is used for the cash leg, so this entry reconciles against that "
             "journal's bank statement.")
    reference = fields.Char(
        string="Voucher / Reference",
        help="The cash disbursement voucher number, or the holder's signed "
             "acknowledgement reference.")
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="At least one attachment is required - the signed disbursement voucher "
             "or the holder's acknowledgement of receipt.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        advance_id = self.env.context.get("default_advance_id") or self.env.context.get("active_id")
        advance = self.env["arcs.advance"].browse(advance_id)
        if advance.exists():
            res["advance_id"] = advance.id
        return res

    def action_confirm(self):
        self.ensure_one()
        advance = self.advance_id
        if advance.state != "locked":
            raise UserError(_(
                "Only locked advances can be disbursed. Use 'Lock Advance' first."))
        if not self.journal_id:
            raise UserError(_("Select the bank/cash journal the cash moves through."))
        if not self.attachment_ids:
            raise UserError(_(
                "Attach the disbursement voucher or the holder's signed acknowledgement "
                "before confirming this disbursement."))

        advance.action_issue(journal_id=self.journal_id.id)

        advance.message_post(
            body=_(
                "Advance disbursed: %(amount).2f %(cur)s via %(journal)s (%(ref)s)."
            ) % {
                "amount": self.amount, "cur": self.currency_id.name or "",
                "journal": self.journal_id.name, "ref": self.reference or advance.name,
            },
            attachment_ids=self.attachment_ids.ids,
        )
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        return {"type": "ir.actions.act_window_close"}
