from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ArcsAdvanceLiquidation(models.Model):
    _name = "arcs.advance.liquidation"
    _description = "Advance Liquidation"
    _inherit = ["arcs.approval.mixin", "mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(
        required=True,
        default=lambda s: _("New"),
        copy=False,
        readonly=True,
        help="Auto-generated reference number for this liquidation report.",
    )

    # ── Core link ─────────────────────────────────────────────────────────────
    advance_id = fields.Many2one(
        "arcs.advance",
        required=True,
        ondelete="cascade",
        tracking=True,
        domain="[('state','=','issued')]",
        help="The issued advance this liquidation is settling. "
             "Only advances in 'Issued' state are selectable. "
             "You can only liquidate advances assigned to you.",
    )

    # ── Fields related from advance (stored for rules / reporting) ────────────
    zone_id = fields.Many2one(related="advance_id.zone_id", store=True)
    company_id = fields.Many2one(related="advance_id.company_id", store=True)
    currency_id = fields.Many2one(related="advance_id.currency_id", store=True)

    # Holder identity — stored so record rules and searches work without joins
    holder_user_id = fields.Many2one(
        "res.users",
        related="advance_id.holder_user_id",
        string="Holder (Debtor)",
        store=True,
        help="The staff member who holds this advance and is submitting the liquidation. "
             "Derived automatically from the linked advance.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        related="advance_id.partner_id",
        string="Advance Partner",
        store=True,
        help="The accounting partner linked to this advance — used on journal entry lines "
             "so the advance receivable balance settles to zero after liquidation.",
    )

    # ── Liquidation details ───────────────────────────────────────────────────
    date = fields.Date(
        default=fields.Date.context_today,
        tracking=True,
        help="Date this liquidation report was prepared or the expenses were incurred.",
    )
    expense_ids = fields.Many2many(
        "arcs.expense",
        string="Justified Expenses",
        domain="[('state','=','posted')]",
        help="Attach posted expense records that justify the advance spending. "
             "The total of these expenses must not exceed the advance's remaining available balance.",
    )
    amount = fields.Monetary(
        compute="_compute_amount",
        store=True,
        currency_field="currency_id",
        help="Total of all linked justified expenses. Computed automatically.",
    )

    # Read-only informational fields surfaced from advance for the user's benefit
    advance_amount = fields.Monetary(
        related="advance_id.amount",
        string="Advance Amount",
        currency_field="currency_id",
        help="Total amount originally issued in the linked advance.",
    )
    advance_available = fields.Monetary(
        compute="_compute_advance_available",
        string="Available to Liquidate",
        currency_field="currency_id",
        store=False,
        help="Remaining advance balance available for this liquidation: "
             "Advance Amount − Already Reported − Cash Returned − "
             "Other non-cancelled liquidations not yet counted in Reported "
             "(i.e. submitted/approved ones pending posting). "
             "This liquidation's own amount is excluded from the deduction so editing is safe.",
    )

    move_id = fields.Many2one(
        "account.move",
        string="Liquidation Entry",
        readonly=True,
        copy=False,
        help="Journal entry posted when this liquidation is approved and posted to the ledger.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("posted", "Posted"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        help="Lifecycle:\n"
             "• Draft – being prepared by the holder.\n"
             "• Submitted – sent to finance for review.\n"
             "• Approved – finance has accepted the expenses.\n"
             "• Posted – journal entry created; advance balance reduced.\n"
             "• Cancelled – rejected or voided.",
    )
    note = fields.Text(
        help="Remarks for the finance reviewer — e.g. explanation of unusual expenses, "
             "supporting document references, or outstanding items.",
    )

    # ── Compute: expense total ─────────────────────────────────────────────────

    @api.depends("expense_ids.amount")
    def _compute_amount(self):
        for liq in self:
            liq.amount = sum(liq.expense_ids.mapped("amount"))

    # ── Compute: how much the holder can still justify on this advance ─────────

    @api.depends(
        "advance_id",
        "advance_id.amount",
        "advance_id.returned_amount",
        "advance_id.liquidation_ids.amount",
        "advance_id.liquidation_ids.state",
        "amount",
    )
    def _compute_advance_available(self):
        """
        Available = Advance Amount
                  − Cash Returned
                  − Sum of sibling liquidations that are NOT cancelled and NOT this record
                    (includes draft/submitted/approved/posted — we are conservative:
                     once an amount is claimed in any active liquidation it reduces headroom)

        We intentionally exclude 'posted' from the "sibling" filter because
        advance_id.reported_amount already counts posted ones.  Using that field
        would double-count.  Instead we recompute from scratch per liquidation.
        """
        for liq in self:
            adv = liq.advance_id
            if not adv:
                liq.advance_available = 0.0
                continue
            siblings = adv.liquidation_ids.filtered(
                lambda l: l.id != liq.id and l.id != liq._origin.id
                and l.state not in ("cancelled",)
            )
            already_claimed = sum(siblings.mapped("amount"))
            liq.advance_available = adv.amount - adv.returned_amount - already_claimed

    # ── Sequence ──────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("arcs.advance.liquidation")
                    or _("New")
                )
        return super().create(vals_list)

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains("advance_id", "amount", "expense_ids")
    def _check_amount_within_advance(self):
        """
        Core financial control: a liquidation cannot claim more than
        the advance's remaining available balance - UNLESS the advance has
        Allow Liquidation Above Advance switched on (off by default; see
        arcs.advance), in which case the holder may have legitimately spent
        more than the advance and fronted the difference themselves. That
        difference is not a validation bypass in the dark: it still has to
        clear Finance's normal Submit → Approve → Post review on this same
        liquidation, and the excess is paid back to the holder afterwards
        through Settle Advance, not silently absorbed.

        Formula (conservative, per-liquidation):
            Allowed = Advance.amount
                    − Advance.returned_amount
                    − Σ sibling_liquidation.amount  (all states except cancelled)
                      (excluding THIS liquidation to avoid self-deduction on edit)

        We use a float tolerance of 0.01 to avoid rounding rejections on minor
        currency conversions (e.g. 1999.999 vs 2000.00).
        """
        precision = 0.01
        for liq in self:
            adv = liq.advance_id
            if not adv or adv.allow_over_liquidation:
                continue
            siblings = adv.liquidation_ids.filtered(
                lambda l: l.id != liq.id and l.state not in ("cancelled",)
            )
            already_claimed = sum(siblings.mapped("amount"))
            ceiling = adv.amount - adv.returned_amount - already_claimed
            if liq.amount > ceiling + precision:
                raise ValidationError(_(
                    "Liquidation %(liq)s cannot be saved.\n\n"
                    "Advance %(adv)s — Financial ceiling check:\n"
                    "  • Advance issued:      %(issued).2f %(cur)s\n"
                    "  • Cash returned:       %(ret).2f %(cur)s\n"
                    "  • Already claimed:     %(claimed).2f %(cur)s\n"
                    "  • Available ceiling:   %(ceil).2f %(cur)s\n"
                    "  • This liquidation:    %(this).2f %(cur)s\n\n"
                    "Reduce the justified expenses or correct the advance amount. If the "
                    "holder genuinely spent more than the advance and covered the "
                    "difference themselves, switch on 'Allow Liquidation Above Advance' "
                    "on the advance first - the excess is then paid back via Settle "
                    "Advance, still subject to the normal Finance review on this "
                    "liquidation."
                ) % {
                    "liq": liq.name or _("New"),
                    "adv": adv.name,
                    "issued": adv.amount,
                    "ret": adv.returned_amount,
                    "claimed": already_claimed,
                    "ceil": ceiling,
                    "this": liq.amount,
                    "cur": adv.currency_id.name or "",
                })

    @api.constrains("advance_id")
    def _check_advance_is_issued(self):
        """Prevent linking to non-issued advances (e.g. draft, closed, cancelled)."""
        for liq in self:
            if liq.advance_id and liq.advance_id.state != "issued":
                raise ValidationError(_(
                    "You can only create a liquidation against an advance in 'Issued' state. "
                    "Advance '%(adv)s' is currently '%(state)s'."
                ) % {"adv": liq.advance_id.name, "state": liq.advance_id.state})

    @api.constrains("advance_id", "holder_user_id")
    def _check_holder_ownership(self):
        """
        A regular user (Finance Officer / Project Manager / plain user) can only
        submit liquidations for advances where they are the registered Holder.
        Finance Managers and System Admins are exempt — they can manage any advance.
        """
        finance_mgr_group = self.env.ref("arcs_base.group_finance_manager", raise_if_not_found=False)
        sys_admin_group = self.env.ref("arcs_base.group_system_admin", raise_if_not_found=False)
        exempt_groups = [g for g in [finance_mgr_group, sys_admin_group] if g]

        for liq in self:
            # Skip if user is Finance Manager or System Admin
            if any(g in self.env.user.groups_id for g in exempt_groups):
                continue
            adv = liq.advance_id
            if not adv:
                continue
            # Advance must be assigned to the current user as holder
            if adv.holder_user_id and adv.holder_user_id != self.env.user:
                raise ValidationError(_(
                    "You are not authorised to submit a liquidation for advance '%(adv)s'.\n"
                    "This advance is assigned to %(holder)s. "
                    "Only the advance holder or a Finance Manager may liquidate it."
                ) % {
                    "adv": adv.name,
                    "holder": adv.holder_user_id.name,
                })

    # ── Business validations ──────────────────────────────────────────────────

    def _check_amount(self):
        for liq in self:
            if liq.amount <= 0:
                raise UserError(_(
                    "Add at least one justified expense before submitting. "
                    "The total amount must be greater than zero."
                ))

    # ── State transitions ─────────────────────────────────────────────────────

    def action_submit(self):
        self._check_amount()
        # Re-run the ceiling check at submit time (belt-and-suspenders)
        self._check_amount_within_advance()
        return self._transition("submitted", "submit")

    def action_approve(self):
        # Final ceiling check before finance commits approval
        self._check_amount_within_advance()
        return self._transition("approved", "approve")

    def action_post(self):
        for liq in self:
            if liq.state != "approved":
                raise UserError(_("Only approved liquidations can be posted."))
            if liq.advance_id.company_id.arcs_advance_book:
                liq.move_id = liq._create_liquidation_move().id
        return self._transition("posted", "post")

    def action_reset_draft(self, reason=False):
        return self._transition("draft", "reset", comment=reason)

    def action_cancel(self, reason=False):
        for liq in self:
            if liq.state == "posted":
                raise UserError(_(
                    "Cannot cancel a posted liquidation. "
                    "Reverse the journal entry first if required."
                ))
        return self._transition("cancelled", "cancel", comment=reason)

    # ── Journal entry ─────────────────────────────────────────────────────────

    def _create_liquidation_move(self):
        """
        Accounting flow on liquidation posting:

          Dr  Advance Clearing Account   (expense recognised)
          Cr  Advance Receivable Account (partner's debt reduced)

        The partner is MANDATORY on the receivable line so the open item
        created at issuance (Dr Receivable / Cr Cash) can be reconciled
        and the partner's balance settles to zero.
        """
        self.ensure_one()
        c = self.company_id
        journal = c.arcs_advance_journal_id
        adv_account = c.arcs_advance_account_id
        clearing = c.arcs_advance_clearing_account_id
        if not journal or not adv_account or not clearing:
            raise UserError(_(
                "Please configure the Advance Journal, Advance Account, and Clearing Account "
                "under Settings → ARCS Configuration before posting liquidations."
            ))
        amount = self.advance_id._company_amount(self.amount)
        ref = _("Liquidation: %s — Advance: %s") % (self.name, self.advance_id.name)
        partner = self.partner_id or self.advance_id.partner_id

        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.date,
            "ref": ref,
            "company_id": c.id,
            "line_ids": [
                # Dr Clearing — expense side (no partner needed; hits expense account)
                (0, 0, {
                    "name": ref,
                    "account_id": clearing.id,
                    "partner_id": partner.id if partner else False,
                    "debit": amount,
                    "credit": 0.0,
                }),
                # Cr Advance Receivable — MUST carry partner to reconcile with issuance entry
                (0, 0, {
                    "name": ref,
                    "account_id": adv_account.id,
                    "partner_id": partner.id if partner else False,
                    "debit": 0.0,
                    "credit": amount,
                }),
            ],
        })
        move.action_post()
        return move

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }
