from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class ArcsMultiDonorSharedCost(models.Model):
    """A cost that benefits more than one donor's portion of a shared
    project. The total is entered ONCE here; splitting generates one draft
    arcs.expense per member grant, each for exactly that member's share -
    never the full amount - so the classic multi-donor accounting mistake
    (the same cost charged in full to two different donors) is structurally
    impossible through this tool."""

    _name = "arcs.multi.donor.shared.cost"
    _description = "Multi-Donor Shared Cost"
    _inherit = ["mail.thread"]
    _order = "project_id, date desc"

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda s: _("New"))
    project_id = fields.Many2one(
        "arcs.multi.donor.project", required=True, tracking=True, ondelete="restrict",
        domain="[('state', '=', 'active')]")
    description = fields.Text()
    date = fields.Date(required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda s: s.env.company.currency_id.id)
    total_amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)

    split_line_ids = fields.One2many(
        "arcs.multi.donor.shared.cost.line", "shared_cost_id", string="Split Lines")
    split_total_pct = fields.Float(compute="_compute_split_totals")
    split_total_amount = fields.Monetary(
        compute="_compute_split_totals", currency_field="currency_id")
    all_expenses_posted = fields.Boolean(compute="_compute_split_totals")

    state = fields.Selection(
        [("draft", "Draft"), ("split", "Split"), ("posted", "Fully Posted"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "The reference must be unique."),
        ("total_amount_positive", "CHECK(total_amount > 0)",
         "The total amount must be greater than zero."),
    ]

    @api.depends("split_line_ids.allocation_pct", "split_line_ids.amount",
                "split_line_ids.expense_id.state")
    def _compute_split_totals(self):
        for c in self:
            c.split_total_pct = sum(c.split_line_ids.mapped("allocation_pct"))
            c.split_total_amount = sum(c.split_line_ids.mapped("amount"))
            lines_with_expense = c.split_line_ids.filtered("expense_id")
            c.all_expenses_posted = bool(c.split_line_ids) and len(
                lines_with_expense.filtered(lambda l: l.expense_id.state == "posted")
            ) == len(c.split_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "arcs.multi.donor.shared.cost") or _("New")
        return super().create(vals_list)

    def action_generate_default_split(self):
        """Fill in one split line per project member that doesn't already
        have one, defaulting to that member's project-level share. Budget
        line and account still need to be picked manually per line before
        the cost can actually be split."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a draft shared cost can generate split lines."))
        existing_members = self.split_line_ids.member_id
        to_create = []
        for member in self.project_id.member_ids.filtered(lambda m: m not in existing_members):
            to_create.append({
                "shared_cost_id": self.id, "member_id": member.id,
                "allocation_pct": member.allocation_pct,
            })
        if to_create:
            self.env["arcs.multi.donor.shared.cost.line"].create(to_create)

    def action_split(self):
        for c in self:
            if c.state != "draft":
                raise UserError(_("Only a draft shared cost can be split."))
            if not c.split_line_ids:
                raise UserError(_(
                    "Generate or add split lines before splitting this cost."))
            if float_compare(c.split_total_pct, 100.0, precision_digits=2) != 0:
                raise UserError(_(
                    "The split lines must add up to exactly 100%% (currently "
                    "%.2f%%).") % c.split_total_pct)
            if float_compare(c.split_total_amount, c.total_amount,
                             precision_rounding=c.currency_id.rounding) != 0:
                raise UserError(_(
                    "The split lines' amounts (%(s).2f) must add up to exactly "
                    "the Total Amount (%(t).2f).",
                    s=c.split_total_amount, t=c.total_amount))
            for line in c.split_line_ids:
                if not line.budget_line_id:
                    raise UserError(_(
                        "Every split line needs a Budget Line before splitting - "
                        "missing one for %s.") % line.grant_id.display_name)
                if not line.account_id:
                    raise UserError(_(
                        "Every split line needs an Account before splitting - "
                        "missing one for %s.") % line.grant_id.display_name)
        for c in self:
            for line in c.split_line_ids:
                expense = self.env["arcs.expense"].create({
                    "grant_id": line.grant_id.id, "budget_line_id": line.budget_line_id.id,
                    "account_id": line.account_id.id, "amount": line.amount, "date": c.date,
                    "shared_cost_id": c.id,
                })
                line.expense_id = expense.id
            c.state = "split"
        return True

    def action_mark_posted(self):
        for c in self:
            if c.state != "split":
                raise UserError(_("Only a split shared cost can be marked Fully Posted."))
            if not c.all_expenses_posted:
                raise UserError(_(
                    "Not every generated expense has been Posted yet - post each "
                    "one on its own grant first."))
        return self.write({"state": "posted"})

    def action_cancel(self):
        for c in self:
            if c.state != "draft":
                raise UserError(_(
                    "Only a draft shared cost can be cancelled - once split, the "
                    "generated expenses are real transactions on each grant and "
                    "must be handled there instead."))
        return self.write({"state": "cancelled"})
