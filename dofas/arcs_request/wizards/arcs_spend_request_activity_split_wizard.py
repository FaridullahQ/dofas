from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class ArcsSpendRequestActivitySplitWizard(models.TransientModel):
    """Recovery action for an acquisition flagged Insufficient Funds on the
    Activity/Project/Program axis (shortfall_type='activity'): cover the
    approved amount by drawing part of it from the acquisition's own
    Activity's Planned Cost and the rest from one or more other activities -
    mirrors arcs.spend.request.split.wizard exactly, one level up.

    The budget line itself is never re-checked here: action_commit() only
    ever reaches this path after confirming the budget line already has
    room for the FULL approved amount, so the underlying budget-line
    reservation doesn't need splitting - each activity leg still reserves
    against the SAME budget line (sequential reserve() calls against one
    line are safe and additive: each call re-locks and re-checks the
    line's CURRENT available, which already reflects prior legs), only
    tagged with a different activity_id per leg, so each activity's own
    ceiling is drawn down separately and can be released separately."""

    _name = "arcs.spend.request.activity.split.wizard"
    _description = "Split Reserve Across Activities"

    request_id = fields.Many2one(
        "arcs.spend.request", string="Acquisition", required=True, readonly=True,
        ondelete="cascade")
    currency_id = fields.Many2one(related="request_id.currency_id", readonly=True)
    approved_amount = fields.Monetary(
        related="request_id.approved_amount", readonly=True,
        help="Total amount to be covered between the primary activity and the splits below.")
    primary_activity_id = fields.Many2one(
        related="request_id.activity_id", string="Primary Activity", readonly=True)
    primary_available = fields.Monetary(
        string="Primary Activity Available", currency_field="currency_id", readonly=True,
        help="Live available Planned Cost on the primary activity, checked when this "
             "wizard opened. Indicative only - the authoritative check happens, under "
             "lock, when you confirm.")
    primary_amount = fields.Monetary(
        string="From Primary Activity", currency_field="currency_id",
        help="How much of the approved amount to reserve on the original activity. "
             "The remainder must be covered by the other activities below.")
    line_ids = fields.One2many(
        "arcs.spend.request.activity.split.wizard.line", "wizard_id",
        string="Other Activities")
    total_allocated = fields.Monetary(
        string="Total Allocated", compute="_compute_totals", currency_field="currency_id")
    remaining_to_allocate = fields.Monetary(
        string="Remaining to Allocate", compute="_compute_totals", currency_field="currency_id",
        help="Must reach zero before the split can be confirmed.")
    reference = fields.Char(
        string="Reference", required=True,
        help="Supporting document reference (approval memo, justification, etc.) - "
             "required, together with an attachment, before confirming.")
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Attachments",
        help="At least one attachment is required - the document backing this split.")

    @api.depends("primary_amount", "line_ids.amount", "approved_amount")
    def _compute_totals(self):
        for w in self:
            w.total_allocated = (w.primary_amount or 0.0) + sum(w.line_ids.mapped("amount"))
            w.remaining_to_allocate = w.approved_amount - w.total_allocated

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("default_request_id") or self.env.context.get("active_id")
        request = self.env["arcs.spend.request"].browse(request_id)
        if request.exists():
            res["request_id"] = request.id
            available = request.activity_id.get_available_locked() \
                if request.activity_id else 0.0
            res["primary_available"] = max(available, 0.0)
            res["primary_amount"] = min(max(available, 0.0), request.approved_amount or 0.0)
        return res

    # ================================================================ actions
    def action_confirm(self):
        self.ensure_one()
        request = self.request_id
        if not (self.env.user.has_group("arcs_base.group_finance_manager")
                or self.env.user.has_group("arcs_base.group_system_admin")):
            raise UserError(_("Only a Finance Manager can split a reserve across activities."))
        if request.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        if request.shortfall_type != "activity":
            raise UserError(_(
                "This request is short on the budget line, not Activity/Project/Program "
                "Planned Cost."))
        if not self.line_ids:
            raise UserError(_("Add at least one other activity before confirming the split."))
        if not self.reference or not self.reference.strip():
            raise UserError(_("Enter a Reference before confirming the split."))
        if not self.attachment_ids:
            raise UserError(_(
                "Attach the supporting document before confirming this split."))

        rounding = self.currency_id.rounding or 0.01
        if float_compare(self.primary_amount, 0.0, precision_rounding=rounding) < 0:
            raise UserError(_("The amount from the primary activity cannot be negative."))
        for line in self.line_ids:
            if float_compare(line.amount, 0.0, precision_rounding=rounding) <= 0:
                raise UserError(_("Every split line's amount must be greater than zero."))
            if line.activity_id.state != "approved":
                raise UserError(_(
                    "'%s' is not an Approved activity.") % line.activity_id.name)
            if line.activity_id.currency_id != self.currency_id:
                raise UserError(_(
                    "'%(a)s' is in %(c1)s; every split line must be in the "
                    "acquisition's currency (%(c2)s).") % {
                    "a": line.activity_id.name,
                    "c1": line.activity_id.currency_id.name,
                    "c2": self.currency_id.name})
        activities = self.line_ids.mapped("activity_id")
        if len(activities) != len(set(activities.ids)):
            raise UserError(_("Each activity can only appear once in the split."))
        if self.primary_activity_id in activities:
            raise UserError(_(
                "'%s' is already the primary activity; adjust 'From Primary Activity' "
                "above instead of adding it again below.") % self.primary_activity_id.name)
        if float_compare(self.remaining_to_allocate, 0.0, precision_rounding=rounding) != 0:
            raise UserError(_(
                "The allocated amounts must add up exactly to the approved amount "
                "(%(total).2f %(cur)s). Currently %(rem).2f %(cur)s is unallocated.") % {
                "total": self.approved_amount, "cur": self.currency_id.name or "",
                "rem": self.remaining_to_allocate})

        allocations = []
        if float_compare(self.primary_amount, 0.0, precision_rounding=rounding) > 0:
            allocations.append((self.primary_activity_id, self.primary_amount))
        for line in self.line_ids:
            allocations.append((line.activity_id, line.amount))
        # Lock activities in a stable order (by id) before reserving, so two
        # splits touching the same pair of activities concurrently can never
        # deadlock by locking them in opposite orders.
        allocations.sort(key=lambda pair: pair[0].id)

        commitments = self.env["arcs.commitment"]
        budget_line = request.budget_line_id
        for activity, amount in allocations:
            # Sequential reserve() calls against the SAME budget line are
            # safe and additive (each re-locks and re-checks the line's
            # CURRENT available, already net of prior legs) - the budget
            # line itself was already confirmed to have room for the full
            # total before this wizard could even open.
            commitments |= budget_line.reserve(
                amount, source_ref="%s,%s" % (request._name, request.id),
                spend_request_id=request.id,
                activity_id=activity.id,
                project_id=activity.project_id.id,
                program_id=activity.project_id.program_id.id,
            )

        primary_commitment = commitments.filtered(
            lambda c: c.activity_id == self.primary_activity_id)
        request.commitment_id = (primary_commitment or commitments)[:1].id
        summary = ", ".join(
            "%s: %.2f %s" % (c.activity_id.name, c.amount, self.currency_id.name or "")
            for c in commitments.sorted("id"))
        request.write({
            "shortfall_amount": 0.0, "shortfall_type": "budget_line",
            "insufficient_funds_note": False,
        })
        request._transition("committed", "activity_split_commit", comment=_(
            "Reserved across %(n)s activities: %(lines)s") % {
            "n": len(commitments), "lines": summary})
        request.message_post(
            body=_("Split reserve reference: %s") % self.reference,
            attachment_ids=self.attachment_ids.ids,
        )
        return {"type": "ir.actions.act_window_close"}

    def action_discard(self):
        self.unlink()
        return {"type": "ir.actions.act_window_close"}


class ArcsSpendRequestActivitySplitWizardLine(models.TransientModel):
    _name = "arcs.spend.request.activity.split.wizard.line"
    _description = "Split Reserve Activity Line"

    wizard_id = fields.Many2one(
        "arcs.spend.request.activity.split.wizard", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    activity_id = fields.Many2one(
        "arcs.activity", string="Activity", required=True,
        domain="[('state', '=', 'approved')]")
    available_amount = fields.Monetary(
        related="activity_id.available_amount", string="Available (indicative)",
        readonly=True,
        help="Snapshot at selection time; the real balance is re-checked under lock "
             "when you confirm the split.")
    amount = fields.Monetary(string="Amount", currency_field="currency_id")

    @api.onchange("activity_id")
    def _onchange_activity_id(self):
        """Same auto-fill principle as the budget-line split wizard's line:
        picking an activity fills its Amount with whatever's still
        unallocated, capped at what THIS activity can actually give (its
        own live available Planned Cost)."""
        if not self.activity_id or not self.wizard_id:
            return
        unallocated_before_this_line = self.wizard_id.remaining_to_allocate + (self.amount or 0.0)
        activity_available = max(self.activity_id.available_amount, 0.0)
        self.amount = max(min(unallocated_before_this_line, activity_available), 0.0)

    @api.constrains("amount")
    def _check_amount_non_negative(self):
        for l in self:
            if l.amount < 0:
                raise ValidationError(_("The amount cannot be negative."))
