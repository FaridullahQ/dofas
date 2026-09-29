from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsRequestedByCascade(TransactionCase):
    """'Requested By' is first in the Requesting Unit group and, once an
    employee is picked, auto-fills Region, Province, Department, Department
    Manager and Budget Holder from that employee's own hr.department record
    - mirroring the existing Activity -> Project -> Program -> Budget Line
    cascade. Every auto-filled field must stay fully editable, and the
    cascade must never wipe a value it just set itself (the same self-wipe
    regression the activity cascade already guards against)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "ARCSREQBY600", "account_type": "expense"})

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-REQBY", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-REQBY-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.budget = cls.env["arcs.budget"].create({"grant_id": cls.grant.id})
        cls.line = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line A",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 5000.0})
        cls.budget.action_approve()
        cls.grant.action_submit()
        cls.grant.action_approve()
        cls.grant.action_activate()

        cls.hq = cls.env["arcs.zone"].create(
            {"name": "Head Office", "code": "REQBY-HQ", "kind": "hq"})
        cls.region = cls.env["arcs.zone"].create({
            "name": "Central Region", "code": "REQBY-CTRL", "kind": "zone",
            "parent_id": cls.hq.id})
        cls.other_region = cls.env["arcs.zone"].create({
            "name": "Eastern Region", "code": "REQBY-EAST", "kind": "zone",
            "parent_id": cls.hq.id})
        cls.province = cls.env["arcs.zone"].create({
            "name": "Kabul Province", "code": "REQBY-KBL", "kind": "province",
            "parent_id": cls.region.id,
            "budget_holder_id": cls.env.user.id})

        cls.dept_manager = cls.env["hr.employee"].create({"name": "Dept Manager"})
        cls.department = cls.env["hr.department"].create({
            "name": "Health", "code": "REQBY-HEALTH",
            "zone_id": cls.province.id, "manager_id": cls.dept_manager.id,
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "Amina Yusuf", "department_id": cls.department.id})
        cls.employee_no_dept = cls.env["hr.employee"].create({"name": "No Department"})

    def test_requested_by_autofills_requesting_unit(self):
        form = Form(self.env["arcs.spend.request"])
        form.budget_line_id = self.line
        form.requested_by = self.employee
        self.assertEqual(form.department_id.id, self.department.id)
        self.assertEqual(form.zone_id.id, self.province.id)
        self.assertEqual(form.region_id.id, self.region.id)
        self.assertEqual(form.department_manager_id.id, self.dept_manager.id)
        self.assertEqual(form.budget_holder_id.id, self.env.user.id)
        request = form.save()
        self.assertEqual(request.department_id, self.department)
        self.assertEqual(request.zone_id, self.province)
        self.assertEqual(request.region_id, self.region)

    def test_cascade_does_not_self_wipe(self):
        """The same regression the Activity cascade already guards against:
        _onchange_requested_by sets region_id AND zone_id together (always
        consistent, by construction) - the region_id/zone_id onchange
        guards firing afterwards must not wipe what was just set."""
        form = Form(self.env["arcs.spend.request"])
        form.requested_by = self.employee
        self.assertEqual(form.zone_id.id, self.province.id)
        self.assertEqual(form.region_id.id, self.region.id)
        self.assertEqual(form.department_id.id, self.department.id)

    def test_employee_without_department_leaves_fields_untouched(self):
        form = Form(self.env["arcs.spend.request"])
        form.zone_id = self.province
        form.requested_by = self.employee_no_dept
        # No department on the employee - nothing to auto-fill from, so the
        # manually-set province is left exactly as the user set it.
        self.assertEqual(form.zone_id.id, self.province.id)
        self.assertFalse(form.department_id)

    def test_every_autofilled_field_stays_editable(self):
        form = Form(self.env["arcs.spend.request"])
        form.requested_by = self.employee
        # Auto-filled to region/province - now override each by hand.
        form.region_id = self.other_region
        self.assertFalse(form.zone_id)  # province cleared: no longer under this region
        other_province = self.env["arcs.zone"].create({
            "name": "Nangarhar Province", "code": "REQBY-NGR", "kind": "province",
            "parent_id": self.other_region.id})
        form.zone_id = other_province
        form.department_id = False
        form.department_manager_id = False
        form.budget_holder_id = False
        request = form.save()
        self.assertEqual(request.region_id, self.other_region)
        self.assertEqual(request.zone_id, other_province)
        self.assertFalse(request.department_id)
        self.assertFalse(request.department_manager_id)
        self.assertFalse(request.budget_holder_id)

    def test_department_domain_narrows_to_selected_province(self):
        """department_id's domain is derived from zone_id - confirm it
        actually resolves to only that province's departments, the same way
        the pre-existing arcs.department-based domain used to."""
        other_dept = self.env["hr.department"].create({
            "name": "Logistics", "code": "REQBY-LOG"})  # no zone_id - different province
        matching = self.env["hr.department"].search(
            [("zone_id", "=", self.province.id)])
        self.assertIn(self.department, matching)
        self.assertNotIn(other_dept, matching)
