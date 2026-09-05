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

    @api.constrains("planned_cost", "project_id")
    def _check_planned_within_project(self):
        for a in self.filtered("project_id"):
            project = a.project_id
            remaining = a._project_remaining_for_planning(project)
            if float_compare(a.planned_cost, remaining,
                             precision_rounding=a.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Planned cost exceeds what's still available under Project "
                    "'%(proj)s' once other activities' own Planned Cost is taken "
                    "into account: %(remaining).2f %(cur)s remains for this one to "
                    "plan against.") % {
                    "proj": project.name, "remaining": remaining,
                    "cur": a.currency_id.name or ""})

    def _project_remaining_for_planning(self, project):
        """How much of `project`'s own Planned Cost is still unclaimed by
        OTHER activities already planned under it - mirrors
        arcs.project._program_remaining_for_planning() one level down, same
        reasoning: several activities sharing one project can never
        together plan more than the project actually has. Activity and
        Project always share the same currency (both derive from the same
        grant), so no conversion is needed here.

        Excludes this activity's OWN prior claim (via `self._origin`, safe
        to call from an onchange on an unsaved record too)."""
        self.ensure_one()
        if not project:
            return 0.0
        domain = [("project_id", "=", project.id)]
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        others = self.env["arcs.activity"].search(domain)
        others_planned = sum(others.mapped("planned_cost"))
        return project.planned_cost - others_planned

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
            self.planned_cost = max(
                self._project_remaining_for_planning(self.project_id), 0.0)

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
