from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ArcsFundReceiptAllocation(models.Model):
    """One row of a Fund Receipt's Program Allocation breakdown - a
    read-only, auto-generated snapshot of the Program -> Project ->
    Activity plan already entered under the receipt's Grant (see
    arcs.fund.receipt._build_allocation_vals / action_refresh_program_
    allocation), not something typed in by hand. Every Program related to
    the grant gets its own row, immediately followed by each of its
    Projects under that grant, immediately followed by each of THEIR
    Activities - `sequence` preserves that nesting order and `level` is
    what the view/report/email use to indent each row under its parent.

    `amount` is that specific record's own Planned Cost, exactly as shown
    everywhere else in the suite - NOT a mutually-exclusive split of the
    receipt's cash. A Program's own figure already includes its Projects',
    which already include their Activities' - by design, this is a nested
    breakdown for donor transparency ("here is our spending plan and
    exactly how your contribution fits into it"), not a partition of this
    one receipt's amount, so the rows are never expected to sum to the
    receipt total."""

    _name = "arcs.fund.receipt.allocation"
    _description = "Fund Receipt Program Allocation"
    _order = "sequence, id"

    fund_receipt_id = fields.Many2one(
        "arcs.fund.receipt", string="Fund Receipt", required=True,
        ondelete="cascade", index=True)
    receipt_state = fields.Selection(related="fund_receipt_id.state", store=True)
    grant_id = fields.Many2one(related="fund_receipt_id.grant_id", store=True)
    company_id = fields.Many2one(related="fund_receipt_id.company_id", store=True)
    currency_id = fields.Many2one(related="fund_receipt_id.currency_id", store=True)

    sequence = fields.Integer(default=10)
    level = fields.Selection(
        [("program", "Program"), ("project", "Project"), ("activity", "Activity")],
        required=True,
        help="Which level of the Program -> Project -> Activity hierarchy this row "
             "represents - drives the indentation shown on the receipt, the printed "
             "letter, and the acknowledgement email.")
    program_id = fields.Many2one(
        "arcs.program", string="Program", required=True,
        domain="['|', ('project_ids.grant_id', '=', grant_id), "
               "('budget_line_id.grant_id', '=', grant_id)]",
        help="Set on every row - even a Project or Activity row carries its parent "
             "Program, so the whole hierarchy can be grouped/indented correctly. "
             "Scoped to Programs actually related to this receipt's Grant, the same "
             "rule the auto-generator itself uses.")
    project_id = fields.Many2one(
        "arcs.project", string="Project",
        domain="[('program_id', '=', program_id), ('grant_id', '=', grant_id)]",
        help="Set for a Project or Activity row; blank for a Program-level row.")
    activity_id = fields.Many2one(
        "arcs.activity", string="Activity",
        domain="[('project_id', '=', project_id)]",
        help="Set only for an Activity-level row.")
    name = fields.Char(
        string="Name", compute="_compute_name",
        help="Indented display label for this row - the Program/Project/Activity's "
             "own name, shown nested under its parent.")
    amount = fields.Monetary(
        string="Planned Cost", currency_field="currency_id",
        help="This row's own Planned Cost, auto-filled from the Program/Project/"
             "Activity it represents. Refresh the allocation (from the Fund Receipt) "
             "if the underlying plan has changed since this was generated.")

    @api.depends("level", "program_id", "project_id", "activity_id",
                "program_id.name", "project_id.name", "activity_id.name")
    def _compute_name(self):
        # Non-breaking spaces (not plain ones) so the indentation actually
        # survives standard HTML whitespace collapsing in the web list view.
        for line in self:
            if line.level == "program":
                line.name = line.program_id.display_name or ""
            elif line.level == "project":
                line.name = "\xa0\xa0\xa0\xa0\u21b3 %s" % (line.project_id.display_name or "")
            elif line.level == "activity":
                line.name = "\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0\u21b3 %s" % (
                    line.activity_id.display_name or "")
            else:
                line.name = ""

    # ---------------- manual add/remove: keep level & amount in sync ----------------
    # These give a line added or edited by hand the exact same "auto-picked
    # amount" behaviour the bulk generator already applies - level and
    # amount always reflect whichever of program_id/project_id/activity_id
    # is currently the deepest one set, so a manually re-added row is
    # indistinguishable from one the generator would have produced itself.
    @api.onchange("program_id")
    def _onchange_program_id(self):
        if self.program_id:
            if not self.project_id:
                self.level = "program"
                self.amount = self.program_id.planned_cost
        else:
            self.project_id = False
            self.activity_id = False

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if self.project_id:
            self.level = "project"
            self.amount = self.project_id.planned_cost
            if self.activity_id and self.activity_id.project_id != self.project_id:
                self.activity_id = False
        elif self.program_id:
            self.level = "program"
            self.amount = self.program_id.planned_cost
            self.activity_id = False

    @api.onchange("activity_id")
    def _onchange_activity_id(self):
        if self.activity_id:
            self.level = "activity"
            self.amount = self.activity_id.planned_cost
        elif self.project_id:
            self.level = "project"
            self.amount = self.project_id.planned_cost
        elif self.program_id:
            self.level = "program"
            self.amount = self.program_id.planned_cost

    @api.constrains("project_id", "program_id", "grant_id")
    def _check_project_matches_program_and_grant(self):
        for line in self:
            if line.project_id and line.project_id.program_id != line.program_id:
                raise ValidationError(_(
                    "Project '%(project)s' does not belong to Program '%(program)s'.",
                    project=line.project_id.display_name, program=line.program_id.display_name))
            if line.project_id and line.grant_id and line.project_id.grant_id != line.grant_id:
                raise ValidationError(_(
                    "Project '%(project)s' belongs to a different Grant than this "
                    "receipt (%(grant)s).", project=line.project_id.display_name,
                    grant=line.grant_id.display_name))

    @api.constrains("activity_id", "project_id")
    def _check_activity_matches_project(self):
        for line in self:
            if line.activity_id and line.activity_id.project_id != line.project_id:
                raise ValidationError(_(
                    "Activity '%(activity)s' does not belong to Project '%(project)s'.",
                    activity=line.activity_id.display_name,
                    project=line.project_id.display_name if line.project_id else _("(none)")))
