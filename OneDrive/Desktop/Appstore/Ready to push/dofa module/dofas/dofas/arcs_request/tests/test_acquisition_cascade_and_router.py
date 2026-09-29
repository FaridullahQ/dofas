import base64

from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsAcquisitionCascadeAndRouter(TransactionCase):
    """Selecting an Activity on an acquisition must cascade upward and fill
    in Project, Program, and (best-effort) Budget Line - not require the
    Budget Line to be picked first. And once flagged Insufficient Funds,
    every recovery option must be reachable regardless of which axis
    (budget line or activity) actually triggered it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "ARCSCASC600", "account_type": "expense"})

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-CASC", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-CASC-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.budget = cls.env["arcs.budget"].create({"grant_id": cls.grant.id})
        cls.line = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line A",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 5000.0})
        cls.other_line = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line B",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 5000.0})
        cls.budget.action_approve()
        cls.grant.action_submit()
        cls.grant.action_approve()
        cls.grant.action_activate()

        cls.program = cls.env["arcs.program"].create({
            "name": "Health Program", "code": "HEALTH-CASC",
            "budget_line_id": cls.line.id, "planned_cost": 3000.0})
        cls.project = cls.env["arcs.project"].create({
            "name": "Wash Unit", "code": "WASH-CASC-001", "grant_id": cls.grant.id,
            "program_id": cls.program.id, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "planned_cost": 2000.0})
        cls.activity = cls.env["arcs.activity"].create({
            "name": "Workshop", "project_id": cls.project.id,
            "date_start": "2026-01-01", "date_end": "2026-03-31", "planned_cost": 700.0})
        cls.activity.action_submit()
        cls.activity.action_approve()

        cls.vendor = cls.env["res.partner"].create({"name": "Acme Supplies"})
        cls.attachment = cls.env["ir.attachment"].create({
            "name": "quote.pdf", "datas": base64.b64encode(b"dummy quotation"),
        })

    # ================================================================ cascade

    def test_selecting_activity_first_cascades_project_program_budget_line(self):
        form = Form(self.env["arcs.spend.request"])
        form.activity_id = self.activity
        self.assertEqual(form.project_id, self.project)
        self.assertEqual(form.program_id, self.program)
        self.assertEqual(form.budget_line_id, self.line)  # from program.budget_line_id
        request = form.save()
        self.assertEqual(request.budget_line_id, self.line)

    def test_activity_budget_line_always_comes_from_its_program(self):
        """Activities have no budget_line_id of their own (arcs_program
        removed it - an Activity gets its budget-line context transitively
        through Project -> Program, never directly). Confirms the cascade
        always reflects whatever the activity's own Program currently
        points at."""
        self.program.budget_line_id = self.other_line.id
        form = Form(self.env["arcs.spend.request"])
        form.activity_id = self.activity
        self.assertEqual(form.budget_line_id, self.other_line)

    def test_selecting_project_first_cascades_program(self):
        form = Form(self.env["arcs.spend.request"])
        form.project_id = self.project
        self.assertEqual(form.program_id, self.program)
        self.assertEqual(form.budget_line_id, self.line)

    def test_selecting_program_first_fills_budget_line(self):
        form = Form(self.env["arcs.spend.request"])
        form.program_id = self.program
        self.assertEqual(form.budget_line_id, self.line)

    def test_changing_budget_line_to_mismatched_grant_clears_project_activity(self):
        other_grant = self.env["arcs.grant"].create({
            "name": "Other", "grant_number": "GR-CASC-2", "donor_id": self.donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 2000.0})
        other_budget = self.env["arcs.budget"].create({"grant_id": other_grant.id})
        other_line = self.env["arcs.budget.line"].create({
            "budget_id": other_budget.id, "name": "Other Line",
            "account_ids": [(6, 0, self.exp_acc.ids)], "planned_amount": 2000.0})
        other_budget.action_approve()

        form = Form(self.env["arcs.spend.request"])
        form.activity_id = self.activity  # cascades project/program/budget_line
        self.assertEqual(form.project_id, self.project)
        form.budget_line_id = other_line  # deliberately switch to a different grant
        self.assertFalse(form.project_id)
        self.assertFalse(form.activity_id)

    def test_activity_cascade_does_not_self_wipe(self):
        """The core regression this feature had to avoid: _onchange_activity
        setting budget_line_id (same grant, by construction) must not
        trigger _onchange_budget_line's mismatch guard and wipe the very
        project/activity it just set."""
        form = Form(self.env["arcs.spend.request"])
        form.activity_id = self.activity
        self.assertEqual(form.activity_id, self.activity)
        self.assertEqual(form.project_id, self.project)
        self.assertEqual(form.budget_line_id, self.line)

    # ================================================================ router

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

    def test_router_wizard_blocked_outside_insufficient_funds(self):
        request = self._submitted_request(1000.0, self.activity)
        with self.assertRaises(UserError):
            request.action_open_insufficient_funds_wizard()

    def test_router_wizard_delegates_to_every_action_regardless_of_shortfall_type(self):
        self.company.arcs_enforce_program_ceilings = True
        request = self._submitted_request(1000.0, self.activity)  # activity only has 700
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        self.assertEqual(request.state, "insufficient_funds")
        self.assertEqual(request.shortfall_type, "activity")

        action = request.action_open_insufficient_funds_wizard()
        router = self.env["arcs.spend.request.insufficient.funds.wizard"].with_context(
            action["context"]).create({})
        self.assertEqual(router.request_id, request)
        self.assertEqual(router.shortfall_type, "activity")

        # Every recovery path is reachable even though the shortfall was on
        # the activity axis, not the budget line - the router doesn't gate
        # by shortfall_type, Finance chooses.
        for method in (
            "action_choose_different_budget_line",
            "action_open_split_wizard",
            "action_request_budget_transfer",
            "action_request_donor_funding",
            "action_choose_different_activity",
            "action_open_activity_split_wizard",
            "action_reset_draft_wizard",
        ):
            result = getattr(router, method)()
            self.assertIn(result.get("type"), ("ir.actions.act_window",))

    def test_budget_line_shortfall_can_still_reach_activity_recovery(self):
        """Confirms the reverse direction: a budget-line shortfall doesn't
        block access to the activity-axis recovery tools either."""
        request = self._submitted_request(6000.0, self.activity)  # exceeds line's 5000
        self._confirm_real_price(request, 6000.0)
        request.action_commit()
        self.assertEqual(request.shortfall_type, "budget_line")

        # No longer raises - shortfall_type guards were removed.
        request.action_choose_different_activity()
        request.action_open_activity_split_wizard()
