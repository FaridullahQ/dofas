import re
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class ArcsDepartment(models.Model):
    _name = "arcs.department"
    _description = "Department"
    _order = "code, name"

    name = fields.Char(required=True)
    code = fields.Char(index=True)
    zone_id = fields.Many2one(
        "arcs.zone", string="Province", domain="[('kind', '=', 'province')]",
        help="The province this department belongs to. The province's own "
             "'Reports To' field links it up to its zone.")
    manager_id = fields.Many2one("res.users", string="Department Manager")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)", "The department code must be unique per company."),
    ]

    @api.onchange("code")
    def _onchange_code_upper(self):
        if self.code:
            self.code = self.code.strip().upper()

    @api.constrains("code")
    def _check_code_format(self):
        for d in self.filtered("code"):
            if not CODE_RE.match(d.code.strip()):
                raise ValidationError(_(
                    "Invalid department code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit. Example: HEALTH or FIN-01.",
                    code=d.code))
