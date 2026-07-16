import re
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class McitZone(models.Model):
    _name = "mcit.zone"
    _description = "Zone / Province"
    _order = "code, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    kind = fields.Selection(
        [("hq", "Headquarters"), ("zone", "Zone"), ("province", "Province")],
        required=True, default="zone")
    parent_id = fields.Many2one(
        "mcit.zone", string="Reports To",
        domain="[('kind', '=', 'hq')] if kind == 'zone' "
               "else [('kind', '=', 'zone')] if kind == 'province' else []",
        help="A Zone reports to a Headquarters, a Province reports to a Zone. "
             "Headquarters has no parent.")
    child_ids = fields.One2many("mcit.zone", "parent_id", string="Sub-zones / Provinces")
    child_count = fields.Integer(compute="_compute_child_count")
    department_ids = fields.One2many("mcit.department", "zone_id", string="Departments")
    department_count = fields.Integer(compute="_compute_department_count")
    manager_id = fields.Many2one("res.users", string="Zone Manager")
    budget_holder_id = fields.Many2one(
        "res.users", string="Budget Holder",
        help="The budget holder who formally initiates acquisitions for this zone.")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    note = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)", "The zone code must be unique per company."),
    ]

    def _compute_child_count(self):
        for z in self:
            z.child_count = len(z.child_ids)

    def _compute_department_count(self):
        for z in self:
            z.department_count = len(z.department_ids)

    def name_get(self):
        return [(z.id, "[%s] %s" % (z.code, z.name) if z.code else z.name) for z in self]

    @api.onchange("code")
    def _onchange_code_upper(self):
        if self.code:
            self.code = self.code.strip().upper()

    @api.onchange("kind")
    def _onchange_kind(self):
        # A parent picked under the previous kind is very likely no longer a
        # valid parent for the new kind (e.g. switching Zone -> Province
        # while "Reports To" still points at a Headquarters).
        if self.kind and self.parent_id:
            expected = {"zone": "hq", "province": "zone"}.get(self.kind)
            if expected and self.parent_id.kind != expected:
                self.parent_id = False

    @api.constrains("code")
    def _check_code_format(self):
        for z in self.filtered("code"):
            if not CODE_RE.match(z.code.strip()):
                raise ValidationError(_(
                    "Invalid zone code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit. Example: HRT or HERAT-Z.",
                    code=z.code))

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_(
                "This would create a circular hierarchy: a zone cannot report to "
                "itself, directly or indirectly."))

    @api.constrains("kind", "parent_id")
    def _check_hierarchy_levels(self):
        for z in self:
            if z.kind == "hq" and z.parent_id:
                raise ValidationError(_(
                    "'%s' is a Headquarters and cannot report to another zone/province.",
                    z.name))
            if z.kind == "zone" and z.parent_id and z.parent_id.kind != "hq":
                raise ValidationError(_(
                    "A Zone must report to a Headquarters (or have no parent). "
                    "'%(parent)s' is a %(kind)s.",
                    parent=z.parent_id.name, kind=z.parent_id.kind))
            if z.kind == "province" and (not z.parent_id or z.parent_id.kind != "zone"):
                raise ValidationError(_(
                    "A Province must report to a Zone. Set '%s''s 'Reports To' "
                    "field to the zone it belongs to.", z.name))

    def action_view_children(self):
        self.ensure_one()
        child_kind = {"hq": "zone", "zone": "province"}.get(self.kind)
        return {
            "type": "ir.actions.act_window",
            "name": _("Provinces") if self.kind == "zone" else _("Zones"),
            "res_model": "mcit.zone",
            "view_mode": "tree,form",
            "domain": [("parent_id", "=", self.id)],
            "context": {"default_parent_id": self.id, "default_kind": child_kind},
        }

    def action_view_departments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Departments"),
            "res_model": "mcit.department",
            "view_mode": "tree,form",
            "domain": [("zone_id", "=", self.id)],
            "context": {"default_zone_id": self.id},
        }
