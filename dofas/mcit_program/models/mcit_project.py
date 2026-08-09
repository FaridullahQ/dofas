from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
import re

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class McitProject(models.Model):
    _name = "mcit.project"
    _description = "Project"
    _inherit = ["mail.thread", "mcit.reason.action.mixin"]
    _order = "code"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Project Code", required=True, copy=False, index=True,
                       help="Example: HEALTH-001")
    program_id = fields.Many2one("mcit.program", string="Program")
    grant_id = fields.Many2one("mcit.grant", string="Grant", required=True, tracking=True)
    company_id = fields.Many2one(related="grant_id.company_id", store=True)
    manager_id = fields.Many2one("res.users", string="Project Manager")
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
                             default="draft", tracking=True)
    component_ids = fields.One2many("mcit.project.component", "project_id", string="Components")
    activity_ids = fields.One2many("mcit.activity", "project_id", string="Activities")
    active = fields.Boolean(default=True)

    _sql_constraints = [("code_uniq", "unique(code, company_id)",
                         "The Project Code must be unique per company.")]

    @api.constrains("date_start", "date_end", "grant_id")
    def _check_dates(self):
        for p in self:
            if p.date_start and p.date_end and p.date_start > p.date_end:
                raise ValidationError(_("Project start date cannot be later than its end date."))
            g = p.grant_id
            if g.date_start and g.date_end and p.date_start and p.date_end:
                if p.date_start < g.date_start or p.date_end > g.date_end:
                    raise ValidationError(_(
                        "Project dates must fall within the grant period (%(s)s to %(e)s).",
                        s=g.date_start, e=g.date_end))

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

    def action_activate(self):
        for p in self:
            if p.state != "draft":
                raise UserError(_("Only draft projects can be activated."))
        self.write({"state": "active"})

    def action_close(self):
        blocked = self.browse()
        for p in self:
            if p.state != "active":
                raise UserError(_("Only active projects can be closed."))
            if p.activity_ids.filtered(lambda a: a.state != "closed"):
                blocked = p
                break
        if blocked:
            return blocked._open_close_wizard()
        self.write({"state": "closed"})

    def _open_close_wizard(self):
        self.ensure_one()
        blockers = self.activity_ids.filtered(lambda a: a.state != "closed")
        wiz = self.env["mcit.lifecycle.close.wizard"].create({
            "res_model": self._name,
            "res_id": self.id,
            "record_name": self.display_name,
            "child_label": _("activities"),
            "blocker_count": len(blockers),
            "blockers": "\n".join("• %s" % n for n in blockers.mapped("name")),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Cannot close yet"),
            "res_model": "mcit.lifecycle.close.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def _force_close(self):
        for p in self:
            p.activity_ids.filtered(lambda a: a.state != "closed").write({"state": "closed"})
            p.write({"state": "closed"})

    def action_reset_draft(self, reason=False):
        self.write({"state": "draft"})
        if reason:
            self.message_post(body=_("Reason: %s") % reason)


class McitProjectComponent(models.Model):
    _name = "mcit.project.component"
    _description = "Project Component"
    _order = "project_id, name"

    name = fields.Char(required=True)
    project_id = fields.Many2one("mcit.project", required=True, ondelete="cascade", index=True)
    activity_ids = fields.One2many("mcit.activity", "component_id", string="Activities")
