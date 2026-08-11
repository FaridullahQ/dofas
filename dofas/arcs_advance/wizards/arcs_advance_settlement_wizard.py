from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsAdvanceSettlementWizard(models.TransientModel):
    """Zero out an issued advance's Outstanding balance with a real journal
    entry through a chosen bank/cash journal, gated on a mandatory attachment
    (the deposit slip or payment slip) - unlike simply typing a number into
    Cash Returned, which books nothing to the ledger.

    Two directions, chosen automatically from the live Outstanding sign:
    - Outstanding > 0: the holder still holds unspent cash and pays it back.
      Dr the journal's cash/bank account / Cr the Advance (Receivable)
      account - money coming IN, closing out the receivable.
    - Outstanding < 0: the holder spent more than the advance and fronted
      the difference themselves (only reachable when the advance has Allow
      Liquidation Above Advance on). Dr the Advance (Receivable) account /
      Cr the journal's cash/bank account - money going OUT, reimbursing them.

    Always posts for real, regardless of the company's 'Book Advances to the
    Ledger' toggle - that toggle governs the internal control-account
    bookkeeping choice for issuing/liquidating; this wizard represents an
    actual amount changing hands and needs a real entry to ever reconcile
    against a bank statement."""

    _name = "arcs.advance.settlement.wizard"
    _description = "Settle Advance"

    advance_id = fields.Many2one(
        "arcs.advance", string="Advance", required=True, readonly=True, ondelete="cascade")
    currency_id = fields.Many2one(related="advance_id.currency_id", readonly=True)
    employee_id = fields.Many2one(related="advance_id.employee_id", readonly=True)
    partner_id = fields.Many2one(related="advance_id.partner_id", readonly=True)
    amount_advanced = fields.Monetary(related="advance_id.amount", readonly=True)
    reported_amount = fields.Monetary(related="advance_id.reported_amount", readonly=True)
    outstanding_amount = fields.Monetary(
        related="advance_id.outstanding_amount", readonly=True,
        help="Positive: the holder still owes this back. Negative: the holder is "
             "owed this as a reimbursement.")
    direction = fields.Selection(
        [("return", "Holder returns unused cash"), ("reimburse", "Holder is reimbursed")],
        compute="_compute_direction", string="Direction")
    settlement_amount = fields.Monetary(
        string="Amount", currency_field="currency_id", required=True,
        help="Defaults to the full Outstanding balance; reduce it for a partial "
             "settlement (any remainder stays Outstanding for a later settlement).")
    journal_id = fields.Many2one(
        "account.journal", string="Bank/Cash Journal", required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="The journal the cash actually moves through.")
    reference = fields.Char(
        string="Slip / Voucher Reference",
        help="The deposit slip number (holder paying back) or payment slip/voucher "
             "number (holder being reimbursed).")
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="At least one attachment is required - the scanned deposit slip or "
             "payment slip evidencing this settlement.")

    @api.depends("outstanding_amount")
    def _compute_direction(self):
        for w in self:
            w.direction = "reimburse" if w.outstanding_amount < 0 else "return"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        advance_id = self.env.context.get("default_advance_id") or self.env.context.get("active_id")
        advance = self.env["arcs.advance"].browse(advance_id)
        if advance.exists():
            res["advance_id"] = advance.id
            res["settlement_amount"] = round(abs(advance.outstanding_amount), 2)
        return res

    def action_confirm(self):
        self.ensure_one()
        advance = self.advance_id
        if advance.state != "issued":
            raise UserError(_("Only issued advances can be settled."))
        rounding = self.currency_id.rounding or 0.01
        if self.settlement_amount <= 0:
            raise UserError(_("Enter an amount greater than zero to settle."))
        # Re-check live, in case something changed since the wizard opened.
        live_outstanding = advance.outstanding_amount
        if self.currency_id.compare_amounts(live_outstanding, 0.0) == 0:
            raise UserError(_("There is nothing left to settle on this advance."))
        live_direction = "reimburse" if live_outstanding < 0 else "return"
        ceiling = abs(live_outstanding)
        if self.settlement_amount > ceiling + rounding:
            raise UserError(_(
                "The settlement amount (%(amt).2f) cannot exceed the outstanding "
                "balance (%(ceil).2f %(cur)s).") % {
                "amt": self.settlement_amount, "ceil": ceiling,
                "cur": self.currency_id.name or ""})
        if not self.attachment_ids:
            raise UserError(_(
                "Attach the deposit slip or payment slip before confirming this "
                "settlement."))
        if not self.journal_id:
            raise UserError(_("Select the bank/cash journal the cash moves through."))

        move = self._create_settlement_move(live_direction)
        if live_direction == "return":
            advance.returned_amount += self.settlement_amount
        else:
            advance.reimbursed_amount += self.settlement_amount

        advance.message_post(
            body=_(
                "Settlement recorded: %(dir)s %(amt).2f %(cur)s via %(journal)s "
                "(%(ref)s)."
            ) % {
                "dir": _("holder returned") if live_direction == "return"
                      else _("holder reimbursed"),
                "amt": self.settlement_amount, "cur": self.currency_id.name or "",
                "journal": self.journal_id.name, "ref": self.reference or move.name,
            },
            attachment_ids=self.attachment_ids.ids,
        )
        if advance.currency_id.compare_amounts(advance.outstanding_amount, 0.0) == 0:
            advance.action_close()
        return {"type": "ir.actions.act_window_close"}

    def _create_settlement_move(self, direction):
        self.ensure_one()
        advance = self.advance_id
        company = advance.company_id
        adv_account = company.arcs_advance_account_id
        if not adv_account:
            raise UserError(_(
                "Configure the Advance (Receivable) Account under Settings → ARCS "
                "Configuration before settling advances."))
        cash_account = self.journal_id.default_account_id
        if not cash_account:
            raise UserError(_(
                "The journal '%s' has no default account set.") % self.journal_id.name)
        amount = advance._company_amount(self.settlement_amount)
        partner = advance.partner_id
        if direction == "return":
            ref = _("Advance return: %s") % advance.name
            debit_account, credit_account = cash_account, adv_account
        else:
            ref = _("Advance reimbursement: %s") % advance.name
            debit_account, credit_account = adv_account, cash_account
        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": fields.Date.context_today(self),
            "ref": "%s (%s)" % (ref, self.reference) if self.reference else ref,
            "company_id": company.id,
            "line_ids": [
                (0, 0, {
                    "name": ref, "account_id": debit_account.id,
                    "partner_id": partner.id if partner else False,
                    "debit": amount, "credit": 0.0,
                }),
                (0, 0, {
                    "name": ref, "account_id": credit_account.id,
                    "partner_id": partner.id if partner else False,
                    "debit": 0.0, "credit": amount,
                }),
            ],
        })
        move.action_post()
        return move

    def action_discard(self):
        return {"type": "ir.actions.act_window_close"}
