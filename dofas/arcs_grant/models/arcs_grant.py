from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

FUNDING_MODELS = [
    ("unrestricted", "Unrestricted Donation"),
    ("grant_based", "Grant Based"),
    ("earmarked", "Earmarked"),
    ("multi_donor", "Multi-Donor Project"),
    ("donor_multi_project", "One Donor, Multiple Projects"),
    ("reimbursement", "Reimbursement"),
    ("revolving_fund", "Revolving Fund"),
]


class ArcsGrant(models.Model):
    _name = "arcs.grant"
    _description = "Grant / Donor Agreement"
    _inherit = ["arcs.approval.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "grant_number desc, id desc"

    name = fields.Char(string="Title", required=True, tracking=True,
                       help="Descriptive title of the grant.")
    grant_number = fields.Char(string="Grant Number", required=True, copy=False,
                               index=True, tracking=True,
                               help="Unique grant reference assigned by the donor. Example: UNDP-2026-001")
    agreement_number = fields.Char(string="Agreement Number", copy=False,
                                   help="Reference of the signed agreement.")
    donor_id = fields.Many2one("arcs.donor", string="Donor", required=True, tracking=True,
                               domain="[('active','=',True)]")
    funding_model = fields.Selection(
        FUNDING_MODELS,
        string="Funding Model",
        required=True,
        default="grant_based",
        help="""
    Choose the donor funding model:

    - Unrestricted Donation → Flexible funds, can be used anywhere.
    - Grant Based → Project-specific funds, with reporting rules.
    - Earmarked → Tagged money, reserved for a particular activity.
    - Multi-Donor Project → Several donors pool resources together.
    - One Donor, Multiple Projects → One donor funds different initiatives.
    - Reimbursement → Spend first, then get refunded later.
    - Revolving Fund → Self-sustaining pool, reused continuously (e.g. loan repayments).
    """
    )
    is_restricted = fields.Boolean(compute="_compute_is_restricted", store=True,
                                   help="Funds tied to this grant are restricted.")
    company_id = fields.Many2one("res.company", required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", string="Grant Currency", required=True,
                                  tracking=True,
                                  default=lambda self: self.env.company.currency_id)
    date_start = fields.Date(string="Start Date", required=True, tracking=True)
    date_end = fields.Date(string="End Date", required=True, tracking=True)
    approved_amount = fields.Monetary(string="Approved Amount", currency_field="currency_id",
                                      tracking=True, help="Enter approved budget amount")
    reporting_frequency = fields.Selection(
        [("monthly", "Monthly"), ("quarterly", "Quarterly"),
         ("semiannual", "Semi-annual"), ("annual", "Annual"), ("final", "Final only")],
        string="Reporting Frequency", default="quarterly")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Analytic Account",
                                          readonly=True, copy=False, ondelete="restrict")
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Review"), ("approved", "Approved"),
         ("active", "Active"), ("closed", "Closed"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False)
    active = fields.Boolean(default=True)

    attachment_ids = fields.One2many(
        "ir.attachment", "res_id", string="Documents", auto_join=True,
        domain=[("res_model", "=", "arcs.grant")],
        help="Files attached to this grant (e.g. the signed agreement). "
             "Add files through the chatter; they appear here.")

    _sql_constraints = [
        ("grant_number_uniq", "unique(grant_number, company_id)",
         "The Grant Number must be unique within a company."),
        ("agreement_number_uniq", "unique(agreement_number, company_id)",
         "The Agreement Number must be unique within a company."),
        ("approved_amount_non_negative", "CHECK(approved_amount >= 0)",
         "The Approved Amount cannot be negative."),
    ]

    @api.depends("funding_model")
    def _compute_is_restricted(self):
        for g in self:
            g.is_restricted = g.funding_model != "unrestricted"

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for g in self.filtered(lambda r: r.date_start and r.date_end):
            if g.date_start > g.date_end:
                raise ValidationError(_("The grant start date cannot be later than the end date."))

    @api.constrains("donor_id")
    def _check_donor_active(self):
        for g in self:
            if g.donor_id and not g.donor_id.active:
                raise ValidationError(_("The selected donor is archived and cannot be used."))

    @api.model_create_multi
    def create(self, vals_list):
        grants = super().create(vals_list)
        for g in grants:
            g._ensure_analytic_account()
        return grants

    def _ensure_analytic_account(self):
        self.ensure_one()
        if self.analytic_account_id:
            return
        plan = self.company_id.arcs_default_analytic_plan_id
        if not plan:
            raise UserError(_("Configure a Default Grant Analytic Plan in ARCS Settings before creating grants."))
        self.analytic_account_id = self.env["account.analytic.account"].create({
            "name": "%s - %s" % (self.grant_number, self.name),
            "plan_id": plan.id,
            "company_id": self.company_id.id,
            "partner_id": self.donor_id.partner_id.id or False,
        }).id

    # Workflow: Draft -> Review -> Approved -> Active -> Closed
    def action_submit(self):
        for g in self:
            if g.state != "draft":
                raise UserError(_("Only draft grants can be submitted for review."))
        return self._transition("review", "submit")

    def action_approve(self):
        for g in self:
            if g.state != "review":
                raise UserError(_("Only grants in review can be approved."))
            if float_compare(g.approved_amount, 0.0, precision_rounding=g.currency_id.rounding) <= 0:
                raise UserError(_("The approved amount must be greater than zero before approval."))
        return self._transition("approved", "approve")

    def action_activate(self):
        for g in self:
            if g.state != "approved":
                raise UserError(_("Only approved grants can be activated."))
        return self._transition("active", "activate")

    def action_reject(self, reason=False):
        for g in self:
            if g.state not in ("review", "approved"):
                raise UserError(_("This grant cannot be rejected in its current state."))
        return self._transition("draft", "reject", comment=reason)

    def action_close(self):
        for g in self:
            if g.state != "active":
                raise UserError(_("Only active grants can be closed."))
        return self._transition("closed", "close")

    def action_reopen(self):
        for g in self:
            if g.state != "closed":
                raise UserError(_("Only closed grants can be reopened."))
        return self._transition("active", "reopen")

    def action_cancel(self, reason=False):
        return self._transition("cancelled", "cancel", comment=reason)
