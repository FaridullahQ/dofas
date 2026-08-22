import re
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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

    @api.constrains("code")
    def _check_code_format(self):
        for r in self.filtered("code"):
            if not CODE_RE.match(r.code.strip()):
                raise ValidationError(_(
                    "Invalid program code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit. Example: HEALTH or HEALTH-2026.",
                    code=r.code))

    @api.depends("planned_cost", "commitment_ids.amount", "commitment_ids.state",
                "commitment_ids.currency_id")
    def _compute_amounts(self):
        Expense = self.env["arcs.expense"]
        for p in self:
            company = p.company_id or self.env.company
            today = fields.Date.context_today(p)

            def to_company(amount, currency):
                if currency and company.currency_id and currency != company.currency_id:
                    return currency._convert(amount, company.currency_id, company, today)
                return amount

            committed = sum(
                to_company(c.amount, c.currency_id)
                for c in p.commitment_ids.filtered(lambda c: c.state == "confirmed")
            )
            expenses = Expense.search([
                ("project_id.program_id", "=", p.id), ("state", "=", "posted"),
            ])
            actual = sum(to_company(e.amount, e.currency_id) for e in expenses)
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
