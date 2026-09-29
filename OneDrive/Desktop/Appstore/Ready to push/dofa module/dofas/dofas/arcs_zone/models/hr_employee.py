import re
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{1,23}$")


class HrEmployee(models.Model):
    """Two employees can share the same name - this adds a short,
    unique-per-company Employee Code so Finance/Programs can always tell
    them apart, everywhere an employee is picked across the ARCS suite
    ('Requested By' on an Acquisition, the Department Manager it auto-fills,
    'Employee' on a Cash Advance, etc.) - without touching any of those
    fields individually. Since every one of them is a plain Many2one to
    hr.employee, extending the model itself here is enough: the code shows
    up in front of the name wherever an employee is displayed (name_get)
    and can be typed to find the right person (_rec_names_search), the
    same way arcs.zone and hr.department (see hr_department.py in this
    same module) already do it for their own codes."""

    _inherit = "hr.employee"

    employee_code = fields.Char(
        string="Employee Code", copy=False, index=True,
        help="Unique ARCS identifier for this employee - lets Finance and Programs "
             "tell apart employees who happen to share the same name. Shown alongside "
             "the name everywhere an employee is picked across the ARCS suite (e.g. "
             "'Requested By' on an Acquisition, 'Employee' on a Cash Advance) and "
             "searchable the same way - type the code to jump straight to the right "
             "person.")

    # Not required at the model level - hr.employee is used well beyond
    # ARCS (Recruitment converting an applicant, other apps creating
    # employees programmatically, etc.) and this must never block any of
    # that. Left blank, an employee just displays and searches by name
    # alone, exactly as before this feature existed.
    _sql_constraints = [
        ("employee_code_company_uniq", "unique(employee_code, company_id)",
         "This Employee Code is already used by another employee in this company."),
    ]

    @api.onchange("employee_code")
    def _onchange_employee_code_upper(self):
        if self.employee_code:
            self.employee_code = self.employee_code.strip().upper()

    @api.constrains("employee_code")
    def _check_employee_code_format(self):
        for e in self.filtered("employee_code"):
            if not CODE_RE.match(e.employee_code.strip()):
                raise ValidationError(_(
                    "Invalid Employee Code '%(code)s'.\n\n"
                    "Use 2-24 characters - letters, digits, dash, underscore or slash - "
                    "starting with a letter or digit. Example: EMP-0042 or STAFF001.",
                    code=e.employee_code))

    # Extra fields name_search() also matches against, in addition to the
    # model's usual name-based search - the official, version-stable Odoo
    # mechanism for this (no need to override _name_search by hand, which
    # has changed signature across versions). Typing an Employee Code in
    # ANY Many2one field pointing at hr.employee now finds the employee
    # immediately, the same way typing part of their name already did.
    _rec_names_search = ["name", "employee_code"]

    def name_get(self):
        # Compose with whatever the rest of the inheritance chain already
        # does (core hr.employee, or any other module's own name_get
        # override) rather than replacing it outright - this only ever
        # prepends the code on top of however the name would otherwise be
        # shown. super().name_get() returns (id, name) tuples in the same
        # order as self, so they can be paired up directly.
        res = []
        for employee, (rec_id, name) in zip(self, super().name_get()):
            if employee.employee_code:
                name = "[%s] %s" % (employee.employee_code, name)
            res.append((rec_id, name))
        return res
