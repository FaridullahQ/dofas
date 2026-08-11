import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsFundReceipt(models.Model):
    _name = "arcs.fund.receipt"
    _description = "Donor Fund Receipt"
    _inherit = ["arcs.approval.mixin", "arcs.voucher.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "received_date desc, id desc"

    name = fields.Char(string="Receipt Number", required=True, copy=False, index=True,
                       default=lambda s: _("New"), tracking=True)
    grant_id = fields.Many2one("arcs.grant", string="Grant", required=True, tracking=True,
                               domain="[('state','in',('approved','active'))]")
    donor_id = fields.Many2one(related="grant_id.donor_id", store=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    installment = fields.Char(string="Installment")

    # --- bank voucher reference (NEW) ---
    bank_voucher_ref = fields.Char(string="Bank Voucher Reference", copy=False, tracking=True,
                                   help="The bank's transfer/voucher number for this receipt.")

    journal_id = fields.Many2one("account.journal", string="Bank Journal",
                                 domain="[('type','in',('bank','cash'))]", tracking=True,
                                 help="Bank/cash journal the funds are deposited into.")
    receivable_account_id = fields.Many2one(
        "account.account", string="Income / Source Account",
        domain="[('deprecated','=',False), ('account_type','=','asset_cash')]",
        help="The credit account. Restricted to Bank and Cash type accounts, "
             "matching the Bank Journal above.")
    currency_id = fields.Many2one("res.currency", required=True,
                                  default=lambda s: s.env.company.currency_id)
    exchange_rate = fields.Float(string="Exchange Rate", digits=(12, 6), default=1.0)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", tracking=True)
    amount_words = fields.Char(string="Amount in Words", compute="_compute_amount_words")
    received_date = fields.Date(string="Received Date", required=True,
                                default=fields.Date.context_today, tracking=True)
    purpose = fields.Char(string="Purpose of Funds")
    state = fields.Selection([("draft", "Draft"), ("posted", "Posted")],
                             default="draft", required=True, tracking=True, copy=False)

    # --- accounting link (NEW) ---
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    move_count = fields.Integer(compute="_compute_move_count")

    # --- attachment gate (NEW) ---
    attachment_count = fields.Integer(compute="_compute_attachment_count")
    voucher_attached = fields.Boolean(compute="_compute_attachment_count",
                                      string="Voucher Attached")

    # --- donor acknowledgement email ---
    thanks_email_sent = fields.Boolean(string="Acknowledgement Emailed", readonly=True,
                                       copy=False, tracking=True)
    thanks_email_date = fields.Datetime(string="Emailed On", readonly=True, copy=False)

    _sql_constraints = [
        ("name_uniq", "unique(name, company_id)", "The Receipt Number must be unique per company."),
        ("amount_positive", "CHECK(amount > 0)", "The receipt amount must be greater than zero."),
        ("voucher_uniq", "unique(bank_voucher_ref, company_id)",
         "This Bank Voucher Reference is already recorded."),
    ]

    @api.depends("amount", "currency_id")
    def _compute_amount_words(self):
        for r in self:
            try:
                r.amount_words = (r.currency_id.amount_to_text(r.amount or 0.0)
                                  if r.currency_id else "")
            except Exception:
                r.amount_words = ""

    def _compute_move_count(self):
        for r in self:
            r.move_count = 1 if r.move_id else 0

    def _compute_attachment_count(self):
        Att = self.env["ir.attachment"]
        for r in self:
            cnt = Att.search_count([
                ("res_model", "=", self._name), ("res_id", "=", r.id)]) if r.id else 0
            r.attachment_count = cnt
            r.voucher_attached = cnt > 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("arcs.fund.receipt") or _("New")
        return super().create(vals_list)

    # ---------------- workflow ----------------
    def action_post(self):
        for r in self:
            if r.state != "draft":
                raise UserError(_("Only draft receipts can be posted."))
            if not r.bank_voucher_ref:
                raise UserError(_("Enter the Bank Voucher Reference before posting."))
            if not r.voucher_attached:
                raise UserError(_(
                    "You must attach the scanned bank voucher before posting.\n\n"
                    "Use the paperclip in the chatter to attach the document, then post."))
            if not r.journal_id or not r.receivable_account_id:
                raise UserError(_(
                    "Set the Bank Journal and the Income/Source Account before posting."))
            r._create_move()
        return self._transition("posted", "post")

    def action_reset(self):
        for r in self:
            if r.move_id:
                move = r.move_id
                r.move_id = False
                if move.state == "posted":
                    move.button_draft()
                move.unlink()
        return self._transition("draft", "reset")

    def _create_move(self):
        """Dr Bank/Cash, Cr Income/Source — tagged with the grant analytic account."""
        self.ensure_one()
        debit_account = self.journal_id.default_account_id
        if not debit_account:
            raise UserError(_(
                "The bank journal '%s' has no default account set.") % self.journal_id.name)
        analytic = self.grant_id.analytic_account_id
        distribution = {str(analytic.id): 100} if analytic else False
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": self.received_date,
            "ref": _("Fund receipt %s (voucher %s)") % (self.name, self.bank_voucher_ref or ""),
            "line_ids": [
                (0, 0, {
                    "name": _("Funds received - %s") % (self.grant_id.name or ""),
                    "account_id": debit_account.id,
                    "debit": self.amount,
                    "credit": 0.0,
                }),
                (0, 0, {
                    "name": _("Donor funding - %s") % (self.donor_id.name or ""),
                    "account_id": self.receivable_account_id.id,
                    "debit": 0.0,
                    "credit": self.amount,
                    "analytic_distribution": distribution,
                }),
            ],
        })
        move.action_post()
        self.move_id = move.id

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print_thanks(self):
        self.ensure_one()
        return self.env.ref("arcs_fund.action_report_fund_thanks").report_action(self)

    # ---------------- donor acknowledgement email ----------------
    def _get_or_create_thanks_attachment(self):
        """Return an existing Thank-You PDF attachment for this receipt,
        generating one if none exists yet, so the send-email wizard always
        opens with a ready-made mandatory attachment."""
        self.ensure_one()
        name = _("Thank-You - %s.pdf") % self.name
        Attachment = self.env["ir.attachment"]
        existing = Attachment.search([
            ("res_model", "=", self._name), ("res_id", "=", self.id),
            ("name", "=", name)], limit=1)
        if existing:
            return existing
        report = self.env.ref("arcs_fund.action_report_fund_thanks")
        pdf_content, _fmt = report._render_qweb_pdf(report.report_name, self.ids)
        return Attachment.create({
            "name": name,
            "type": "binary",
            "datas": base64.b64encode(pdf_content),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/pdf",
        })

    # ---------------- voucher printing ----------------
    def _voucher_title(self):
        return "Fund Receipt Voucher"

    def _voucher_party_label(self):
        return "Donor"

    def _voucher_party_name(self):
        return self.donor_id.name

    def _voucher_context_line(self):
        parts = [p for p in (self.grant_id.name, self.bank_voucher_ref) if p]
        return " | ".join(parts) if parts else False

    def action_print_voucher(self):
        self.ensure_one()
        return self.env.ref("arcs_fund.action_report_fund_receipt_voucher").report_action(self)

    def action_open_send_wizard(self):
        self.ensure_one()
        if self.state != "posted":
            raise UserError(_("Only posted receipts can be emailed to the donor."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Acknowledgement Email"),
            "res_model": "arcs.fund.receipt.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_fund_receipt_id": self.id},
        }
