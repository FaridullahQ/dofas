import re
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class McitProgram(models.Model):
    _name = "mcit.program"
    _description = "Program"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True, help="Program name, e.g. Health Program.")
    code = fields.Char(required=True, copy=False, index=True)
    manager_id = fields.Many2one("res.users", string="Program Manager")
    description = fields.Text()
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft", required=True, tracking=True, copy=False)
    project_ids = fields.One2many("mcit.project", "program_id", string="Projects")

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
        wiz = self.env["mcit.lifecycle.close.wizard"].create({
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
            "res_model": "mcit.lifecycle.close.wizard",
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

    def action_reset_draft(self):
        self.write({"state": "draft"})
