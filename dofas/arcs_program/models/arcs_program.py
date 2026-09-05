import re
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class ArcsProgram(models.Model):
    _name = "arcs.program"
    _description = "Program"
    _inherit = ["mail.thread", "arcs.reason.action.mixin"]
    _order = "name"

    name = fields.Char(required=True, help="Program name, e.g. Health Program.")
    code = fields.Char(required=True, copy=False, index=True)
    manager_id = fields.Many2one("res.users", string="Program Manager")
    description = fields.Text()
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency")
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft", required=True, tracking=True, copy=False)
    project_ids = fields.One2many("arcs.project", "program_id", string="Projects")
    budget_line_id = fields.Many2one(
        "arcs.budget.line", string="Budget Line",
        domain="[('budget_state', '=', 'approved')]",
        help="Optional source budget line for this program's Planned Cost ceiling. "
             "Selecting one suggests Planned Cost from whatever the line still has "
             "left after every OTHER program already planning against it (converted "
             "to company currency) - and Planned Cost can never exceed that remaining "
             "amount, so several programs sharing one budget line can never together "
             "plan more than it actually has. This is the top of the cascade: a "
             "Project's Planned Cost can never exceed its Program's (net of sibling "
             "projects), and an Activity's can never exceed its Project's (net of "
             "sibling activities).")
    planned_cost = fields.Monetary(
        currency_field="currency_id",
        help="In company currency: a Program can span projects funded by different "
             "grants, potentially in different currencies, so this ceiling and its "
             "tracking are always expressed in company currency.")
    commitment_ids = fields.One2many("arcs.commitment", "program_id", string="Commitments")
    committed_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Sum of confirmed reserves against this program (converted to company "
             "currency) - created when an acquisition linked to one of its activities "
             "is committed (Program/Project/Activity ceiling enforcement must be on in "
             "ARCS Settings for this to ever block anything).")
    actual_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Sum of posted expenses linked to this program, in company currency.")
    available_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Planned Cost − Committed − Actual, in company currency.")

    _sql_constraints = [("code_uniq", "unique(code, company_id)",
                         "The Program Code must be unique per company.")]

    @api.onchange("code")
    def _onchange_code_upper(self):
        if self.code:
            self.code = self.code.strip().upper()

    @api.onchange("budget_line_id")
    def _onchange_budget_line_id(self):
        if self.budget_line_id:
            self.planned_cost = max(
                self._budget_line_remaining_for_planning(self.budget_line_id), 0.0)

    def _to_company_currency(self, amount, currency):
        """Shared conversion used everywhere this model compares or derives a
        company-currency amount from a source in another currency (a budget
        line's own currency, or a child project's grant currency) - one
        implementation instead of the same three lines repeated three times."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if currency and company.currency_id and currency != company.currency_id:
            return currency._convert(amount, company.currency_id, company,
                                     fields.Date.context_today(self))
        return amount

    def _budget_line_remaining_for_planning(self, budget_line):
        """How much of `budget_line`'s Available Amount (converted to company
        currency) is still unclaimed by OTHER programs already planning
        against it. This - not the budget line's raw Available Amount - is
        the real ceiling THIS program's own Planned Cost must respect: if
        the line has 20,000 and one program already plans 10,000, only
        10,000 remains for every other program planning against that same
        line.

        Excludes this program's OWN prior claim (via `self._origin`, so
        this is safe to call from an onchange on an unsaved record too) -
        editing a program's own Planned Cost isn't competing against its
        own existing figure, only against everyone else's.

        Does not row-lock the budget line: Planned Cost is a softer,
        planning-stage ceiling, not a real money reservation - the actual
        financial reservation (arcs.commitment, via budget_line.reserve())
        already row-locks correctly and is completely unaffected by this
        check either way."""
        self.ensure_one()
        if not budget_line:
            return 0.0
        available = self._to_company_currency(
            budget_line.available_amount, budget_line.currency_id)
        domain = [("budget_line_id", "=", budget_line.id)]
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        others = self.env["arcs.program"].search(domain)
        others_planned = sum(
            self._to_company_currency(o.planned_cost, o.currency_id) for o in others)
        return available - others_planned

    @api.constrains("code")
    def _check_code_format(self):
        for r in self.filtered("code"):
            if not CODE_RE.match(r.code.strip()):
                raise ValidationError(_(
                    "Invalid program code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit. Example: HEALTH or HEALTH-2026.",
                    code=r.code))

    @api.constrains("planned_cost", "budget_line_id")
    def _check_planned_within_budget_line(self):
        for p in self.filtered("budget_line_id"):
            remaining = p._budget_line_remaining_for_planning(p.budget_line_id)
            if float_compare(p.planned_cost, remaining,
                             precision_rounding=p.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Planned Cost (%(pc).2f %(cur)s) exceeds what's still available "
                    "on budget line '%(line)s' once other programs' own Planned Cost "
                    "is taken into account: %(remaining).2f %(cur)s remains for this "
                    "one to plan against.") % {
                    "pc": p.planned_cost, "cur": p.currency_id.name or "",
                    "line": p.budget_line_id.name, "remaining": remaining})

    @api.constrains("planned_cost")
    def _check_children_still_fit(self):
        for p in self:
            total_children = sum(
                p._to_company_currency(proj.planned_cost, proj.currency_id)
                for proj in p.project_ids)
            if float_compare(total_children, p.planned_cost,
                             precision_rounding=p.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Cannot set this Program's Planned Cost to %(new).2f %(cur)s - "
                    "its projects already total %(total).2f %(cur)s planned between "
                    "them. Reduce the project(s) first.") % {
                    "new": p.planned_cost, "cur": p.currency_id.name or "",
                    "total": total_children})

    @api.depends("planned_cost", "commitment_ids.amount", "commitment_ids.state",
                "commitment_ids.currency_id")
    def _compute_amounts(self):
        Expense = self.env["arcs.expense"]
        for p in self:
            committed = sum(
                p._to_company_currency(c.amount, c.currency_id)
                for c in p.commitment_ids.filtered(lambda c: c.state == "confirmed")
            )
            expenses = Expense.search([
                ("project_id.program_id", "=", p.id), ("state", "=", "posted"),
            ])
            actual = sum(p._to_company_currency(e.amount, e.currency_id) for e in expenses)
            p.committed_amount = committed
            p.actual_amount = actual
            p.available_amount = p.planned_cost - committed - actual

    def get_available_locked(self):
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM arcs_program WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset(["committed_amount", "actual_amount", "available_amount"])
        return self.available_amount

    def action_activate(self):
        for p in self:
            if p.state != "draft":
                raise UserError(_("Only draft programs can be activated."))
        self.write({"state": "active"})

    def action_close(self):
        blocked = self.browse()
        for p in self:
            if p.state != "active":
                raise UserError(_("Only active programs can be closed."))
            if p.project_ids.filtered(lambda x: x.state != "closed"):
                blocked = p
                break
        if blocked:
            return blocked._open_close_wizard()
        self.write({"state": "closed"})

    def _open_close_wizard(self):
        self.ensure_one()
        blockers = self.project_ids.filtered(lambda x: x.state != "closed")
        wiz = self.env["arcs.lifecycle.close.wizard"].create({
            "res_model": self._name,
            "res_id": self.id,
            "record_name": self.display_name,
            "child_label": _("projects"),
            "blocker_count": len(blockers),
            "blockers": "\n".join("• %s" % n for n in blockers.mapped("display_name")),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Cannot close yet"),
            "res_model": "arcs.lifecycle.close.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def _force_close(self):
        for prog in self:
            for proj in prog.project_ids.filtered(lambda x: x.state != "closed"):
                proj.activity_ids.filtered(lambda a: a.state != "closed").write({"state": "closed"})
                proj.write({"state": "closed"})
            prog.write({"state": "closed"})

    def action_reset_draft(self, reason=False):
        self.write({"state": "draft"})
        if reason:
            self.message_post(body=_("Reason: %s") % reason)
