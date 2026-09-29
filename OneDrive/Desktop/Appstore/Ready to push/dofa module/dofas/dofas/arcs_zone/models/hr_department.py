import re
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class HrDepartment(models.Model):
    """Departments are a real Odoo HR concept - reusing hr.department instead
    of a parallel ARCS-only model. This extension adds only what ARCS needs
    on top of the standard model: the Province (arcs.zone, kind='province')
    a department belongs to, and an optional short code used to identify it
    in ARCS reports/vouchers. Name and Department Manager (manager_id) are
    already native hr.department fields and are reused as-is - manager_id is
    a Many2one to hr.employee natively, which is why arcs.spend.request's
    auto-filled 'Department Manager' field (see arcs_request) is typed the
    same way."""

    _inherit = "hr.department"

    zone_id = fields.Many2one(
        "arcs.zone", string="Province", domain="[('kind', '=', 'province')]",
        help="The province this department belongs to. The province's own "
             "'Reports To' field links it up to its region.")
    code = fields.Char(
        help="Optional short ARCS identifier for this department, e.g. HEALTH or FIN-01.")

    _sql_constraints = [
        ("arcs_code_company_uniq", "unique(code, company_id)",
         "The department code must be unique per company."),
    ]

    @api.onchange("code")
    def _onchange_arcs_code_upper(self):
        if self.code:
            self.code = self.code.strip().upper()

    @api.constrains("code")
    def _check_arcs_code_format(self):
        for d in self.filtered("code"):
            if not CODE_RE.match(d.code.strip()):
                raise ValidationError(_(
                    "Invalid department code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit. Example: HEALTH or FIN-01.",
                    code=d.code))
