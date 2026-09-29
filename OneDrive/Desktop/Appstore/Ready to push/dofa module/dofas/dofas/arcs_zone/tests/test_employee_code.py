from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsHrEmployeeCode(TransactionCase):
    """Two employees can share the same name - Employee Code (added onto
    the real hr.employee model) is what lets Finance/Programs pick the
    right one everywhere an employee is chosen across the suite, without
    touching each of those individual fields (arcs.spend.request.
    requested_by, arcs.advance.employee_id, hr.department.manager_id...)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_code_shown_in_front_of_the_name(self):
        employee = self.env["hr.employee"].create(
            {"name": "John Smith", "employee_code": "EMP-0001"})
        name = dict(employee.name_get())[employee.id]
        self.assertEqual(name, "[EMP-0001] John Smith")

    def test_no_code_falls_back_to_plain_name(self):
        employee = self.env["hr.employee"].create({"name": "No Code Yet"})
        name = dict(employee.name_get())[employee.id]
        self.assertEqual(name, "No Code Yet")

    def test_duplicate_names_are_distinguishable_by_code(self):
        e1 = self.env["hr.employee"].create(
            {"name": "John Smith", "employee_code": "EMP-0001"})
        e2 = self.env["hr.employee"].create(
            {"name": "John Smith", "employee_code": "EMP-0002"})
        names = dict((e1 | e2).name_get())
        self.assertNotEqual(names[e1.id], names[e2.id])
        self.assertIn("EMP-0001", names[e1.id])
        self.assertIn("EMP-0002", names[e2.id])

    def test_code_unique_per_company(self):
        self.env["hr.employee"].create(
            {"name": "John Smith", "employee_code": "EMP-DUP", "company_id": self.company.id})
        with self.assertRaises(Exception):
            # SQL constraint - surfaces as IntegrityError, wrapped by the ORM.
            self.env["hr.employee"].create(
                {"name": "Someone Else", "employee_code": "EMP-DUP",
                 "company_id": self.company.id})
            self.env.cr.flush()

    def test_code_format_validated(self):
        with self.assertRaises(ValidationError):
            self.env["hr.employee"].create(
                {"name": "Bad Code", "employee_code": "e"})  # too short, lowercase

    def test_code_auto_uppercased_on_change(self):
        employee = self.env.new({"name": "Test", "employee_code": "emp-0099"})
        employee._onchange_employee_code_upper()
        self.assertEqual(employee.employee_code, "EMP-0099")

    def test_search_by_code_finds_the_employee(self):
        """The core of the feature: typing the code in any Many2one picker
        pointing at hr.employee (e.g. 'Requested By' on an Acquisition,
        'Employee' on a Cash Advance) must resolve the right person, not
        just searching by name."""
        e1 = self.env["hr.employee"].create(
            {"name": "Duplicate Name", "employee_code": "EMP-A1"})
        e2 = self.env["hr.employee"].create(
            {"name": "Duplicate Name", "employee_code": "EMP-B2"})

        found = self.env["hr.employee"].name_search("EMP-A1")
        found_ids = [f[0] for f in found]
        self.assertIn(e1.id, found_ids)
        self.assertNotIn(e2.id, found_ids)

    def test_code_optional_does_not_block_unrelated_employee_creation(self):
        """Employee Code is deliberately NOT required at the model level -
        hr.employee is used well beyond ARCS (Recruitment, other apps
        creating employees programmatically), and this feature must never
        block any of that."""
        employee = self.env["hr.employee"].create({"name": "No Code At All"})
        self.assertTrue(employee.id)
        self.assertFalse(employee.employee_code)
