from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

import re

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class ArcsActivity(models.Model):
    _name = "arcs.activity"
    _description = "Activity"
    _inherit = ["arcs.approval.mixin", "mail.thread"]
    _order = "date_start, id"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(copy=False, index=True)
    project_id = fields.Many2one("arcs.project", required=True, ondelete="cascade", index=True)
    component_id = fields.Many2one("arcs.project.component", string="Component",
                                   domain="[('project_id','=',project_id)]")
    grant_id = fields.Many2one(related="project_id.grant_id", store=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="grant_id.currency_id", store=True)
    budget_line_id = fields.Many2one(
        "arcs.budget.line", string="Budget Line",
        domain="[('grant_id','=',grant_id), ('budget_state','=','approved')]")
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    planned_cost = fields.Monetary(currency_field="currency_id")
    commitment_ids = fields.One2many("arcs.commitment", "activity_id", string="Commitments")
    committed_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Sum of confirmed reserves against this activity - created when an "
             "acquisition linked to it is committed (Program/Project/Activity ceiling "
             "enforcement must be on in ARCS Settings for this to ever block anything).")
    actual_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Sum of posted expenses linked to this activity.")
    available_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id",
        help="Planned Cost − Committed − Actual.")
    expected_outputs = fields.Text()
    expected_beneficiaries = fields.Integer()
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"),
         ("implemented", "Implemented"), ("closed", "Closed")],
        default="draft", required=True, tracking=True, copy=False)

    @api.constrains("date_start", "date_end", "project_id")
    def _check_dates(self):
        for a in self:
            if a.date_start and a.date_end and a.date_start > a.date_end:
                raise ValidationError(_("Activity start date cannot be later than its end date."))
            p = a.project_id
            if p.date_start and p.date_end and a.date_start and a.date_end:
                if a.date_start < p.date_start or a.date_end > p.date_end:
                    raise ValidationError(_(
                        "Activity dates must fall within the project period (%(s)s to %(e)s).",
                        s=p.date_start, e=p.date_end))

    @api.constrains("planned_cost", "budget_line_id")
    def _check_planned_within_budget(self):
        for a in self.filtered("budget_line_id"):
            if float_compare(a.planned_cost, a.budget_line_id.available_amount,
                             precision_rounding=a.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Planned cost exceeds the available budget on line '%s'.",
                    a.budget_line_id.name))

    @api.constrains("planned_cost", "project_id")
    def _check_planned_within_project(self):
        for a in self.filtered("project_id"):
            project = a.project_id
            if float_compare(a.planned_cost, project.planned_cost,
                             precision_rounding=a.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Planned cost exceeds Project '%s''s own Planned Cost.",
                    project.name))

    @api.depends("planned_cost", "commitment_ids.amount", "commitment_ids.state")
    def _compute_amounts(self):
        Expense = self.env["arcs.expense"]
        for a in self:
            committed = sum(a.commitment_ids.filtered(
                lambda c: c.state == "confirmed").mapped("amount"))
            actual = sum(Expense.search([
                ("activity_id", "=", a.id), ("state", "=", "posted"),
            ]).mapped("amount"))
            a.committed_amount = committed
            a.actual_amount = actual
            a.available_amount = a.planned_cost - committed - actual

    def get_available_locked(self):
        """Row-locks this activity and returns a freshly recomputed Available,
        mirroring arcs.budget.line.get_available_locked() exactly - same
        concurrency-safe pattern, same reasoning: two acquisitions committing
        against the same activity at once must be serialised, not race."""
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM arcs_activity WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset(["committed_amount", "actual_amount", "available_amount"])
        return self.available_amount

    @api.onchange("code")
    def _onchange_code_upper(self):
        if self.code:
            self.code = self.code.strip().upper()

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if self.project_id and not self.planned_cost:
            self.planned_cost = self.project_id.planned_cost

    @api.constrains("code")
    def _check_code_format(self):
        for a in self.filtered("code"):
            if not CODE_RE.match(a.code.strip()):
                raise ValidationError(_(
                    "Invalid activity code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit.", code=a.code))

    @api.constrains("planned_cost", "expected_beneficiaries")
    def _check_non_negative(self):
        for a in self:
            if a.planned_cost < 0:
                raise ValidationError(_("Planned cost cannot be negative."))
            if a.expected_beneficiaries < 0:
                raise ValidationError(_("Expected beneficiaries cannot be negative."))

    def action_submit(self):
        return self._transition("submitted", "submit")

    def action_approve(self):
        for a in self:
            if a.state != "submitted":
                raise UserError(_("Only submitted activities can be approved."))
        return self._transition("approved", "approve")

    def action_implement(self):
        for a in self:
            if a.state != "approved":
                raise UserError(_("Only approved activities can be implemented."))
        return self._transition("implemented", "implement")

    def action_close(self):
        return self._transition("closed", "close")
