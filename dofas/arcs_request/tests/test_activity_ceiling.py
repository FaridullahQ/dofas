import base64

from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsActivityCeiling(TransactionCase):
    """Commit & Reserve, when the acquisition is linked to an Activity and
    the company has Program/Project/Activity ceiling enforcement on, must
    also check the Activity's (and its Project's/Program's) own Planned
    Cost - independently of, and in addition to, the Budget Line check."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "ARCSACT600", "account_type": "expense"})

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-ACT", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-ACT-1", "donor_id": cls.donor.id,
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

        cls.program = cls.env["arcs.program"].create({
            "name": "Health Program", "code": "HEALTH-ACT", "planned_cost": 3000.0})
        cls.project = cls.env["arcs.project"].create({
            "name": "Wash Unit", "code": "WASH-ACT-001", "grant_id": cls.grant.id,
            "program_id": cls.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 2000.0})
        cls.activity_a = cls.env["arcs.activity"].create({
            "name": "Workshop A", "project_id": cls.project.id,
            "date_start": "2026-01-01", "date_end": "2026-03-31", "planned_cost": 700.0})
        cls.activity_a.action_submit()
        cls.activity_a.action_approve()
        cls.activity_b = cls.env["arcs.activity"].create({
            "name": "Workshop B", "project_id": cls.project.id,
            "date_start": "2026-04-01", "date_end": "2026-06-30", "planned_cost": 2000.0})
        cls.activity_b.action_submit()
        cls.activity_b.action_approve()

        cls.vendor = cls.env["res.partner"].create({"name": "Acme Supplies"})
        cls.attachment = cls.env["ir.attachment"].create({
            "name": "quote.pdf", "datas": base64.b64encode(b"dummy quotation"),
        })

    def _submitted_request(self, item_amount, activity=None):
        vals = {
            "budget_line_id": self.line.id,
            "line_ids": [(0, 0, {"name": "Equipment", "quantity": 1, "unit_estimate": item_amount})],
        }
        if activity:
            vals["activity_id"] = activity.id
        request = self.env["arcs.spend.request"].create(vals)
        request.action_submit()
        return request

    def _confirm_real_price(self, request, amount):
        wizard = self.env["arcs.spend.request.quotation.wizard"].create({
            "request_id": request.id, "vendor_id": self.vendor.id, "quotation_ref": "QTN-1",
            "attachment_ids": [(6, 0, self.attachment.ids)],
            "line_ids": [(0, 0, {
                "request_line_id": request.line_ids[0].id, "quoted_unit_price": amount,
            })],
        })
        wizard.action_confirm()

    def test_program_project_activity_shown_readonly_on_acquisition(self):
        request = self._submitted_request(1000.0, self.activity_a)
        self.assertEqual(request.project_id, self.project)
        self.assertEqual(request.program_id, self.program)
        self.assertEqual(request.activity_planned_cost, 700.0)
        self.assertEqual(request.project_planned_cost, 2000.0)
        self.assertEqual(request.program_planned_cost, 3000.0)

    def test_ceiling_ignored_by_default_backward_compatible(self):
        """Enforcement is off by default: an activity with less Planned Cost
        than the acquisition amount must NOT block commit - zero behavior
        change for any acquisition not opted into this feature."""
        self.assertFalse(self.company.arcs_enforce_program_ceilings)
        request = self._submitted_request(1000.0, self.activity_a)  # activity only has 700
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        self.assertEqual(request.state, "committed")
        # Still tagged for reporting, just not enforced as a hard stop.
        self.assertEqual(request.commitment_id.activity_id, self.activity_a)

    def test_ceiling_blocks_when_enforced_and_leaves_nothing_orphaned(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity_a)  # activity only has 700
        self._confirm_real_price(request, 1000.0)
        request.action_commit()

        self.assertEqual(request.state, "insufficient_funds")
        self.assertEqual(request.shortfall_type, "activity")
        self.assertEqual(request.shortfall_amount, 300.0)
        # No commitment was created at all - not on the budget line, not on
        # the activity - nothing to release, nothing orphaned.
        self.assertFalse(request.commitment_id)
        self.assertEqual(len(request.commitment_ids), 0)
        self.line.invalidate_recordset()
        self.assertEqual(self.line.available_amount, 5000.0)

    def test_ceiling_passes_when_project_or_program_short_even_if_activity_ok(self):
        """Activity B alone has plenty of room, but its Project ceiling
        (2000, already informed by Activity A's own 700 planned) can still
        be the binding constraint once enough is committed elsewhere."""
        self.company.arcs_enforce_program_ceilings = True
        # Commit 1600 against activity_a's own project first, via a separate
        # acquisition, to eat into the shared project ceiling.
        other = self._submitted_request(700.0, self.activity_a)
        self._confirm_real_price(other, 700.0)
        other.action_commit()
        self.assertEqual(other.state, "committed")

        # Project now has 2000 - 700 = 1300 left. Activity B's own ceiling
        # (1000) is fine, but asking for 1400 exceeds the PROJECT's 1300.
        request = self._submitted_request(1400.0, self.activity_b)
        self._confirm_real_price(request, 1400.0)
        request.action_commit()
        self.assertEqual(request.state, "insufficient_funds")
        self.assertEqual(request.shortfall_type, "activity")
        self.assertIn("Project", request.insufficient_funds_note or "")

    def test_budget_line_recovery_actions_blocked_on_activity_shortfall(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity_a)
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        self.assertEqual(request.shortfall_type, "activity")

        with self.assertRaises(UserError):
            request.action_choose_different_budget_line()
        with self.assertRaises(UserError):
            request.action_open_split_wizard()
        with self.assertRaises(UserError):
            request.action_request_budget_transfer()
        with self.assertRaises(UserError):
            request.action_request_donor_funding()

    def test_activity_recovery_actions_blocked_on_budget_line_shortfall(self):
        request = self._submitted_request(6000.0, self.activity_a)  # exceeds line's 5000
        self._confirm_real_price(request, 6000.0)
        request.action_commit()
        self.assertEqual(request.shortfall_type, "budget_line")

        with self.assertRaises(UserError):
            request.action_choose_different_activity()
        with self.assertRaises(UserError):
            request.action_open_activity_split_wizard()

    def test_choose_different_activity_recovers(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity_a)  # only 700 available
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        self.assertEqual(request.state, "insufficient_funds")

        wizard = self.env["arcs.spend.request.activity.reassign.wizard"].with_context(
            default_request_id=request.id).create({
                "new_activity_id": self.activity_b.id,  # has 1000, enough
                "reference": "MEMO-ACT-0001",
                "attachment_ids": [(6, 0, self.attachment.ids)],
            })
        wizard.action_confirm()
        self.assertEqual(request.state, "submitted")
        self.assertEqual(request.activity_id, self.activity_b)
        self.assertEqual(request.shortfall_type, "budget_line")

        request.action_commit()
        self.assertEqual(request.state, "committed")
        self.assertEqual(request.commitment_id.activity_id, self.activity_b)

    def test_split_across_activities(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity_a)  # only 700 available
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        self.assertEqual(request.state, "insufficient_funds")

        wizard = self.env["arcs.spend.request.activity.split.wizard"].with_context(
            default_request_id=request.id).create({
                "reference": "MEMO-ACT-SPLIT-0001",
                "attachment_ids": [(6, 0, self.attachment.ids)],
                "line_ids": [(0, 0, {"activity_id": self.activity_b.id, "amount": 300.0})],
            })
        self.assertEqual(wizard.primary_amount, 700.0)
        self.assertEqual(wizard.remaining_to_allocate, 0.0)
        wizard.action_confirm()

        self.assertEqual(request.state, "committed")
        self.assertEqual(request.shortfall_type, "budget_line")

        self.activity_a.invalidate_recordset()
        self.activity_b.invalidate_recordset()
        self.assertEqual(self.activity_a.available_amount, 0.0)
        self.assertEqual(self.activity_b.available_amount, 1700.0)

        commitments = request.commitment_ids.filtered(lambda c: c.state == "confirmed")
        self.assertEqual(len(commitments), 2)
        by_activity = {c.activity_id: c.amount for c in commitments}
        self.assertEqual(by_activity[self.activity_a], 700.0)
        self.assertEqual(by_activity[self.activity_b], 300.0)
        # Both legs are still against the SAME budget line - only the
        # activity axis was split, not the financial one.
        self.assertTrue(all(c.budget_line_id == self.line for c in commitments))

    def test_split_activity_line_onchange_autofills_capped_amount(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity_a)
        self._confirm_real_price(request, 1000.0)
        request.action_commit()

        activity_c = self.env["arcs.activity"].create({
            "name": "Workshop C", "project_id": self.project.id,
            "date_start": "2026-07-01", "date_end": "2026-09-30", "planned_cost": 120.0})
        activity_c.action_submit()
        activity_c.action_approve()

        wizard = self.env["arcs.spend.request.activity.split.wizard"].with_context(
            default_request_id=request.id).create({})
        self.assertEqual(wizard.primary_amount, 700.0)
        self.assertEqual(wizard.remaining_to_allocate, 300.0)

        form = Form(wizard)
        with form.line_ids.new() as line:
            line.activity_id = activity_c
            self.assertEqual(line.amount, 120.0)  # capped at activity_c's own available
        form.save()
        wizard.invalidate_recordset()
        self.assertEqual(wizard.remaining_to_allocate, 180.0)

        form = Form(wizard)
        with form.line_ids.new() as line:
            line.activity_id = self.activity_b
            self.assertEqual(line.amount, 180.0)  # picks up exactly what's left
        form.save()
        wizard.invalidate_recordset()
        self.assertEqual(wizard.remaining_to_allocate, 0.0)

    def test_reject_after_activity_split_releases_all_activities(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity_a)
        self._confirm_real_price(request, 1000.0)
        request.action_commit()

        wizard = self.env["arcs.spend.request.activity.split.wizard"].with_context(
            default_request_id=request.id).create({
                "reference": "MEMO-ACT-SPLIT-0002",
                "attachment_ids": [(6, 0, self.attachment.ids)],
                "line_ids": [(0, 0, {"activity_id": self.activity_b.id, "amount": 300.0})],
            })
        wizard.action_confirm()
        request.action_reject()

        self.activity_a.invalidate_recordset()
        self.activity_b.invalidate_recordset()
        self.assertEqual(self.activity_a.available_amount, 700.0)
        self.assertEqual(self.activity_b.available_amount, 2000.0)
