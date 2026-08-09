from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class McitSpendRequestSplitWizard(models.TransientModel):
    """4th recovery action for an acquisition flagged Insufficient Funds
    (alongside reassign / internal transfer / donor funding): cover the
    approved amount by reserving part of it on the primary budget line and
    the rest on one or more other budget lines - e.g. approved amount 1000,
    primary line has 700 available, the other 300 comes from a second line.
    Each portion becomes its own mcit.commitment (one per budget line used),
    so every line involved is tracked, released, and reported on separately -
    unlike an internal transfer or donor funding request, this does not move
    money between lines or wait on anyone's approval; it reserves directly
    across the lines that already have room, right now."""

    _name = "mcit.spend.request.split.wizard"
    _description = "Split Reserve Across Budget Lines"

    request_id = fields.Many2one(
        "mcit.spend.request", string="Acquisition", required=True, readonly=True,
        ondelete="cascade")
    currency_id = fields.Many2one(related="request_id.currency_id", readonly=True)
    approved_amount = fields.Monetary(
        related="request_id.approved_amount", readonly=True,
        help="Total amount to be covered between the primary line and the splits below.")
    primary_budget_line_id = fields.Many2one(
        related="request_id.budget_line_id", string="Primary Budget Line", readonly=True)
    primary_available = fields.Monetary(
        string="Primary Line Available", currency_field="currency_id", readonly=True,
        help="Live available balance on the primary budget line, checked when this "
             "wizard opened. Indicative only - the authoritative check happens, under "
             "lock, when you confirm.")
    primary_amount = fields.Monetary(
        string="From Primary Line", currency_field="currency_id",
        help="How much of the approved amount to reserve on the original budget line. "
             "The remainder must be covered by the other budget lines below.")
    line_ids = fields.One2many(
        "mcit.spend.request.split.wizard.line", "wizard_id", string="Other Budget Lines")
    total_allocated = fields.Monetary(
        string="Total Allocated", compute="_compute_totals", currency_field="currency_id")
    remaining_to_allocate = fields.Monetary(
        string="Remaining to Allocate", compute="_compute_totals", currency_field="currency_id",
        help="Must reach zero before the split can be confirmed.")

    @api.depends("primary_amount", "line_ids.amount", "approved_amount")
    def _compute_totals(self):
        for w in self:
            w.total_allocated = (w.primary_amount or 0.0) + sum(w.line_ids.mapped("amount"))
            w.remaining_to_allocate = w.approved_amount - w.total_allocated

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_request_id") or self.env.context.get("active_id")
        request = self.env["mcit.spend.request"].browse(request_id)
        if request.exists():
            res["request_id"] = request.id
            available = request.budget_line_id.get_available_locked() \
                if request.budget_line_id else 0.0
            res["primary_available"] = max(available, 0.0)
            res["primary_amount"] = min(max(available, 0.0), request.approved_amount or 0.0)
        return res

    # ================================================================ actions
    def action_confirm(self):
        self.ensure_one()
        request = self.request_id
        if not (self.env.user.has_group("mcit_base.group_finance_manager")
                or self.env.user.has_group("mcit_base.group_system_admin")):
            raise UserError(_("Only a Finance Manager can split a reserve across budget lines."))
        if request.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        if not self.line_ids:
            raise UserError(_("Add at least one other budget line before confirming the split."))

        rounding = self.currency_id.rounding or 0.01
        if float_compare(self.primary_amount, 0.0, precision_rounding=rounding) < 0:
            raise UserError(_("The amount from the primary line cannot be negative."))
        for line in self.line_ids:
            if float_compare(line.amount, 0.0, precision_rounding=rounding) <= 0:
                raise UserError(_("Every split line's amount must be greater than zero."))
            if line.budget_line_id.budget_state != "approved":
                raise UserError(_(
                    "'%s' is not on an Approved budget version.") % line.budget_line_id.name)
            if line.budget_line_id.currency_id != self.currency_id:
                raise UserError(_(
                    "'%(line)s' is in %(c1)s; every split line must be in the "
                    "acquisition's currency (%(c2)s).") % {
                    "line": line.budget_line_id.name,
                    "c1": line.budget_line_id.currency_id.name,
                    "c2": self.currency_id.name})
        budget_lines = self.line_ids.mapped("budget_line_id")
        if len(budget_lines) != len(set(budget_lines.ids)):
            raise UserError(_("Each budget line can only appear once in the split."))
        if self.primary_budget_line_id in budget_lines:
            raise UserError(_(
                "'%s' is already the primary budget line; adjust 'From Primary Line' "
                "above instead of adding it again below.") % self.primary_budget_line_id.name)
        if float_compare(self.remaining_to_allocate, 0.0, precision_rounding=rounding) != 0:
            raise UserError(_(
                "The allocated amounts must add up exactly to the approved amount "
                "(%(total).2f %(cur)s). Currently %(rem).2f %(cur)s is unallocated.") % {
                "total": self.approved_amount, "cur": self.currency_id.name or "",
                "rem": self.remaining_to_allocate})

        allocations = []
        if float_compare(self.primary_amount, 0.0, precision_rounding=rounding) > 0:
            allocations.append((self.primary_budget_line_id, self.primary_amount))
        for line in self.line_ids:
            allocations.append((line.budget_line_id, line.amount))
        # Lock budget lines in a stable order (by id) before reserving, so two
        # splits touching the same pair of lines concurrently can never
        # deadlock by locking them in opposite orders.
        allocations.sort(key=lambda pair: pair[0].id)

        commitments = self.env["mcit.commitment"]
        for budget_line, amount in allocations:
            # reserve() itself re-locks and re-checks live availability, so
            # this stays safe even if the balance shown above is now stale.
            commitments |= budget_line.reserve(
                amount, source_ref="%s,%s" % (request._name, request.id),
                spend_request_id=request.id)

        primary_commitment = commitments.filtered(
            lambda c: c.budget_line_id == self.primary_budget_line_id)
        request.commitment_id = (primary_commitment or commitments)[:1].id
        summary = ", ".join(
            "%s: %.2f %s" % (c.budget_line_id.name, c.amount, self.currency_id.name or "")
            for c in commitments.sorted("id"))
        request.write({"shortfall_amount": 0.0, "insufficient_funds_note": False})
        request._transition("committed", "split_commit", comment=_(
            "Reserved across %(n)s budget lines: %(lines)s") % {
            "n": len(commitments), "lines": summary})
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        self.unlink()
        return {"type": "ir.actions.act_window_close"}


class McitSpendRequestSplitWizardLine(models.TransientModel):
    _name = "mcit.spend.request.split.wizard.line"
    _description = "Split Reserve Line"

    wizard_id = fields.Many2one(
        "mcit.spend.request.split.wizard", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    budget_line_id = fields.Many2one(
        "mcit.budget.line", string="Budget Line", required=True,
        domain="[('budget_state', '=', 'approved')]")
    available_amount = fields.Monetary(
        related="budget_line_id.available_amount", string="Available (indicative)",
        readonly=True,
        help="Snapshot at selection time; the real balance is re-checked under lock "
             "when you confirm the split.")
    amount = fields.Monetary(string="Amount", currency_field="currency_id")

    @api.constrains("amount")
    def _check_amount_non_negative(self):
        for l in self:
            if l.amount < 0:
                raise ValidationError(_("The amount cannot be negative."))
