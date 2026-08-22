from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsPlannedCost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-PC", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-PC-1", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})

        cls.program = cls.env["arcs.program"].create({
            "name": "Health Program", "code": "HEALTH", "planned_cost": 3000.0})
        cls.project = cls.env["arcs.project"].create({
            "name": "Wash Unit", "code": "WASH-001", "grant_id": cls.grant.id,
            "program_id": cls.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 2000.0})
        cls.activity = cls.env["arcs.activity"].create({
            "name": "Workshop", "project_id": cls.project.id,
            "date_start": "2026-01-01", "date_end": "2026-03-31", "planned_cost": 1000.0})
        cls.activity.action_submit()
        cls.activity.action_approve()

    def _confirm_commitment(self, activity, amount, budget_line=None):
        """Direct model-level reserve, bypassing the acquisition flow, purely
        to exercise the Program/Project/Activity roll-up in isolation."""
        if budget_line is None:
            budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
            budget_line = self.env["arcs.budget.line"].create({
                "budget_id": budget.id, "name": "Line A", "planned_amount": 5000.0})
            budget.action_approve()
        return budget_line.reserve(
            amount, activity_id=activity.id, project_id=activity.project_id.id,
            program_id=activity.project_id.program_id.id)

    def test_planned_cost_fields_exist_and_default_zero(self):
        program = self.env["arcs.program"].create({"name": "P2", "code": "P2"})
        self.assertEqual(program.planned_cost, 0.0)
        self.assertEqual(program.available_amount, 0.0)

    def test_commitment_decreases_availability_at_all_three_levels(self):
        self.assertEqual(self.activity.available_amount, 1000.0)
        self.assertEqual(self.project.available_amount, 2000.0)
        self.assertEqual(self.program.available_amount, 3000.0)

        self._confirm_commitment(self.activity, 400.0)

        self.activity.invalidate_recordset()
        self.project.invalidate_recordset()
        self.program.invalidate_recordset()
        self.assertEqual(self.activity.committed_amount, 400.0)
        self.assertEqual(self.activity.available_amount, 600.0)
        self.assertEqual(self.project.committed_amount, 400.0)
        self.assertEqual(self.project.available_amount, 1600.0)
        self.assertEqual(self.program.committed_amount, 400.0)
        self.assertEqual(self.program.available_amount, 2600.0)

    def test_release_restores_availability_at_all_three_levels(self):
        commitment = self._confirm_commitment(self.activity, 400.0)
        commitment.action_release()

        self.activity.invalidate_recordset()
        self.project.invalidate_recordset()
        self.program.invalidate_recordset()
        self.assertEqual(self.activity.committed_amount, 0.0)
        self.assertEqual(self.activity.available_amount, 1000.0)
        self.assertEqual(self.project.available_amount, 2000.0)
        self.assertEqual(self.program.available_amount, 3000.0)

    def test_second_activity_under_same_project_shares_project_ceiling(self):
        activity_2 = self.env["arcs.activity"].create({
            "name": "Distribution", "project_id": self.project.id,
            "date_start": "2026-04-01", "date_end": "2026-06-30", "planned_cost": 800.0})
        activity_2.action_submit()
        activity_2.action_approve()

        self._confirm_commitment(self.activity, 400.0)
        self._confirm_commitment(activity_2, 300.0)

        self.project.invalidate_recordset()
        self.program.invalidate_recordset()
        self.assertEqual(self.project.committed_amount, 700.0)
        self.assertEqual(self.project.available_amount, 1300.0)
        self.assertEqual(self.program.committed_amount, 700.0)
