from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo import fields


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

    # ================================================================ cascade

    def test_program_planned_cost_capped_at_its_budget_line(self):
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Line P", "planned_amount": 500.0})
        budget.action_approve()

        with self.assertRaises(ValidationError):
            self.env["arcs.program"].create({
                "name": "Over Program", "code": "OVER-P",
                "budget_line_id": line.id, "planned_cost": 600.0})  # exceeds 500

        program = self.env["arcs.program"].create({
            "name": "Fits Program", "code": "FITS-P",
            "budget_line_id": line.id, "planned_cost": 500.0})
        self.assertEqual(program.planned_cost, 500.0)

    def test_program_budget_line_onchange_suggests_planned_cost(self):
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Line Q", "planned_amount": 750.0})
        budget.action_approve()

        form = Form(self.env["arcs.program"])
        form.name = "Suggested Program"
        form.code = "SUGGEST-P"
        form.budget_line_id = line
        self.assertEqual(form.planned_cost, 750.0)
        program = form.save()
        self.assertEqual(program.planned_cost, 750.0)

    def test_project_cannot_exceed_program_planned_cost(self):
        with self.assertRaises(ValidationError):
            self.env["arcs.project"].create({
                "name": "Too Big Project", "code": "TOOBIG-PJ",
                "grant_id": self.grant.id, "program_id": self.program.id,
                "date_start": "2026-01-01", "date_end": "2026-12-31",
                "planned_cost": self.program.planned_cost + 1.0})

    def test_activity_cannot_exceed_project_planned_cost(self):
        with self.assertRaises(ValidationError):
            self.env["arcs.activity"].create({
                "name": "Too Big Activity", "project_id": self.project.id,
                "date_start": "2026-01-01", "date_end": "2026-03-31",
                "planned_cost": self.project.planned_cost + 1.0})

    def test_reducing_program_below_existing_project_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.program.planned_cost = self.project.planned_cost - 1.0

    def test_reducing_project_below_existing_activity_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.project.planned_cost = self.activity.planned_cost - 1.0

    def test_project_onchange_suggests_program_planned_cost(self):
        """setUpClass already has self.project (2000) as a sibling under
        self.program (3000) - so the correct suggestion for a brand-new
        second project is only what's left: 1000, not the program's full
        3000. This is the sibling-sharing fix itself, exercised via the
        very same fixtures every other test in this file already uses."""
        form = Form(self.env["arcs.project"])
        form.name = "Suggested Project"
        form.code = "SUGGEST-PJ"
        form.grant_id = self.grant
        form.program_id = self.program
        form.date_start = fields.Date.from_string("2026-01-01")
        form.date_end = fields.Date.from_string("2026-12-31")
        self.assertEqual(form.planned_cost, self.program.planned_cost - self.project.planned_cost)

    def test_activity_onchange_suggests_project_planned_cost(self):
        """Same reasoning one level down: self.activity (1000) is already a
        sibling under self.project (2000), so a brand-new second activity
        is only suggested the remaining 1000, not the project's full 2000."""
        form = Form(self.env["arcs.activity"])
        form.name = "Suggested Activity"
        form.project_id = self.project
        form.date_start = fields.Date.from_string("2026-01-01")
        form.date_end = fields.Date.from_string("2026-03-31")
        self.assertEqual(form.planned_cost, self.project.planned_cost - self.activity.planned_cost)

    # ======================================================= sibling sharing
    # The actual client requirement: several records planning against the
    # SAME parent (budget line / program / project) must never together
    # claim more than that parent actually has - a first record claiming
    # part of it must leave only the remainder for every other one.

    def test_activity_has_no_own_budget_line_field(self):
        """Activities are related to, and based on, their project - they no
        longer carry an independent budget_line_id of their own; the
        budget line only ever enters the hierarchy at the Program level."""
        self.assertNotIn("budget_line_id", self.env["arcs.activity"]._fields)

    def test_second_program_sharing_a_budget_line_is_capped_by_the_remainder(self):
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Shared Line", "planned_amount": 20000.0})
        budget.action_approve()

        program_a = self.env["arcs.program"].create({
            "name": "Program A", "code": "SHARE-A",
            "budget_line_id": line.id, "planned_cost": 10000.0})
        self.assertEqual(program_a.planned_cost, 10000.0)

        # Only 10,000 of the line's 20,000 remains for anyone else.
        with self.assertRaises(ValidationError):
            self.env["arcs.program"].create({
                "name": "Program B", "code": "SHARE-B",
                "budget_line_id": line.id, "planned_cost": 10000.01})

        program_b = self.env["arcs.program"].create({
            "name": "Program B", "code": "SHARE-B",
            "budget_line_id": line.id, "planned_cost": 10000.0})
        self.assertEqual(program_b.planned_cost, 10000.0)

        # And now the line is fully claimed - a third program gets nothing.
        with self.assertRaises(ValidationError):
            self.env["arcs.program"].create({
                "name": "Program C", "code": "SHARE-C",
                "budget_line_id": line.id, "planned_cost": 0.01})

    def test_program_budget_line_onchange_suggests_only_the_remainder(self):
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Shared Line 2", "planned_amount": 20000.0})
        budget.action_approve()
        self.env["arcs.program"].create({
            "name": "Program A2", "code": "SHARE-A2",
            "budget_line_id": line.id, "planned_cost": 12000.0})

        form = Form(self.env["arcs.program"])
        form.name = "Program B2"
        form.code = "SHARE-B2"
        form.budget_line_id = line
        # Not the line's full 20,000 - only what's left after Program A2.
        self.assertEqual(form.planned_cost, 8000.0)

    def test_editing_a_program_does_not_count_its_own_prior_claim_twice(self):
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Shared Line 3", "planned_amount": 5000.0})
        budget.action_approve()
        program = self.env["arcs.program"].create({
            "name": "Program A3", "code": "SHARE-A3",
            "budget_line_id": line.id, "planned_cost": 5000.0})
        # Re-saving the SAME value must not be blocked by its own claim.
        program.planned_cost = 5000.0
        self.assertEqual(program.planned_cost, 5000.0)

    def test_second_project_sharing_a_program_is_capped_by_the_remainder(self):
        program = self.env["arcs.program"].create(
            {"name": "Shared Program", "code": "SHARE-PROG", "planned_cost": 10000.0})
        self.env["arcs.project"].create({
            "name": "Project A", "code": "SHARE-PJ-A", "grant_id": self.grant.id,
            "program_id": program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 6000.0})

        with self.assertRaises(ValidationError):
            self.env["arcs.project"].create({
                "name": "Project B", "code": "SHARE-PJ-B", "grant_id": self.grant.id,
                "program_id": program.id, "date_start": "2026-01-01",
                "date_end": "2026-12-31", "planned_cost": 4000.01})  # only 4,000 left

        project_b = self.env["arcs.project"].create({
            "name": "Project B", "code": "SHARE-PJ-B", "grant_id": self.grant.id,
            "program_id": program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 4000.0})
        self.assertEqual(project_b.planned_cost, 4000.0)

    def test_project_onchange_suggests_only_the_remainder_of_its_program(self):
        program = self.env["arcs.program"].create(
            {"name": "Shared Program 2", "code": "SHARE-PROG2", "planned_cost": 10000.0})
        self.env["arcs.project"].create({
            "name": "Project A2", "code": "SHARE-PJ-A2", "grant_id": self.grant.id,
            "program_id": program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 7000.0})

        form = Form(self.env["arcs.project"])
        form.name = "Project B2"
        form.code = "SHARE-PJ-B2"
        form.grant_id = self.grant
        form.program_id = program
        form.date_start = fields.Date.from_string("2026-01-01")
        form.date_end = fields.Date.from_string("2026-12-31")
        self.assertEqual(form.planned_cost, 3000.0)

    def test_second_activity_sharing_a_project_is_capped_by_the_remainder(self):
        self.env["arcs.activity"].create({
            "name": "Second Workshop", "project_id": self.project.id,
            "date_start": "2026-04-01", "date_end": "2026-06-30",
            "planned_cost": 900.0})  # project has 2000, first activity already has 1000

        # Only 100 remains: 2000 (project) - 1000 (self.activity) - 900 (second) = 100.
        with self.assertRaises(ValidationError):
            self.env["arcs.activity"].create({
                "name": "Third Workshop", "project_id": self.project.id,
                "date_start": "2026-07-01", "date_end": "2026-09-30",
                "planned_cost": 100.01})

        third = self.env["arcs.activity"].create({
            "name": "Third Workshop", "project_id": self.project.id,
            "date_start": "2026-07-01", "date_end": "2026-09-30",
            "planned_cost": 100.0})
        self.assertEqual(third.planned_cost, 100.0)

    def test_activity_onchange_suggests_only_the_remainder_of_its_project(self):
        self.env["arcs.activity"].create({
            "name": "Second Workshop 2", "project_id": self.project.id,
            "date_start": "2026-04-01", "date_end": "2026-06-30",
            "planned_cost": 1000.0})  # project has 2000, first activity already has 1000
        # -> project is now fully claimed: 1000 (self.activity) + 1000 (second) = 2000.

        form = Form(self.env["arcs.activity"])
        form.name = "Third Workshop 2"
        form.project_id = self.project
        form.date_start = fields.Date.from_string("2026-07-01")
        form.date_end = fields.Date.from_string("2026-09-30")
        # Nothing left - suggested value is clamped to 0, never negative.
        self.assertEqual(form.planned_cost, 0.0)

    def test_reducing_program_below_sum_of_all_projects_is_blocked(self):
        """Not just each project individually - the SUM of every sibling
        project must still fit once the program shrinks."""
        program = self.env["arcs.program"].create(
            {"name": "Sum Program", "code": "SUM-PROG", "planned_cost": 3000.0})
        self.env["arcs.project"].create({
            "name": "Sum Project A", "code": "SUM-PJ-A", "grant_id": self.grant.id,
            "program_id": program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 1500.0})
        self.env["arcs.project"].create({
            "name": "Sum Project B", "code": "SUM-PJ-B", "grant_id": self.grant.id,
            "program_id": program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 1500.0})
        # Each project (1500) individually still fits under a reduced 2000
        # ceiling - only their SUM (3000) doesn't.
        with self.assertRaises(ValidationError):
            program.planned_cost = 2000.0

    def test_reducing_project_below_sum_of_all_activities_is_blocked(self):
        second = self.env["arcs.activity"].create({
            "name": "Sum Workshop", "project_id": self.project.id,
            "date_start": "2026-04-01", "date_end": "2026-06-30",
            "planned_cost": 900.0})
        self.assertEqual(self.activity.planned_cost, 1000.0)
        self.assertEqual(second.planned_cost, 900.0)
        # 1000 + 900 = 1900, so a project ceiling of 1500 leaves no single
        # activity individually over 1500, but their sum doesn't fit.
        with self.assertRaises(ValidationError):
            self.project.planned_cost = 1500.0

    def test_expense_activity_onchange_now_sources_budget_line_from_program(self):
        """arcs.expense's convenience auto-fill used to read the activity's
        own budget_line_id (removed) - it now cascades from the activity's
        Program instead, the new single source of truth."""
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Expense Line", "planned_amount": 5000.0})
        budget.action_approve()
        self.program.budget_line_id = line.id

        form = Form(self.env["arcs.expense"])
        form.grant_id = self.grant
        form.project_id = self.project
        form.activity_id = self.activity
        self.assertEqual(form.budget_line_id, line)


@tagged("post_install", "-at_install", "arcs")
class TestArcsProgramSmartButtons(TransactionCase):
    """Program/Project/Activity cross-navigation smart buttons: each count
    field and each action must reflect the real hierarchy and open the
    correct target with no side effects on any other record."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-SB", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-SB-1", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.program = cls.env["arcs.program"].create(
            {"name": "Health Program", "code": "SB-HEALTH", "planned_cost": 3000.0})
        cls.project = cls.env["arcs.project"].create({
            "name": "Wash Unit", "code": "SB-WASH-001", "grant_id": cls.grant.id,
            "program_id": cls.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 2000.0})
        cls.activity = cls.env["arcs.activity"].create({
            "name": "Workshop", "project_id": cls.project.id,
            "date_start": "2026-01-01", "date_end": "2026-03-31", "planned_cost": 1000.0})

    def test_program_project_count(self):
        self.assertEqual(self.program.project_count, 1)
        self.env["arcs.project"].create({
            "name": "Second Project", "code": "SB-WASH-002", "grant_id": self.grant.id,
            "program_id": self.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 500.0})
        self.program.invalidate_recordset()
        self.assertEqual(self.program.project_count, 2)

    def test_program_action_view_projects_domain(self):
        action = self.program.action_view_projects()
        self.assertEqual(action["res_model"], "arcs.project")
        self.assertEqual(action["domain"], [("program_id", "=", self.program.id)])
        self.assertEqual(action["context"]["default_program_id"], self.program.id)

    def test_project_activity_count(self):
        self.assertEqual(self.project.activity_count, 1)
        self.env["arcs.activity"].create({
            "name": "Second Workshop", "project_id": self.project.id,
            "date_start": "2026-04-01", "date_end": "2026-06-30", "planned_cost": 500.0})
        self.project.invalidate_recordset()
        self.assertEqual(self.project.activity_count, 2)

    def test_project_action_view_activities_domain(self):
        action = self.project.action_view_activities()
        self.assertEqual(action["res_model"], "arcs.activity")
        self.assertEqual(action["domain"], [("project_id", "=", self.project.id)])
        self.assertEqual(action["context"]["default_project_id"], self.project.id)

    def test_project_action_view_program_opens_correct_record(self):
        action = self.project.action_view_program()
        self.assertEqual(action["res_model"], "arcs.program")
        self.assertEqual(action["res_id"], self.program.id)
        self.assertEqual(action["view_mode"], "form")

    def test_project_without_program_has_no_program_link(self):
        orphan = self.env["arcs.project"].create({
            "name": "Standalone Project", "code": "SB-STANDALONE",
            "grant_id": self.grant.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 100.0})
        self.assertFalse(orphan.program_id)
        # action_view_program is only ever wired to a button that is
        # invisible when program_id is falsy; calling it directly on such
        # a record would open a non-existent record, so the view guards it
        # rather than the method - documented here so the guard is not
        # accidentally dropped later.
        action = orphan.action_view_program()
        self.assertFalse(action["res_id"])

    def test_activity_action_view_project_opens_correct_record(self):
        action = self.activity.action_view_project()
        self.assertEqual(action["res_model"], "arcs.project")
        self.assertEqual(action["res_id"], self.project.id)
        self.assertEqual(action["view_mode"], "form")

    def test_smart_button_actions_do_not_mutate_any_record(self):
        """Pure navigation: calling every new action method must not create,
        write, or unlink anything anywhere in the database."""
        Program = self.env["arcs.program"]
        Project = self.env["arcs.project"]
        Activity = self.env["arcs.activity"]
        before = (Program.search_count([]), Project.search_count([]),
                  Activity.search_count([]))
        self.program.action_view_projects()
        self.project.action_view_activities()
        self.project.action_view_program()
        self.activity.action_view_project()
        after = (Program.search_count([]), Project.search_count([]),
                 Activity.search_count([]))
        self.assertEqual(before, after)


@tagged("post_install", "-at_install", "arcs")
class TestArcsActivationGate(TransactionCase):
    """A Program/Project with a zero (or negative) Planned Cost is not
    considered ready to run: Activate must refuse it. Draft state itself
    stays completely unrestricted - only the transition is gated."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-AG", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-AG-1", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})

    def test_program_with_zero_planned_cost_cannot_activate(self):
        program = self.env["arcs.program"].create(
            {"name": "Empty Program", "code": "AG-EMPTY"})
        self.assertEqual(program.planned_cost, 0.0)
        with self.assertRaises(UserError):
            program.action_activate()
        self.assertEqual(program.state, "draft")

    def test_program_with_positive_planned_cost_activates(self):
        program = self.env["arcs.program"].create(
            {"name": "Funded Program", "code": "AG-FUNDED", "planned_cost": 1000.0})
        program.action_activate()
        self.assertEqual(program.state, "active")

    def test_program_negative_planned_cost_is_rejected_outright(self):
        with self.assertRaises(ValidationError):
            self.env["arcs.program"].create(
                {"name": "Negative Program", "code": "AG-NEG", "planned_cost": -1.0})

    def test_project_with_zero_planned_cost_cannot_activate(self):
        project = self.env["arcs.project"].create({
            "name": "Empty Project", "code": "AG-EMPTY-PJ", "grant_id": self.grant.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31"})
        self.assertEqual(project.planned_cost, 0.0)
        with self.assertRaises(UserError):
            project.action_activate()
        self.assertEqual(project.state, "draft")

    def test_project_with_positive_planned_cost_activates(self):
        project = self.env["arcs.project"].create({
            "name": "Funded Project", "code": "AG-FUNDED-PJ", "grant_id": self.grant.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31", "planned_cost": 500.0})
        project.action_activate()
        self.assertEqual(project.state, "active")

    def test_project_negative_planned_cost_is_rejected_outright(self):
        with self.assertRaises(ValidationError):
            self.env["arcs.project"].create({
                "name": "Negative Project", "code": "AG-NEG-PJ", "grant_id": self.grant.id,
                "date_start": "2026-01-01", "date_end": "2026-12-31", "planned_cost": -1.0})


@tagged("post_install", "-at_install", "arcs")
class TestArcsProgramGrantCascade(TransactionCase):
    """Program.grant_id (optional) narrows the Budget Line picker and lets
    Project inherit the Grant automatically instead of reselecting it -
    without forcing every Program into a single-grant shape, since a
    Program spanning several grants (documented, pre-existing behavior)
    must keep working exactly as before."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-GC", "donor_type": "multilateral"})
        cls.grant_a = cls.env["arcs.grant"].create({
            "name": "Grant A", "grant_number": "GR-GC-A", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.grant_b = cls.env["arcs.grant"].create({
            "name": "Grant B", "grant_number": "GR-GC-B", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.budget_a = cls.env["arcs.budget"].create({"grant_id": cls.grant_a.id})
        cls.line_a = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget_a.id, "name": "Line A", "planned_amount": 4000.0})
        cls.budget_a.action_approve()
        cls.budget_b = cls.env["arcs.budget"].create({"grant_id": cls.grant_b.id})
        cls.line_b = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget_b.id, "name": "Line B", "planned_amount": 4000.0})
        cls.budget_b.action_approve()

    def test_budget_line_domain_narrows_to_selected_grant(self):
        program = self.env["arcs.program"].create(
            {"name": "Pinned Program", "code": "GC-PINNED"})
        program.grant_id = self.grant_a
        result = program._onchange_grant_id()
        self.assertIn(("grant_id", "=", self.grant_a.id), result["domain"]["budget_line_id"])

    def test_budget_line_domain_unrestricted_without_grant(self):
        program = self.env["arcs.program"].create(
            {"name": "Open Program", "code": "GC-OPEN"})
        result = program._onchange_grant_id()
        self.assertEqual(result["domain"]["budget_line_id"],
                         [("budget_state", "=", "approved")])

    def test_mismatched_budget_line_cleared_when_grant_changes(self):
        program = self.env["arcs.program"].create({
            "name": "Switching Program", "code": "GC-SWITCH",
            "budget_line_id": self.line_a.id})
        form = Form(program)
        form.grant_id = self.grant_b
        program = form.save()
        self.assertFalse(program.budget_line_id)

    def test_matching_budget_line_kept_when_grant_set(self):
        program = self.env["arcs.program"].create({
            "name": "Consistent Program", "code": "GC-KEEP",
            "budget_line_id": self.line_a.id})
        form = Form(program)
        form.grant_id = self.grant_a
        program = form.save()
        self.assertEqual(program.budget_line_id, self.line_a)

    def test_grant_budget_line_mismatch_blocked_at_create(self):
        """The onchange is a UI convenience only - direct ORM writes (API,
        import, XML data) must still be rejected if they disagree."""
        with self.assertRaises(ValidationError):
            self.env["arcs.program"].create({
                "name": "Bad Program", "code": "GC-BAD",
                "grant_id": self.grant_a.id, "budget_line_id": self.line_b.id})

    def test_project_inherits_grant_from_program_via_form(self):
        program = self.env["arcs.program"].create(
            {"name": "Grant-Pinned Program", "code": "GC-INHERIT",
             "grant_id": self.grant_a.id})
        form = Form(self.env["arcs.project"])
        form.name = "Inheriting Project"
        form.code = "GC-INH-PJ"
        form.program_id = program
        form.date_start = fields.Date.from_string("2026-01-01")
        form.date_end = fields.Date.from_string("2026-12-31")
        # grant_id was never touched by hand - picking the Program alone
        # was enough.
        self.assertEqual(form.grant_id, self.grant_a)
        project = form.save()
        self.assertEqual(project.grant_id, self.grant_a)

    def test_project_grant_not_overwritten_if_already_chosen(self):
        """Picking a Program never silently swaps a Grant the user already
        deliberately chose (e.g. reassigning an existing standalone
        project's program, or a program spanning several grants)."""
        program = self.env["arcs.program"].create(
            {"name": "Grant-Pinned Program 2", "code": "GC-INHERIT2",
             "grant_id": self.grant_a.id})
        form = Form(self.env["arcs.project"])
        form.name = "Independent Project"
        form.code = "GC-IND-PJ"
        form.grant_id = self.grant_b
        form.program_id = program
        form.date_start = fields.Date.from_string("2026-01-01")
        form.date_end = fields.Date.from_string("2026-12-31")
        self.assertEqual(form.grant_id, self.grant_b)

    def test_standalone_project_without_program_keeps_direct_grant_selection(self):
        """A project under no Program (e.g. the One Donor, Multiple Projects
        model) is completely unaffected by any of this - it keeps picking
        its Grant directly, exactly as before."""
        project = self.env["arcs.project"].create({
            "name": "Standalone", "code": "GC-STANDALONE", "grant_id": self.grant_b.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31", "planned_cost": 100.0})
        self.assertFalse(project.program_id)
        self.assertEqual(project.grant_id, self.grant_b)
