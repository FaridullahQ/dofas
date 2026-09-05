from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare
import logging

_logger = logging.getLogger(__name__)


class ArcsSpendRequest(models.Model):
    _name = "arcs.spend.request"
    _description = "Acquisition (Four Form)"
    _inherit = ["arcs.approval.mixin", "arcs.voucher.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "date_request desc, id desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False, readonly=True)
    date_request = fields.Date(default=fields.Date.context_today, tracking=True)
    region_id = fields.Many2one(
        "arcs.zone", string="Region", tracking=True,
        domain="[('kind', '=', 'zone')]",
        help="The region this acquisition is filed under. Auto-filled, together with "
             "Province, Department, Department Manager and Budget Holder, from the "
             "requested employee's own HR department once 'Requested By' is set - "
             "still fully editable afterwards, and narrows the Province choice below "
             "once picked (either automatically or by hand).")
    zone_id = fields.Many2one(
        "arcs.zone", string="Province", tracking=True,
        domain="[('kind', '=', 'province')] + ([('parent_id', '=', region_id)] if region_id else [])",
        help="The province this acquisition is filed under.")
    department_id = fields.Many2one(
        "hr.department", string="Department",
        domain="[('zone_id', '=', zone_id)] if zone_id else []",
        help="Narrowed to the departments of the selected Province once one is chosen.")
    department_manager_id = fields.Many2one(
        "hr.employee", string="Department Manager",
        help="Auto-filled from the requested employee's department manager once "
             "'Requested By' is set; editable if a different approver applies to "
             "this particular acquisition.")
    budget_line_id = fields.Many2one(
        "arcs.budget.line", string="Budget Line", required=True, tracking=True,
        domain="[('budget_state', '=', 'approved')]",
        help="Only budget lines on an Approved budget version are selectable - "
             "a Draft version isn't active yet and a Superseded one is historical.")
    grant_id = fields.Many2one("arcs.grant", related="budget_line_id.grant_id", store=True)
    program_id = fields.Many2one(
        "arcs.program", string="Program", tracking=True,
        help="Pick a program first to narrow the Project choices below.")
    program_currency_id = fields.Many2one(related="program_id.currency_id", readonly=True)
    program_planned_cost = fields.Monetary(
        related="program_id.planned_cost", currency_field="program_currency_id", readonly=True,
        help="In company currency - see the Program record.")
    program_available_amount = fields.Monetary(
        related="program_id.available_amount", currency_field="program_currency_id", readonly=True)
    project_id = fields.Many2one(
        "arcs.project", string="Project",
        domain="([('grant_id','=',grant_id)] if grant_id else []) + ([('program_id','=',program_id)] if program_id else [])")
    project_planned_cost = fields.Monetary(
        related="project_id.planned_cost", currency_field="currency_id", readonly=True)
    project_available_amount = fields.Monetary(
        related="project_id.available_amount", currency_field="currency_id", readonly=True)
    activity_id = fields.Many2one(
        "arcs.activity", string="Activity",
        domain="[('project_id','=',project_id)] if project_id else []")
    activity_planned_cost = fields.Monetary(
        related="activity_id.planned_cost", currency_field="currency_id", readonly=True)
    activity_available_amount = fields.Monetary(
        related="activity_id.available_amount", currency_field="currency_id", readonly=True)
    company_id = fields.Many2one(related="budget_line_id.company_id", store=True)
    currency_id = fields.Many2one(related="budget_line_id.currency_id", store=True)
    budget_holder_id = fields.Many2one("res.users", string="Budget Holder", tracking=True)
    requested_by = fields.Many2one(
        "hr.employee", string="Requested By",
        default=lambda s: s.env.user.employee_id,
        help="The employee this acquisition is filed for. Once set, auto-fills Region, "
             "Province, Department, Department Manager and Budget Holder from this "
             "employee's own HR department (still fully editable afterwards). Once "
             "Approved, this is also who the approved amount is disbursed to as a cash "
             "advance (see the Employee Advance section) - they spend it, and any "
             "difference between what they spent and what they were given is settled "
             "with them afterwards.")
    requested_by_employee_code = fields.Char(
        related="requested_by.employee_code", string="Employee Code", readonly=True,
        help="The selected employee's unique ARCS identifier - confirms exactly which "
             "person this acquisition (and its eventual cash advance) is for when "
             "several employees share the same name.")
    line_ids = fields.One2many("arcs.spend.request.line", "request_id", string="Items")
    estimated_amount = fields.Monetary(compute="_compute_estimated", store=True,
                                       currency_field="currency_id")
    approved_amount = fields.Monetary(
        string="Approved (Quotation) Amount", currency_field="currency_id",
        copy=False, readonly=True, tracking=True,
        help="Real amount confirmed against approved supplier quotations. "
             "Required (via 'Confirm Real Price') before Commit & Reserve becomes "
             "available; this is what gets reserved on the budget line and drives "
             "the eventual journal entries instead of the estimated amount.")
    quotation_ref = fields.Char(
        string="Quotation Reference", copy=False, readonly=True, tracking=True,
        help="Reference number of the approved supplier quotation(s) used to "
             "confirm the real price.")
    vendor_id = fields.Many2one(
        "res.partner", string="Vendor", copy=False, readonly=True, tracking=True,
        help="Vendor whose quotation the real price was confirmed against.")
    available_on_line = fields.Monetary(compute="_compute_available", currency_field="currency_id")
    commitment_id = fields.Many2one(
        "arcs.commitment", string="Primary Reserve", readonly=True, copy=False,
        help="Reserve on the primary Budget Line above. When the approved amount was "
             "split across several budget lines (see 'Budget Reserves' tab), this holds "
             "the portion reserved on this primary line - the rest is in commitment_ids.")
    commitment_ids = fields.One2many(
        "arcs.commitment", "spend_request_id", string="Budget Reserves", copy=False,
        help="Every reserve tied to this acquisition. Normally a single row on the "
             "primary Budget Line; when Finance splits the shortfall across other "
             "budget lines, one row per line used, each tracked and released separately.")
    commitment_count = fields.Integer(compute="_compute_commitment_count")
    is_split_reserve = fields.Boolean(
        compute="_compute_is_split_reserve",
        help="True once the approved amount was reserved across more than one budget line.")
    expense_ids = fields.One2many("arcs.expense", "request_id", string="Expenses")
    advance_id = fields.Many2one(
        "arcs.advance", string="Employee Advance", readonly=True, copy=False,
        help="The cash advance disbursed to Requested By once this acquisition is "
             "Approved, for the Approved (Quotation) Amount. They spend against it; "
             "once their actual expenses are posted and justified via a liquidation, "
             "any difference is settled with them - paid back if they spent less, "
             "reimbursed if they spent more.")
    advance_state = fields.Selection(related="advance_id.state", string="Advance Status")
    advance_outstanding_amount = fields.Monetary(
        related="advance_id.outstanding_amount", string="Advance Outstanding",
        currency_field="currency_id")
    advance_liquidation_ids = fields.One2many(
        related="advance_id.liquidation_ids", string="Advance Liquidations")
    expense_count = fields.Integer(compute="_compute_expense_count")
    budget_transfer_ids = fields.One2many(
        "arcs.budget.transfer", "spend_request_id", string="Internal Budget Transfers")
    budget_transfer_count = fields.Integer(compute="_compute_budget_transfer_count")
    donor_funding_ids = fields.One2many(
        "arcs.donor.funding.request", "spend_request_id", string="Donor Funding Requests")
    donor_funding_count = fields.Integer(compute="_compute_donor_funding_count")
    state = fields.Selection(
        [("draft", "Drafted"), ("submitted", "Submitted"),
         ("insufficient_funds", "Insufficient Funds"), ("committed", "Committed"),
         ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)
    shortfall_amount = fields.Monetary(
        string="Shortfall", currency_field="currency_id", readonly=True, copy=False,
        help="How much the requested amount exceeded the budget line's (or, for an "
             "activity shortfall, the Activity/Project/Program's) live available balance.")
    insufficient_funds_note = fields.Char(readonly=True, copy=False)
    shortfall_type = fields.Selection(
        [("budget_line", "Budget Line"), ("activity", "Activity")],
        default="budget_line", readonly=True, copy=False,
        help="Which axis was short when this request was flagged Insufficient Funds - "
             "determines which recovery options are offered: Budget Line shortfalls get "
             "Choose Different Budget Line / Split Across Budget Lines / Internal "
             "Transfer / Donor Funding; Activity shortfalls get Choose Different "
             "Activity / Split Across Activities / Revise.")
    note = fields.Text()

    @api.depends("line_ids.amount")
    def _compute_estimated(self):
        for r in self:
            r.estimated_amount = sum(r.line_ids.mapped("amount"))

    def _compute_available(self):
        for r in self:
            r.available_on_line = r.budget_line_id.available_amount if r.budget_line_id else 0.0

    def _active_commitments(self):
        """Reserves still economically live for this request: confirmed
        (reserved, not yet spent) or consumed (an approved expense drawn from
        this reserve has posted). Excludes released rows kept only for
        historical audit trail after a reject/cancel/revise cycle."""
        self.ensure_one()
        return self.commitment_ids.filtered(lambda c: c.state in ("confirmed", "consumed"))

    @api.depends("commitment_ids.state")
    def _compute_commitment_count(self):
        for r in self:
            r.commitment_count = len(r._active_commitments())

    @api.depends("commitment_ids.state", "commitment_ids.budget_line_id")
    def _compute_is_split_reserve(self):
        for r in self:
            r.is_split_reserve = len(r._active_commitments().mapped("budget_line_id")) > 1

    def _compute_expense_count(self):
        for r in self:
            r.expense_count = len(r.expense_ids)

    def _compute_budget_transfer_count(self):
        for r in self:
            r.budget_transfer_count = len(r.budget_transfer_ids)

    def _compute_donor_funding_count(self):
        for r in self:
            r.donor_funding_count = len(r.donor_funding_ids)

    @api.onchange("requested_by")
    def _onchange_requested_by(self):
        """Entry point requested by the client: pick the requesting employee
        and every relevant requesting-unit field - Region, Province,
        Department, Department Manager and Budget Holder - fills in from
        that employee's own HR department, mirroring the established
        Activity -> Project -> Program -> Budget Line cascade below (every
        field it touches is set directly here, rather than relying on the
        other onchange methods to fire and re-derive it, exactly like
        _onchange_activity does for the budget line). Every field stays
        fully editable afterwards - this is an auto-fill convenience, not a
        lock, and it only ever fills in blanks / replaces a PREVIOUS
        auto-fill, never overwrites unrelated user input on an employee
        with no department."""
        if not self.requested_by:
            return
        department = self.requested_by.department_id
        if not department:
            return
        self.department_id = department
        province = department.zone_id
        if province:
            self.zone_id = province
            self.region_id = province.parent_id
            if province.budget_holder_id:
                self.budget_holder_id = province.budget_holder_id
        if department.manager_id:
            self.department_manager_id = department.manager_id

    @api.onchange("region_id")
    def _onchange_region(self):
        """Only clears Province when it's become genuinely inconsistent with
        the new Region - not unconditionally, so a Region auto-filled BY the
        Requested By cascade above (always the matching parent, by
        construction) never wipes the very Province selection that produced
        it, mirroring _onchange_budget_line's guard below."""
        if self.zone_id and self.zone_id.parent_id != self.region_id:
            self.zone_id = False

    @api.onchange("zone_id")
    def _onchange_zone(self):
        if self.zone_id:
            if self.zone_id.budget_holder_id:
                self.budget_holder_id = self.zone_id.budget_holder_id
            if not self.region_id:
                self.region_id = self.zone_id.parent_id
        if self.department_id and self.department_id.zone_id and self.zone_id and \
                self.department_id.zone_id != self.zone_id:
            self.department_id = False

    @api.onchange("program_id")
    def _onchange_program(self):
        if self.program_id and self.project_id and self.project_id.program_id != self.program_id:
            self.project_id = False
            self.activity_id = False
        if self.program_id and not self.budget_line_id and self.program_id.budget_line_id:
            self.budget_line_id = self.program_id.budget_line_id

    @api.onchange("project_id")
    def _onchange_project(self):
        if self.activity_id and self.activity_id.project_id != self.project_id:
            self.activity_id = False
        if self.project_id and self.project_id.program_id and not self.program_id:
            self.program_id = self.project_id.program_id
        if self.project_id and not self.budget_line_id:
            program = self.project_id.program_id
            if program and program.budget_line_id \
                    and program.budget_line_id.grant_id == self.project_id.grant_id:
                self.budget_line_id = program.budget_line_id

    @api.onchange("activity_id")
    def _onchange_activity(self):
        """The entry point the client asked for: pick an Activity and every
        relevant upstream field - Project, Program, and (best-effort) Budget
        Line - fills in from it, instead of having to pick Budget Line first
        and work down. Falls back to the Activity's own Program's budget
        line (arcs_program's single source of truth for where a budget line
        enters the Program -> Project -> Activity cascade - an Activity has
        no direct budget_line_id of its own), but only when that line is
        confirmed to belong to the SAME grant as the project/activity -
        filling in a budget line from a different grant would immediately
        get wiped by _onchange_budget_line's own mismatch guard below, so
        it's safer to leave it for the user to pick manually in that edge
        case than to fill in something that can't stick."""
        if not self.activity_id:
            return
        activity = self.activity_id
        project = activity.project_id
        if self.project_id != project:
            self.project_id = project
        if project.program_id and self.program_id != project.program_id:
            self.program_id = project.program_id
        if not self.budget_line_id:
            if project.program_id and project.program_id.budget_line_id \
                    and project.program_id.budget_line_id.grant_id == project.grant_id:
                self.budget_line_id = project.program_id.budget_line_id

    @api.onchange("budget_line_id")
    def _onchange_budget_line(self):
        """Only clears Project/Activity when they've become genuinely
        inconsistent with the new Budget Line's grant - not unconditionally,
        so a Budget Line auto-filled BY the Activity/Project/Program cascade
        above (always the same grant, by construction) never wipes the very
        selections that produced it."""
        if self.project_id and self.project_id.grant_id != self.grant_id:
            self.project_id = False
            self.activity_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("arcs.spend.request") or _("New")
        return super().create(vals_list)

    # ---------------- four-step workflow ----------------
    def action_submit(self):
        """Override to check activity available amount before submission."""
        finance_or_admin = self.env.user.has_group("arcs_base.group_finance_manager") \
                           or self.env.user.has_group("arcs_base.group_system_admin")

        for r in self:
            if r.state != "draft":
                raise UserError(_("Only drafted requests can be submitted."))
            if not r.line_ids:
                raise UserError(_("Add at least one item before submitting."))
            if r.budget_holder_id and r.budget_holder_id != self.env.user and not finance_or_admin:
                raise UserError(_(
                    "Only the assigned Budget Holder (%s) can submit this acquisition "
                    "for finance review.") % r.budget_holder_id.name)

            # Check for activity shortfall BEFORE submission
            if r.activity_id and r.activity_available_amount < r.estimated_amount:
                return self._open_activity_warning_wizard(r)

        return self._transition("submitted", "submit")

    def _open_activity_warning_wizard(self, request):
        """Open the warning wizard for insufficient activity funds."""
        _logger.info(f"Opening activity warning wizard for request {request.name}")

        wizard = self.env["arcs.spend.request.activity.warning.wizard"].create({
            "request_id": request.id,
            "activity_available_amount": request.activity_available_amount,
            "estimated_amount": request.estimated_amount,
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Activity Insufficient Funds"),
            "res_model": "arcs.spend.request.activity.warning.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_request_id": request.id,
            },
        }

    def action_force_submit_ignore_activity(self):
        """Force submit even if activity has insufficient funds."""
        _logger.info(f"action_force_submit_ignore_activity called for {self.name}")

        finance_or_admin = self.env.user.has_group("arcs_base.group_finance_manager") \
                           or self.env.user.has_group("arcs_base.group_system_admin")

        for r in self:
            _logger.info(f"Processing request {r.name}, state: {r.state}")
            if r.state != "draft":
                raise UserError(_("Only drafted requests can be submitted."))
            if not r.line_ids:
                raise UserError(_("Add at least one item before submitting."))
            if r.budget_holder_id and r.budget_holder_id != self.env.user and not finance_or_admin:
                raise UserError(_(
                    "Only the assigned Budget Holder (%s) can submit this acquisition "
                    "for finance review.") % r.budget_holder_id.name)

        result = self._transition("submitted", "submit")
        _logger.info(f"Transition completed, new state: {self.state}")
        return result

    def action_commit(self):
        for r in self:
            if r.state != "submitted":
                raise UserError(_("Only submitted requests can be committed."))
            if r.commitment_id:
                raise UserError(_("This request already has a reserve."))
            if not r.approved_amount:
                raise UserError(_(
                    "Confirm the real price against a supplier quotation first "
                    "('Confirm Real Price') before committing and reserving budget."))
            reserve_amount = r.approved_amount
            if reserve_amount <= 0:
                raise UserError(_("The amount to reserve must be greater than zero."))
            available = r.budget_line_id.get_available_locked()
            rounding = r.currency_id.rounding
            if float_compare(reserve_amount, available, precision_rounding=rounding) > 0:
                shortfall = reserve_amount - available
                r.write({
                    "shortfall_amount": shortfall,
                    "shortfall_type": "budget_line",
                    "insufficient_funds_note": _(
                        "Available %(a).2f %(c)s, requested %(r).2f %(c)s on '%(l)s'.") % {
                                                   "a": available, "r": reserve_amount, "c": r.currency_id.name or "",
                                                   "l": r.budget_line_id.name},
                })
                r._transition("insufficient_funds", "insufficient_funds", comment=_(
                    "Insufficient budget: short by %(s).2f %(c)s on '%(l)s'.") % {
                                                                                      "s": shortfall,
                                                                                      "c": r.currency_id.name or "",
                                                                                      "l": r.budget_line_id.name})
                continue

            # Budget line has room. If this acquisition is tied to an Activity
            # and the company has Program/Project/Activity ceiling enforcement
            # on, that second, independent axis must have room too before we
            # commit anything - checked here, BEFORE the budget-line reserve
            # is created, so a failure here never leaves an orphaned reserve
            # behind (nothing to roll back, because nothing was created yet).
            activity_shortfall = r._check_activity_availability(reserve_amount) \
                if r.activity_id else False
            if activity_shortfall:
                level_name, level_available = activity_shortfall
                shortfall = reserve_amount - level_available
                r.write({
                    "shortfall_amount": shortfall,
                    "shortfall_type": "activity",
                    "insufficient_funds_note": _(
                        "Available %(a).2f %(c)s, requested %(r).2f %(c)s on %(lvl)s.") % {
                                                   "a": level_available, "r": reserve_amount,
                                                   "c": r.currency_id.name or "",
                                                   "lvl": level_name},
                })
                r._transition("insufficient_funds", "insufficient_funds", comment=_(
                    "Insufficient Planned Cost: short by %(s).2f %(c)s on %(lvl)s.") % {
                                                                                      "s": shortfall,
                                                                                      "c": r.currency_id.name or "",
                                                                                      "lvl": level_name})
                continue

            extra_vals = {"spend_request_id": r.id}
            if r.activity_id:
                extra_vals.update({
                    "activity_id": r.activity_id.id,
                    "project_id": r.project_id.id,
                    "program_id": r.program_id.id,
                })
            commitment = r.budget_line_id.reserve(
                reserve_amount, source_ref="%s,%s" % (r._name, r.id), **extra_vals)
            r.commitment_id = commitment.id
            r._transition("committed", "commit", comment=_(
                "Reserved %(amount).2f %(currency)s (quoted, ref %(ref)s) on '%(line)s'") % {
                                                             "amount": reserve_amount,
                                                             "currency": r.currency_id.name or "",
                                                             "ref": r.quotation_ref or "",
                                                             "line": r.budget_line_id.name})
        return True

    def _check_activity_availability(self, reserve_amount):
        """Returns False if there's room, or (level_name, level_available) for
        the FIRST level (checked Activity, then Project, then Program) that
        doesn't have enough - checked in that order since a shortfall lower
        in the hierarchy is the more specific, more actionable one to report.
        Each level is row-locked via its own get_available_locked(), exactly
        mirroring how the budget line itself is checked just above - so two
        acquisitions committing against the same activity at once are
        correctly serialised, not racing each other."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if not company.arcs_enforce_program_ceilings:
            return False
        rounding = self.currency_id.rounding
        for level_name, record in (
                (_("Activity '%s'") % self.activity_id.name, self.activity_id),
                (_("Project '%s'") % self.project_id.name, self.project_id),
                (_("Program '%s'") % self.program_id.name, self.program_id),
        ):
            if not record:
                continue
            level_available = record.get_available_locked()
            if float_compare(reserve_amount, level_available, precision_rounding=rounding) > 0:
                return (level_name, level_available)
        return False

    def action_open_quotation_wizard(self):
        self.ensure_one()
        if self.state != "submitted":
            raise UserError(_(
                "The real price can only be confirmed while the acquisition is submitted."))
        wizard = self.env["arcs.spend.request.quotation.wizard"].create({
            "request_id": self.id,
            "line_ids": [(0, 0, {
                "request_line_id": line.id,
                "quoted_unit_price": line.unit_estimate,
            }) for line in self.line_ids],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Confirm Real Price"),
            "res_model": "arcs.spend.request.quotation.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_approve(self):
        for r in self:
            if r.state != "committed":
                raise UserError(_("Only committed requests can be approved."))
        return self._transition("approved", "approve")

    def action_disburse_advance(self):
        """Create the cash advance (arcs.advance, advance_type='employee')
        for Requested By, linked back to this acquisition's grant/budget
        line/currency, if one doesn't already exist - then open THAT
        ADVANCE'S OWN FORM, rather than silently locking it and jumping
        straight to the disbursement wizard on the employee's behalf.

        This is deliberate: locking an employee advance requires a real
        debtor Partner (see arcs.advance.action_lock). arcs_advance now
        derives that from the employee's own contact record whenever
        possible (see ArcsAdvance._derive_employee_partner), but it can't
        always - the employee's HR record may simply have no partner of
        any kind linked yet. Silently trying to lock here and failing with
        a raw error dialog left Finance with no way to fix it. Landing on
        the advance's own form instead means every field - including
        Partner - is right there, editable, with the advance's own 'Lock
        Advance' and 'Issue Advance' buttons driving the rest of the flow,
        exactly the same as any advance created directly from the Advances
        menu: review the details (and the Employee Code shown next to
        Requested By above, so there's no ambiguity about which employee
        this is for), Lock, then Issue.

        Calling this again on an acquisition that already has an advance
        simply re-opens that advance's form - the natural 'resume' path if
        Finance navigated away before locking or disbursing - so this one
        method now covers what action_complete_disbursement used to handle
        as a separate button.

        A deliberate, explicit Finance action - never automatic on Approve -
        matching how every other real money movement in this system works
        (Commit & Reserve, fund receipts, donor funding). Allow Liquidation
        Above Advance is switched on for this advance specifically, since
        an acquisition's confirmed price can end up a little higher than
        what was advanced for it - the difference is then settled via
        Settle Advance rather than being blocked as it would be for a
        normal advance.

        arcs_request deliberately does not duplicate any journal-entry
        logic here - it only ever creates the draft record and hands off
        to arcs_advance's own buttons/wizards, the same way
        action_settle_advance below hands off to arcs_advance's Settlement
        wizard."""
        self.ensure_one()
        if not (self.env.user.has_group("arcs_base.group_finance_manager")
                or self.env.user.has_group("arcs_base.group_system_admin")):
            raise UserError(_("Only a Finance Manager can disburse an employee advance."))
        if self.state != "approved":
            raise UserError(_("Only approved acquisitions can have their advance disbursed."))
        if self.advance_id and self.advance_id.state == "issued":
            raise UserError(_("An advance has already been disbursed for this acquisition."))
        if not self.advance_id:
            if not self.requested_by:
                raise UserError(_(
                    "Set 'Requested By' (the employee this acquisition is for) before "
                    "disbursing an advance."))
            amount = self.approved_amount or self.estimated_amount
            advance = self.env["arcs.advance"].create({
                "advance_type": "employee",
                "employee_id": self.requested_by.id,
                "grant_id": self.grant_id.id,
                "budget_line_id": self.budget_line_id.id,
                "currency_id": self.currency_id.id,
                "amount": amount,
                "date": fields.Date.context_today(self),
                "reference": self.name,
                "allow_over_liquidation": True,
                "note": _("Advance for acquisition %s.") % self.name,
                "spend_request_id": self.id,
            })
            self.advance_id = advance.id
        return self.action_view_advance()

    def action_complete_disbursement(self):
        """Kept as a thin alias - some views/automations may still call
        this name - now just delegates to action_disburse_advance(), which
        already handles both 'create and open' and 'resume, already
        exists' in one place."""
        self.ensure_one()
        if not self.advance_id:
            raise UserError(_("There is no pending disbursement to complete."))
        return self.action_disburse_advance()

    def action_view_advance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "arcs.advance",
            "res_id": self.advance_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_settle_advance(self):
        self.ensure_one()
        if not self.advance_id:
            raise UserError(_("No advance has been disbursed for this acquisition yet."))
        return self.advance_id.action_open_settlement_wizard()

    def action_create_liquidation_for_advance(self):
        """Same as the advance's own 'Create Liquidation', but pre-fills the
        justified expenses with this acquisition's own posted expenses so
        Finance doesn't have to hunt for them among every posted expense in
        the system."""
        self.ensure_one()
        if not self.advance_id:
            raise UserError(_("No advance has been disbursed for this acquisition yet."))
        posted_expenses = self.expense_ids.filtered(lambda e: e.state == "posted")
        return {
            "type": "ir.actions.act_window",
            "name": _("New Liquidation"),
            "res_model": "arcs.advance.liquidation",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_advance_id": self.advance_id.id,
                "default_expense_ids": [(6, 0, posted_expenses.ids)],
            },
        }

    def _release(self):
        """Release every still-confirmed reserve tied to this request - not just
        the primary one - so a split reserve frees ALL the budget lines it
        touched, not only the first."""
        for r in self:
            r.commitment_ids.filtered(lambda c: c.state == "confirmed").action_release()

    def action_reject(self, reason=False):
        self._release()
        return self._transition("rejected", "reject", comment=reason)

    def action_cancel(self, reason=False):
        self._release()
        return self._transition("cancelled", "cancel", comment=reason)

    def action_reset_draft(self, reason=False):
        self._release()
        for r in self:
            r.commitment_id = False
        self.write({
            "shortfall_amount": 0.0, "insufficient_funds_note": False,
            "shortfall_type": "budget_line",
        })
        return self._transition("draft", "reset", comment=reason)

    def action_create_expense(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only approved requests can spawn an expense."))
        commitments = self._active_commitments()
        if len(commitments.mapped("budget_line_id")) > 1:
            return self._action_create_split_expenses(commitments)
        ctx = {
            "default_request_id": self.id,
            "default_budget_line_id": self.budget_line_id.id,
            "default_grant_id": self.grant_id.id,
            "default_amount": self.approved_amount or self.estimated_amount,
            "default_zone_id": self.zone_id.id,
            "default_department_id": self.department_id.id,
            "default_project_id": self.project_id.id,
            "default_activity_id": self.activity_id.id,
            "default_partner_id": self.vendor_id.id,
        }
        return {"type": "ir.actions.act_window", "res_model": "arcs.expense",
                "view_mode": "form", "target": "current", "context": ctx}

    def _action_create_split_expenses(self, commitments):
        """The reserve was split across several budget lines, so a single
        arcs.expense (one budget_line_id, one commitment_id) can't represent
        the actual spend: create one draft expense per line instead, each
        pre-filled with that line's own reserved amount. Each keeps its own
        budget line end-to-end - through approval (adopts the matching
        commitment, see arcs_expense.py), posting, and the actuals/available
        figures on arcs.budget.line - exactly mirroring the split made at
        reservation time instead of collapsing it back into one line."""
        self.ensure_one()
        Expense = self.env["arcs.expense"]
        expenses = Expense.browse()
        for c in commitments.sorted("id"):
            expenses |= Expense.create({
                "request_id": self.id,
                "budget_line_id": c.budget_line_id.id,
                "grant_id": c.budget_line_id.grant_id.id,
                "amount": c.amount,
                "date": fields.Date.context_today(self),
                "zone_id": self.zone_id.id,
                "department_id": self.department_id.id,
                "project_id": self.project_id.id,
                "activity_id": self.activity_id.id,
                "partner_id": self.vendor_id.id,
                "name": _("%(request)s - %(line)s") % {
                    "request": self.name, "line": c.budget_line_id.name},
            })
        self.message_post(body=_(
            "Created %(n)s draft expenses (one per reserved budget line) from this "
            "split acquisition.") % {"n": len(expenses)})
        return {
            "type": "ir.actions.act_window", "res_model": "arcs.expense",
            "name": _("Expenses"), "view_mode": "tree,form",
            "domain": [("id", "in", expenses.ids)],
        }

    # ---------------- voucher printing ----------------
    def _voucher_title(self):
        return "Acquisition Commitment Voucher"

    def _voucher_subtitle(self):
        return "Budget Reservation Reference"

    def _voucher_party_label(self):
        return "Vendor" if self.vendor_id else False

    def _voucher_party_name(self):
        return self.vendor_id.name

    def _voucher_context_line(self):
        parts = [p for p in (self.grant_id.name, self.budget_line_id.name,
                             self.quotation_ref and _("Quotation: %s") % self.quotation_ref) if p]
        return " | ".join(parts) if parts else False

    def _voucher_is_posted(self):
        return False

    def _voucher_lines(self):
        """One debit/credit pair per reserved budget line. Before Commit &amp;
        Reserve (or for a request that only ever used a single line) this is
        exactly the original single pair; once Finance has split the approved
        amount across several budget lines, each line gets its own pair so the
        voucher shows - and foots to - exactly how much was drawn from where,
        instead of a single number that would hide the split."""
        self.ensure_one()
        commitments = self._active_commitments()
        if not commitments:
            amount = self.approved_amount or self.estimated_amount
            account_name = ", ".join(self.budget_line_id.account_ids.mapped("display_name")) \
                           or self.budget_line_id.name
            return [
                {"account": account_name, "description": self.name, "debit": amount, "credit": 0.0},
                {"account": _("Budget Reserve - %s") % self.budget_line_id.name,
                 "description": _("Reservation"), "debit": 0.0, "credit": amount},
            ]
        lines = []
        for c in commitments.sorted("id"):
            account_name = ", ".join(c.budget_line_id.account_ids.mapped("display_name")) \
                           or c.budget_line_id.name
            lines.append({"account": account_name, "description": self.name,
                          "debit": c.amount, "credit": 0.0})
            lines.append({"account": _("Budget Reserve - %s") % c.budget_line_id.name,
                          "description": _("Reservation"), "debit": 0.0, "credit": c.amount})
        return lines

    def action_print_voucher(self):
        self.ensure_one()
        return self.env.ref("arcs_request.action_report_acquisition_voucher").report_action(self)

    def action_print_request_summary(self):
        """Reference sheet used to collect vendor quotations - not a
        commitment voucher (no debit/credit lines, no accounting
        significance), just a printout of the acquisition as currently
        filled in (Requesting Unit, Activity/Project/Program, Budget Line
        & Funding, and the requested Items with their estimated amounts),
        plus a small blank section for the vendor to fill in their quoted
        price. Available once Submitted, when the estimated amounts are
        final but the real quotation hasn't been collected yet - the exact
        gap this document exists to bridge."""
        self.ensure_one()
        return self.env.ref(
            "arcs_request.action_report_acquisition_request_summary").report_action(self)

    def action_view_expenses(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "arcs.expense",
                "name": _("Expenses"), "view_mode": "tree,form",
                "domain": [("request_id", "=", self.id)],
                "context": {"default_request_id": self.id}}

    def action_view_commitments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("arcs_budget.action_arcs_commitment")
        action["domain"] = [("spend_request_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_view_budget_transfers(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "arcs.budget.transfer",
                "name": _("Internal Budget Transfers"), "view_mode": "tree,form",
                "domain": [("spend_request_id", "=", self.id)]}

    def action_view_donor_funding(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "arcs.donor.funding.request",
                "name": _("Donor Funding Requests"), "view_mode": "tree,form",
                "domain": [("spend_request_id", "=", self.id)]}

    # ---------------- insufficient-funds recovery ----------------
    def action_open_insufficient_funds_wizard(self):
        """The single entry point for every recovery path - opens the
        router wizard that offers all of them together, regardless of
        which axis (budget line or Activity/Project/Program) triggered
        the shortfall."""
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Resolve Insufficient Funds"),
            "res_model": "arcs.spend.request.insufficient.funds.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_choose_different_budget_line(self):
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Choose a Different Budget Line"),
            "res_model": "arcs.spend.request.reassign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_choose_different_activity(self):
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Choose a Different Activity"),
            "res_model": "arcs.spend.request.activity.reassign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_open_split_wizard(self):
        """One of the recovery paths offered on any Insufficient Funds
        request, alongside reassign / internal transfer / donor funding /
        the activity-axis equivalents: cover the approved amount by
        reserving part of it on the primary budget line and the rest on one
        or more other lines, instead of moving money between lines or
        waiting on a transfer/donor-funding approval. Restricted like
        Commit & Reserve (not just via the button's `groups` attribute,
        which only hides it - this actually reserves budget, so it needs
        the same server-side authorization)."""
        self.ensure_one()
        if not (self.env.user.has_group("arcs_base.group_finance_manager")
                or self.env.user.has_group("arcs_base.group_system_admin")):
            raise UserError(_("Only a Finance Manager can split a reserve across budget lines."))
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Split Reserve Across Budget Lines"),
            "res_model": "arcs.spend.request.split.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_open_activity_split_wizard(self):
        """Same idea as action_open_split_wizard, one level up: cover the
        approved amount by drawing part of it from the acquisition's own
        Activity's Planned Cost and the rest from one or more other
        activities - most relevant when the budget line itself has room but
        the programmatic (Activity/Project/Program) ceiling doesn't, though
        offered alongside every other recovery path regardless of which
        axis actually triggered the shortfall - Finance decides which tool
        fits, not the system."""
        self.ensure_one()
        if not (self.env.user.has_group("arcs_base.group_finance_manager")
                or self.env.user.has_group("arcs_base.group_system_admin")):
            raise UserError(_("Only a Finance Manager can split a reserve across activities."))
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        if not self.activity_id:
            raise UserError(_(
                "This acquisition isn't linked to an Activity, so there's nothing to "
                "split across activities."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Split Reserve Across Activities"),
            "res_model": "arcs.spend.request.activity.split.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_request_budget_transfer(self):
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        transfer = self.env["arcs.budget.transfer"].create({
            "to_line_id": self.budget_line_id.id,
            "amount": self.shortfall_amount,
            "reason": _("Cover the shortfall on acquisition %s.") % self.name,
            "spend_request_id": self.id,
        })
        self.message_post(body=_("Internal budget transfer %s requested to cover the shortfall.")
                               % transfer.name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Internal Budget Transfer"),
            "res_model": "arcs.budget.transfer",
            "res_id": transfer.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_request_donor_funding(self):
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        if not self.budget_line_id.grant_id:
            raise UserError(_("The budget line has no grant to request supplementary funding from."))
        funding = self.env["arcs.donor.funding.request"].create({
            "grant_id": self.budget_line_id.grant_id.id,
            "amount_requested": self.shortfall_amount,
            "reason": _("Cover the shortfall on acquisition %s.") % self.name,
            "spend_request_id": self.id,
        })
        self.message_post(body=_("Donor supplementary funding request %s created to cover the shortfall.")
                               % funding.name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Donor Supplementary Funding Request"),
            "res_model": "arcs.donor.funding.request",
            "res_id": funding.id,
            "view_mode": "form",
            "target": "current",
        }


class ArcsSpendRequestLine(models.Model):
    _name = "arcs.spend.request.line"
    _description = "Acquisition Item"

    request_id = fields.Many2one("arcs.spend.request", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="request_id.currency_id")
    name = fields.Char(string="Item", required=True)
    quantity = fields.Float(default=1.0)
    unit_estimate = fields.Monetary(string="Est. Unit", currency_field="currency_id")
    amount = fields.Monetary(string="Est. Amount", compute="_compute_amount", store=True,
                             currency_field="currency_id")
    quoted_unit_price = fields.Monetary(
        string="Quoted Unit", currency_field="currency_id", copy=False, readonly=True,
        help="Real vendor-quoted unit price, set by 'Confirm Real Price'. "
             "Blank until a quotation has been confirmed for this acquisition.")
    quoted_amount = fields.Monetary(
        string="Quoted Total", currency_field="currency_id", copy=False, readonly=True,
        help="Real vendor-quoted line total (quantity x Quoted Unit), set by "
             "'Confirm Real Price'. Blank until a quotation has been confirmed.")
    note = fields.Char()

    @api.depends("quantity", "unit_estimate")
    def _compute_amount(self):
        for l in self:
            l.amount = (l.quantity or 0.0) * (l.unit_estimate or 0.0)
