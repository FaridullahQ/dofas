from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class McitSpendRequest(models.Model):
    _name = "mcit.spend.request"
    _description = "Acquisition (Four Form)"
    _inherit = ["mcit.approval.mixin", "mcit.voucher.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "date_request desc, id desc"

    name = fields.Char(required=True, default=lambda s: _("New"), copy=False, readonly=True)
    date_request = fields.Date(default=fields.Date.context_today, tracking=True)
    zone_id = fields.Many2one("mcit.zone", string="Region / Province", tracking=True)
    department_id = fields.Many2one(
        "mcit.department", string="Department",
        domain="[] if not zone_id else ['|', ('zone_id', '=', zone_id), ('zone_id.parent_id', '=', zone_id)]",
        help="Narrowed to the departments of the selected Region/Province once one is chosen "
             "(matches whether you picked the province directly or its parent zone).")
    budget_line_id = fields.Many2one(
        "mcit.budget.line", string="Budget Line", required=True, tracking=True,
        domain="[('budget_state', '=', 'approved')]",
        help="Only budget lines on an Approved budget version are selectable - "
             "a Draft version isn't active yet and a Superseded one is historical.")
    grant_id = fields.Many2one("mcit.grant", related="budget_line_id.grant_id", store=True)
    program_id = fields.Many2one(
        "mcit.program", string="Program", tracking=True,
        help="Pick a program first to narrow the Project choices below.")
    project_id = fields.Many2one(
        "mcit.project", string="Project",
        domain="[('grant_id','=',grant_id)] + ([('program_id','=',program_id)] if program_id else [])")
    activity_id = fields.Many2one("mcit.activity", string="Activity",
                                  domain="[('project_id','=',project_id)]")
    company_id = fields.Many2one(related="budget_line_id.company_id", store=True)
    currency_id = fields.Many2one(related="budget_line_id.currency_id", store=True)
    budget_holder_id = fields.Many2one("res.users", string="Budget Holder", tracking=True)
    requested_by = fields.Many2one("res.users", string="Requested By",
                                   default=lambda s: s.env.user)
    line_ids = fields.One2many("mcit.spend.request.line", "request_id", string="Items")
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
    commitment_id = fields.Many2one("mcit.commitment", string="Reserve", readonly=True, copy=False)
    expense_ids = fields.One2many("mcit.expense", "request_id", string="Expenses")
    expense_count = fields.Integer(compute="_compute_expense_count")
    budget_transfer_ids = fields.One2many(
        "mcit.budget.transfer", "spend_request_id", string="Internal Budget Transfers")
    budget_transfer_count = fields.Integer(compute="_compute_budget_transfer_count")
    donor_funding_ids = fields.One2many(
        "mcit.donor.funding.request", "spend_request_id", string="Donor Funding Requests")
    donor_funding_count = fields.Integer(compute="_compute_donor_funding_count")
    state = fields.Selection(
        [("draft", "Drafted"), ("submitted", "Submitted"),
         ("insufficient_funds", "Insufficient Funds"), ("committed", "Committed"),
         ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)
    shortfall_amount = fields.Monetary(
        string="Shortfall", currency_field="currency_id", readonly=True, copy=False,
        help="How much the requested amount exceeded the budget line's live available balance.")
    insufficient_funds_note = fields.Char(readonly=True, copy=False)
    note = fields.Text()

    @api.depends("line_ids.amount")
    def _compute_estimated(self):
        for r in self:
            r.estimated_amount = sum(r.line_ids.mapped("amount"))

    def _compute_available(self):
        for r in self:
            r.available_on_line = r.budget_line_id.available_amount if r.budget_line_id else 0.0

    def _compute_expense_count(self):
        for r in self:
            r.expense_count = len(r.expense_ids)

    def _compute_budget_transfer_count(self):
        for r in self:
            r.budget_transfer_count = len(r.budget_transfer_ids)

    def _compute_donor_funding_count(self):
        for r in self:
            r.donor_funding_count = len(r.donor_funding_ids)

    @api.onchange("zone_id")
    def _onchange_zone(self):
        if self.zone_id and self.zone_id.budget_holder_id:
            self.budget_holder_id = self.zone_id.budget_holder_id
        if self.department_id and self.department_id.zone_id and self.zone_id and \
                self.department_id.zone_id != self.zone_id and \
                self.department_id.zone_id.parent_id != self.zone_id:
            self.department_id = False

    @api.onchange("program_id")
    def _onchange_program(self):
        if self.program_id and self.project_id and self.project_id.program_id != self.program_id:
            self.project_id = False
            self.activity_id = False

    @api.onchange("project_id")
    def _onchange_project(self):
        if self.activity_id and self.activity_id.project_id != self.project_id:
            self.activity_id = False
        if self.project_id and self.project_id.program_id and not self.program_id:
            self.program_id = self.project_id.program_id

    @api.onchange("budget_line_id")
    def _onchange_budget_line(self):
        self.project_id = False
        self.activity_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mcit.spend.request") or _("New")
        return super().create(vals_list)

    # ---------------- four-step workflow ----------------
    def action_submit(self):
        finance_or_admin = self.env.user.has_group("mcit_base.group_finance_manager") \
            or self.env.user.has_group("mcit_base.group_system_admin")
        for r in self:
            if r.state != "draft":
                raise UserError(_("Only drafted requests can be submitted."))
            if not r.line_ids:
                raise UserError(_("Add at least one item before submitting."))
            if r.budget_holder_id and r.budget_holder_id != self.env.user and not finance_or_admin:
                raise UserError(_(
                    "Only the assigned Budget Holder (%s) can submit this acquisition "
                    "for finance review.") % r.budget_holder_id.name)
        return self._transition("submitted", "submit")

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
                    "insufficient_funds_note": _(
                        "Available %(a).2f %(c)s, requested %(r).2f %(c)s on '%(l)s'.") % {
                        "a": available, "r": reserve_amount, "c": r.currency_id.name or "",
                        "l": r.budget_line_id.name},
                })
                r._transition("insufficient_funds", "insufficient_funds", comment=_(
                    "Insufficient budget: short by %(s).2f %(c)s on '%(l)s'.") % {
                    "s": shortfall, "c": r.currency_id.name or "", "l": r.budget_line_id.name})
                continue
            commitment = r.budget_line_id.reserve(
                reserve_amount, source_ref="%s,%s" % (r._name, r.id))
            r.commitment_id = commitment.id
            r._transition("committed", "commit", comment=_(
                "Reserved %(amount).2f %(currency)s (quoted, ref %(ref)s) on '%(line)s'") % {
                "amount": reserve_amount, "currency": r.currency_id.name or "",
                "ref": r.quotation_ref or "", "line": r.budget_line_id.name})
        return True

    def action_open_quotation_wizard(self):
        self.ensure_one()
        if self.state != "submitted":
            raise UserError(_(
                "The real price can only be confirmed while the acquisition is submitted."))
        wizard = self.env["mcit.spend.request.quotation.wizard"].create({
            "request_id": self.id,
            "line_ids": [(0, 0, {
                "request_line_id": line.id,
                "quoted_unit_price": line.unit_estimate,
            }) for line in self.line_ids],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Confirm Real Price"),
            "res_model": "mcit.spend.request.quotation.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_approve(self):
        for r in self:
            if r.state != "committed":
                raise UserError(_("Only committed requests can be approved."))
        return self._transition("approved", "approve")

    def _release(self):
        for r in self:
            if r.commitment_id and r.commitment_id.state == "confirmed":
                r.commitment_id.action_release()

    def action_reject(self):
        self._release()
        return self._transition("rejected", "reject")

    def action_cancel(self):
        self._release()
        return self._transition("cancelled", "cancel")

    def action_reset_draft(self):
        self._release()
        for r in self:
            r.commitment_id = False
        self.write({"shortfall_amount": 0.0, "insufficient_funds_note": False})
        return self._transition("draft", "reset")

    def action_create_expense(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only approved requests can spawn an expense."))
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
        return {"type": "ir.actions.act_window", "res_model": "mcit.expense",
                "view_mode": "form", "target": "current", "context": ctx}

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
        self.ensure_one()
        amount = self.approved_amount or self.estimated_amount
        account_name = ", ".join(self.budget_line_id.account_ids.mapped("display_name")) \
                       or self.budget_line_id.name
        return [
            {"account": account_name, "description": self.name, "debit": amount, "credit": 0.0},
            {"account": _("Budget Reserve - %s") % self.budget_line_id.name,
             "description": _("Reservation"), "debit": 0.0, "credit": amount},
        ]

    def action_print_voucher(self):
        self.ensure_one()
        return self.env.ref("mcit_request.action_report_acquisition_voucher").report_action(self)

    def action_view_expenses(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "mcit.expense",
                "name": _("Expenses"), "view_mode": "tree,form",
                "domain": [("request_id", "=", self.id)],
                "context": {"default_request_id": self.id}}

    def action_view_budget_transfers(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "mcit.budget.transfer",
                "name": _("Internal Budget Transfers"), "view_mode": "tree,form",
                "domain": [("spend_request_id", "=", self.id)]}

    def action_view_donor_funding(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "mcit.donor.funding.request",
                "name": _("Donor Funding Requests"), "view_mode": "tree,form",
                "domain": [("spend_request_id", "=", self.id)]}

    # ---------------- insufficient-funds recovery ----------------
    def action_choose_different_budget_line(self):
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Choose a Different Budget Line"),
            "res_model": "mcit.spend.request.reassign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_request_budget_transfer(self):
        self.ensure_one()
        if self.state != "insufficient_funds":
            raise UserError(_("This is only available on requests flagged Insufficient Funds."))
        transfer = self.env["mcit.budget.transfer"].create({
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
            "res_model": "mcit.budget.transfer",
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
        funding = self.env["mcit.donor.funding.request"].create({
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
            "res_model": "mcit.donor.funding.request",
            "res_id": funding.id,
            "view_mode": "form",
            "target": "current",
        }


class McitSpendRequestLine(models.Model):
    _name = "mcit.spend.request.line"
    _description = "Acquisition Item"

    request_id = fields.Many2one("mcit.spend.request", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="request_id.currency_id")
    name = fields.Char(string="Item", required=True)
    quantity = fields.Float(default=1.0)
    unit_estimate = fields.Monetary(string="Est. Unit", currency_field="currency_id")
    amount = fields.Monetary(string="Est. Amount", compute="_compute_amount", store=True,
                             currency_field="currency_id")
    note = fields.Char()

    @api.depends("quantity", "unit_estimate")
    def _compute_amount(self):
        for l in self:
            l.amount = (l.quantity or 0.0) * (l.unit_estimate or 0.0)
