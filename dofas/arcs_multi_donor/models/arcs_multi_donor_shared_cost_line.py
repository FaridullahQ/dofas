from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ArcsMultiDonorSharedCostLine(models.Model):
    """One member's share of a shared cost. allocation_pct defaults from the
    member's project-level share but can be overridden for this specific
    cost (e.g. the project splits 70/30 overall, but one particular shared
    training was agreed 50/50) - amount is always recomputed from whatever
    percentage actually ends up here, never typed in directly."""

    _name = "arcs.multi.donor.shared.cost.line"
    _description = "Multi-Donor Shared Cost Split Line"
    _order = "shared_cost_id, id"

    shared_cost_id = fields.Many2one(
        "arcs.multi.donor.shared.cost", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="shared_cost_id.project_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="shared_cost_id.currency_id", readonly=True)
    member_id = fields.Many2one(
        "arcs.multi.donor.project.member", required=True, ondelete="restrict",
        domain="[('project_id', '=', project_id)]")
    grant_id = fields.Many2one(related="member_id.grant_id", store=True, readonly=True)
    donor_id = fields.Many2one(related="member_id.donor_id", readonly=True)

    allocation_pct = fields.Float(
        string="Share (%)", required=True, digits=(5, 2),
        help="Defaults to this member's project-level share, but can be "
             "overridden for this specific shared cost.")
    budget_line_id = fields.Many2one(
        "arcs.budget.line", string="Budget Line", required=True,
        domain="[('grant_id', '=', grant_id), ('budget_state', '=', 'approved')]")
    account_id = fields.Many2one("account.account", string="Account", required=True)
    amount = fields.Monetary(
        compute="_compute_amount", store=True, currency_field="currency_id")
    expense_id = fields.Many2one("arcs.expense", readonly=True, copy=False)

    _sql_constraints = [
        ("shared_cost_member_uniq", "unique(shared_cost_id, member_id)",
         "This grant already has a split line on this shared cost."),
        ("allocation_pct_range", "CHECK(allocation_pct > 0 AND allocation_pct <= 100)",
         "The share must be greater than 0% and no more than 100%."),
    ]

    @api.depends("allocation_pct", "shared_cost_id.total_amount")
    def _compute_amount(self):
        for line in self:
            line.amount = line.shared_cost_id.total_amount * line.allocation_pct / 100.0

    @api.onchange("member_id")
    def _onchange_member_id(self):
        if self.member_id and not self.allocation_pct:
            self.allocation_pct = self.member_id.allocation_pct

    @api.onchange("budget_line_id")
    def _onchange_budget_line_id(self):
        if self.budget_line_id and self.budget_line_id.account_ids:
            self.account_id = self.budget_line_id.account_ids[:1]

    @api.constrains("account_id", "budget_line_id")
    def _check_account_allowed(self):
        for line in self:
            if (line.account_id and line.budget_line_id
                    and line.account_id not in line.budget_line_id.account_ids):
                raise ValidationError(_(
                    "Account '%(a)s' is not one of the accounts allowed on budget "
                    "line '%(b)s'.", a=line.account_id.display_name,
                    b=line.budget_line_id.display_name))
