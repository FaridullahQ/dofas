from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsFundReceiptProgramAllocation(TransactionCase):
    """The Program Allocation on a Fund Receipt is auto-generated from the
    Grant's own Program -> Project -> Activity plan (arcs_program) - not
    typed in by hand - so a donor can see, in the organisation's own
    planning structure, exactly how their contribution maps onto real
    programs, projects and activities."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-ALLOC", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-ALLOC-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 50000.0})

        cls.other_grant = cls.env["arcs.grant"].create({
            "name": "Other", "grant_number": "GR-ALLOC-2", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 10000.0})

        # Program with two projects under cls.grant, one with an activity;
        # a second, unrelated project under cls.other_grant, to confirm the
        # generator only ever pulls in what's actually related to the
        # RECEIPT's own grant.
        cls.program = cls.env["arcs.program"].create(
            {"name": "Health Program", "code": "ALLOC-PROG", "planned_cost": 30000.0})
        cls.project_a = cls.env["arcs.project"].create({
            "name": "Vaccination Project", "code": "ALLOC-PJ-A", "grant_id": cls.grant.id,
            "program_id": cls.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 18000.0})
        cls.activity = cls.env["arcs.activity"].create({
            "name": "Cold Chain Kits", "project_id": cls.project_a.id,
            "date_start": "2026-01-01", "date_end": "2026-06-30", "planned_cost": 7000.0})
        cls.project_b = cls.env["arcs.project"].create({
            "name": "Nutrition Project", "code": "ALLOC-PJ-B", "grant_id": cls.grant.id,
            "program_id": cls.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 12000.0})
        cls.project_other_grant = cls.env["arcs.project"].create({
            "name": "Unrelated Project", "code": "ALLOC-PJ-OTHER",
            "grant_id": cls.other_grant.id, "program_id": cls.program.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31", "planned_cost": 5000.0})

    def _draft_receipt(self, grant=None):
        return self.env["arcs.fund.receipt"].create({
            "grant_id": (grant or self.grant).id, "amount": 20000.0,
            "currency_id": self.company.currency_id.id,
        })

    def test_onchange_grant_id_builds_full_hierarchy(self):
        form = Form(self.env["arcs.fund.receipt"])
        form.grant_id = self.grant
        form.amount = 20000.0
        receipt = form.save()

        lines = receipt.allocation_ids.sorted("sequence")
        self.assertEqual(len(lines), 4)  # program, project_a, activity, project_b
        self.assertEqual(lines[0].level, "program")
        self.assertEqual(lines[0].program_id, self.program)
        self.assertEqual(lines[0].amount, 30000.0)

        self.assertEqual(lines[1].level, "project")
        self.assertEqual(lines[1].project_id, self.project_a)
        self.assertEqual(lines[1].amount, 18000.0)

        self.assertEqual(lines[2].level, "activity")
        self.assertEqual(lines[2].activity_id, self.activity)
        self.assertEqual(lines[2].amount, 7000.0)

        self.assertEqual(lines[3].level, "project")
        self.assertEqual(lines[3].project_id, self.project_b)
        self.assertEqual(lines[3].amount, 12000.0)

        # The unrelated project under a different grant never shows up.
        self.assertNotIn(self.project_other_grant, lines.mapped("project_id"))

    def test_program_planned_total_does_not_double_count(self):
        receipt = self._draft_receipt()
        receipt._onchange_grant_id_allocation()
        # Only the program-level row(s) - NOT program + its projects + their
        # activities, which would count the same money three times over.
        self.assertEqual(receipt.program_planned_total, 30000.0)

    def test_hierarchical_name_is_indented_per_level(self):
        receipt = self._draft_receipt()
        receipt._onchange_grant_id_allocation()
        by_level = {l.level: l for l in receipt.allocation_ids if l.level != "project"
                   or l.project_id == self.project_a}
        self.assertFalse(by_level["program"].name.startswith("\xa0"))
        self.assertTrue(by_level["project"].name.startswith("\xa0"))
        self.assertTrue(by_level["activity"].name.startswith("\xa0"))
        self.assertIn(self.project_a.name, by_level["project"].name)
        self.assertIn(self.activity.name, by_level["activity"].name)

    def test_refresh_resyncs_after_plan_changes(self):
        receipt = self._draft_receipt()
        receipt._onchange_grant_id_allocation()
        self.assertEqual(receipt.program_planned_total, 30000.0)

        self.program.planned_cost = 45000.0
        receipt.action_refresh_program_allocation()
        self.assertEqual(receipt.program_planned_total, 45000.0)

    def test_refresh_blocked_once_posted(self):
        receipt = self._draft_receipt()
        receipt.action_refresh_program_allocation()  # fine while draft
        receipt.state = "posted"  # simulate posted without the full posting flow
        with self.assertRaises(UserError):
            receipt.action_refresh_program_allocation()

    def test_program_with_no_project_under_this_grant_but_own_budget_line(self):
        budget = self.env["arcs.budget"].create({"grant_id": self.grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Alloc Line", "planned_amount": 5000.0})
        budget.action_approve()
        standalone_program = self.env["arcs.program"].create({
            "name": "Standalone Program", "code": "ALLOC-STANDALONE",
            "budget_line_id": line.id, "planned_cost": 4000.0})

        receipt = self._draft_receipt()
        receipt.action_refresh_program_allocation()
        programs_shown = receipt.allocation_ids.filtered(
            lambda l: l.level == "program").mapped("program_id")
        self.assertIn(standalone_program, programs_shown)

    def test_allocation_email_html_includes_every_level(self):
        receipt = self._draft_receipt()
        receipt.action_refresh_program_allocation()
        html = receipt._allocation_email_html()
        self.assertIn(self.program.name, html)
        self.assertIn(self.project_a.name, html)
        self.assertIn(self.activity.name, html)
        self.assertIn(self.project_b.name, html)

    def test_activity_must_belong_to_its_row_project(self):
        other_project = self.env["arcs.project"].create({
            "name": "Other Project", "code": "ALLOC-PJ-C", "grant_id": self.grant.id,
            "program_id": self.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 1000.0})
        receipt = self._draft_receipt()
        with self.assertRaises(Exception):
            self.env["arcs.fund.receipt.allocation"].create({
                "fund_receipt_id": receipt.id, "level": "activity",
                "program_id": self.program.id, "project_id": other_project.id,
                "activity_id": self.activity.id,  # belongs to project_a, not other_project
                "amount": 100.0,
            })

    # ================================================================ manual add/remove
    # The client's other ask: auto-generated is right, but Finance still
    # needs to be able to remove a row, or add one back - with the same
    # "picked automatically" Planned Cost behaviour either way, not a
    # blank amount left for someone to type by hand.

    def test_removing_a_row_is_allowed(self):
        receipt = self._draft_receipt()
        receipt.action_refresh_program_allocation()
        count_before = len(receipt.allocation_ids)
        row = receipt.allocation_ids.filtered(lambda l: l.level == "activity")
        row.unlink()
        self.assertEqual(len(receipt.allocation_ids), count_before - 1)

    def test_manually_adding_a_program_row_fills_level_and_amount(self):
        program_only = self.env["arcs.program"].create(
            {"name": "Manual Program", "code": "ALLOC-MANUAL-P", "planned_cost": 8000.0})
        receipt = self._draft_receipt()
        form = Form(receipt)
        with form.allocation_ids.new() as line:
            line.program_id = program_only
        form.save()

        added = receipt.allocation_ids.filtered(lambda l: l.program_id == program_only)
        self.assertEqual(added.level, "program")
        self.assertEqual(added.amount, 8000.0)

    def test_adding_project_then_activity_deepens_level_and_updates_amount(self):
        receipt = self._draft_receipt()
        form = Form(receipt)
        with form.allocation_ids.new() as line:
            line.program_id = self.program
            self.assertEqual(line.level, "program")
            self.assertEqual(line.amount, 30000.0)

            line.project_id = self.project_a
            self.assertEqual(line.level, "project")
            self.assertEqual(line.amount, 18000.0)

            line.activity_id = self.activity
            self.assertEqual(line.level, "activity")
            self.assertEqual(line.amount, 7000.0)
        form.save()

    def test_clearing_activity_reverts_to_project_level_and_amount(self):
        receipt = self._draft_receipt()
        form = Form(receipt)
        with form.allocation_ids.new() as line:
            line.program_id = self.program
            line.project_id = self.project_a
            line.activity_id = self.activity
            line.activity_id = self.env["arcs.activity"]  # clear it
            self.assertEqual(line.level, "project")
            self.assertEqual(line.amount, 18000.0)
        form.save()

    def test_manually_added_program_scoped_to_grant(self):
        """program_id's domain only offers Programs actually related to
        this receipt's Grant - the same rule the auto-generator uses - so
        a manually added row can't casually point at something unrelated.
        Checked directly against the same query the field's own domain
        uses, rather than against Form's domain-violation behaviour (a UI
        hint honoured by the picker widget, not something to assert an
        exact exception type for)."""
        unrelated_program = self.env["arcs.program"].create(
            {"name": "Totally Unrelated", "code": "ALLOC-UNRELATED", "planned_cost": 500.0})
        matching = self.env["arcs.program"].search([
            "|", ("project_ids.grant_id", "=", self.grant.id),
            ("budget_line_id.grant_id", "=", self.grant.id),
        ])
        self.assertIn(self.program, matching)
        self.assertNotIn(unrelated_program, matching)
