from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ArcsComplianceChecklist(models.Model):
    _name = "arcs.compliance.checklist"
    _description = "Compliance Checklist"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True)
    donor_id = fields.Many2one("arcs.donor", string="Donor")
    line_ids = fields.One2many("arcs.compliance.checklist.line", "checklist_id", string="Items")
    active = fields.Boolean(default=True)

    line_count = fields.Integer(string="Items", compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for c in self:
            c.line_count = len(c.line_ids)

    @api.constrains("name", "donor_id", "active")
    def _check_unique_name(self):
        for c in self.filtered("active"):
            dom = [("id", "!=", c.id), ("name", "=", c.name), ("active", "=", True)]
            dom += [("donor_id", "=", c.donor_id.id)] if c.donor_id else [("donor_id", "=", False)]
            if self.search_count(dom):
                where = (" for donor '%s'" % c.donor_id.display_name) if c.donor_id else " (general)"
                raise ValidationError(_(
                    "A compliance checklist named '%(n)s' already exists%(w)s.\n\n"
                    "Rename this one or edit the existing checklist instead.",
                    n=c.name, w=where))


class ArcsComplianceChecklistLine(models.Model):
    _name = "arcs.compliance.checklist.line"
    _description = "Compliance Checklist Item"
    _order = "sequence, id"

    checklist_id = fields.Many2one("arcs.compliance.checklist", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help="Compliance requirement description.")
    required = fields.Boolean(default=True)
