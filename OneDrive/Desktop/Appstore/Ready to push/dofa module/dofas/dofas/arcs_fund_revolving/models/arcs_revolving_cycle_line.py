from odoo import fields, models


class ArcsRevolvingCycleLine(models.Model):
    """The specific approved budget lines a Revolving Fund cycle's committed
    amount is earmarked against (SRS 3.1: 'specified expense lines'). This
    is deliberately a thin allocation record, not a parallel budget - the
    real budget-line ceiling enforcement stays in arcs_budget/arcs_expense
    unchanged; this table only records intent per cycle."""

    _name = "arcs.revolving.cycle.line"
    _description = "Revolving Fund Cycle - Budget Line Allocation"
    _order = "cycle_id, id"

    cycle_id = fields.Many2one(
        "arcs.revolving.cycle", required=True, ondelete="cascade", index=True)
    grant_id = fields.Many2one(related="cycle_id.grant_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="cycle_id.currency_id", readonly=True)
    budget_line_id = fields.Many2one(
        "arcs.budget.line", string="Budget Line", required=True,
        domain="[('grant_id', '=', grant_id), ('budget_state', '=', 'approved')]")
    amount = fields.Monetary(currency_field="currency_id", required=True)

    _sql_constraints = [
        ("amount_non_negative", "CHECK(amount >= 0)",
         "The allocated amount cannot be negative."),
        ("line_uniq", "unique(cycle_id, budget_line_id)",
         "This budget line is already allocated on this cycle."),
    ]
