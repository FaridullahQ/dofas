from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class ArcsBudgetLine(models.Model):
    _name = "arcs.budget.line"
    _description = "Grant Budget Line"
    _order = "budget_id, sequence, id"

    budget_id = fields.Many2one("arcs.budget", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    grant_id = fields.Many2one(related="budget_id.grant_id", store=True, index=True)
    company_id = fields.Many2one(related="budget_id.company_id", store=True)
    analytic_account_id = fields.Many2one(related="grant_id.analytic_account_id", store=True)
    currency_id = fields.Many2one(related="budget_id.currency_id", store=True)
    budget_state = fields.Selection(
        related="budget_id.state", store=True, string="Budget Version Status",
        help="Status of the budget version this line belongs to. Only lines on an "
             "Approved version should be selectable for reserving/spending - a "
             "Superseded version is historical and a Draft version isn't active yet.")
    name = fields.Char(string="Budget Line", required=True,
                       help="Select the approved budget category under which expenditures will be charged.")
    category = fields.Selection(
        [("hr", "HR"), ("logistics", "Logistics"), ("procurement", "Procurement"),
         ("training", "Training"), ("travel", "Travel"), ("equipment", "Equipment"),
         ("administration", "Administration"), ("operational", "Operational Costs")],
        string="Category")
    account_ids = fields.Many2many("account.account", string="Cost Accounts",
                                   help="GL accounts whose postings consume this line.")
    commitment_ids = fields.One2many("arcs.commitment", "budget_line_id", string="Commitments")
    incoming_transfer_ids = fields.One2many(
        "arcs.budget.transfer", "to_line_id", string="Incoming Transfers")
    outgoing_transfer_ids = fields.One2many(
        "arcs.budget.transfer", "from_line_id", string="Outgoing Transfers")
    planned_amount = fields.Monetary(string="Planned", currency_field="currency_id",
                                     help="The originally approved budget amount for this line. "
                                          "This never changes because of an internal transfer - "
                                          "only a direct edit to the line (while its budget is in "
                                          "Draft) changes it. See Transferred In / Transferred Out "
                                          "for the effect of transfers, and Net Planned for the "
                                          "resulting spendable ceiling.")
    # Stored so they are aggregatable in Pivot/Graph (read_group needs real SQL
    # columns; a non-stored compute has none -> "Cannot convert field ... to SQL").
    # Recompute is driven by @api.depends on the commitments below. Because every
    # expense/PO that books an actual also flips a commitment state in the SAME
    # transaction, _compute_amounts re-reads the analytic actuals and refreshes
    # actual_amount together with committed_amount. The hard-stop reserve() still
    # forces a live recompute under the row lock, so the control path never trusts
    # a stale stored value.
    committed_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    actual_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    transferred_in_amount = fields.Monetary(
        string="Transferred In", compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Cumulative total moved INTO this line by approved internal budget transfers "
             "(arcs.budget.transfer). A ledger total, not netted against Transferred Out or "
             "against transfers later reversed - a reversal is booked as its own transfer in "
             "the opposite direction, so both the original and the reversal stay visible here.")
    transferred_out_amount = fields.Monetary(
        string="Transferred Out", compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Cumulative total moved OUT of this line by approved internal budget transfers. "
             "Same ledger convention as Transferred In.")
    effective_planned_amount = fields.Monetary(
        string="Net Planned", compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Planned + Transferred In - Transferred Out: the actual ceiling this line can "
             "commit/spend against. Planned itself is left untouched by transfers so it always "
             "shows the originally approved figure; this field shows the effect of transfers.")
    available_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    utilization = fields.Float(string="Utilisation (%)", compute="_compute_amounts", store=True)

    _sql_constraints = [
        ("planned_non_negative", "CHECK(planned_amount >= 0)", "The planned amount cannot be negative."),
    ]

    def _read_actuals(self):
        AAL = self.env["account.analytic.line"]
        analytic_ids = self.mapped("analytic_account_id").ids
        result = {l.id: 0.0 for l in self}
        if not analytic_ids:
            return result
        rows = AAL._read_group(
            [("account_id", "in", analytic_ids)],
            ["account_id", "general_account_id"], ["amount:sum"])
        by_pair = {}
        for analytic, general, amount_sum in rows:
            by_pair[(analytic.id, general.id if general else False)] = amount_sum
        for line in self:
            aid = line.analytic_account_id.id
            spend = 0.0
            for gid in line.account_ids.ids:
                spend -= by_pair.get((aid, gid), 0.0)  # costs are negative analytic amounts
            result[line.id] = spend
        return result

    @api.depends("planned_amount", "commitment_ids.amount", "commitment_ids.state",
                "incoming_transfer_ids.amount", "incoming_transfer_ids.state",
                "outgoing_transfer_ids.amount", "outgoing_transfer_ids.state")
    def _compute_amounts(self):
        actuals = self._read_actuals()
        for line in self:
            company = line.company_id or self.env.company
            committed = sum(line.commitment_ids.filtered(lambda c: c.state == "confirmed").mapped("amount"))
            transferred_in = sum(line.incoming_transfer_ids.filtered(
                lambda t: t.state == "approved").mapped("amount"))
            transferred_out = sum(line.outgoing_transfer_ids.filtered(
                lambda t: t.state == "approved").mapped("amount"))
            effective_planned = line.planned_amount + transferred_in - transferred_out
            actual_company = actuals.get(line.id, 0.0)
            if company.currency_id and line.currency_id and company.currency_id != line.currency_id:
                actual = company.currency_id._convert(actual_company, line.currency_id, company,
                                                       fields.Date.context_today(line))
            else:
                actual = actual_company
            line.committed_amount = committed
            line.actual_amount = actual
            line.transferred_in_amount = transferred_in
            line.transferred_out_amount = transferred_out
            line.effective_planned_amount = effective_planned
            line.available_amount = effective_planned - committed - actual
            line.utilization = (100.0 * (committed + actual) / effective_planned) if effective_planned else 0.0

    @api.constrains("planned_amount")
    def _check_within_grant(self):
        for line in self:
            grant = line.grant_id
            if not grant.approved_amount:
                continue
            total = sum(line.budget_id.line_ids.mapped("planned_amount"))
            if float_compare(total, grant.approved_amount, precision_rounding=line.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "The total of budget lines (%(t)s) exceeds the grant's approved amount (%(g)s).",
                    t=total, g=grant.approved_amount))

    def get_available_locked(self):
        """Lock the row and return the live available amount under that lock.
        Split out of reserve() so callers can pre-check availability (e.g. to
        route a request to a recovery flow) without creating a commitment."""
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM arcs_budget_line WHERE id = %s FOR UPDATE", (self.id,))
        # The aggregates are stored; invalidating clears the cache but a read would
        # then fetch the DB column rather than recompute. Recompute explicitly so the
        # guard uses a live figure derived under the row lock, not a stale snapshot.
        self.invalidate_recordset([
            "committed_amount", "actual_amount", "transferred_in_amount",
            "transferred_out_amount", "effective_planned_amount", "available_amount"])
        self._compute_amounts()
        return self.available_amount

    def reserve(self, amount, source_ref=False, **extra_vals):
        """Concurrency-safe hard stop: lock the line, recompute live, refuse if
        insufficient, then encumber. An action (not a constraint) so it can
        serialise concurrent posters on the same line.

        `extra_vals` is an open extension point (Open/Closed Principle):
        downstream modules that arcs_budget knows nothing about - e.g.
        arcs_request tagging the commitment with `spend_request_id` so it can
        split a single reserve across several calls to this method, one per
        budget line - can pass extra fields to store on the created
        arcs.commitment without this method having to import or reference
        those models."""
        self.ensure_one()
        rounding = self.currency_id.rounding
        available = self.get_available_locked()
        if float_compare(amount, available, precision_rounding=rounding) > 0:
            raise UserError(_(
                "Insufficient budget on line '%(l)s'.\nAvailable: %(a).2f %(c)s - requested: %(r).2f %(c)s.",
                l=self.name, a=available, r=amount, c=self.currency_id.name))
        company = self.company_id or self.env.company
        company_amount = amount
        if company.currency_id and self.currency_id and company.currency_id != self.currency_id:
            company_amount = self.currency_id._convert(amount, company.currency_id, company,
                                                       fields.Date.context_today(self))
        vals = {
            "budget_line_id": self.id, "amount": amount,
            "company_amount": company_amount, "source_ref": source_ref or False,
            "state": "confirmed",
        }
        vals.update(extra_vals)
        return self.env["arcs.commitment"].create(vals)
