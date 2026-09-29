from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsEarmarked(TransactionCase):
    """Covers the activity-required guard, the activity-ceiling hard stop
    (unconditional regardless of the global toggle), the closure guard, and
    confirms every other funding model - including the global toggle's own
    normal optional behavior - is completely unaffected."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.plan = cls.env["account.analytic.plan"].create({"name": "ARCS Grants EM"})
        cls.company.arcs_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme EM", "code": "ARCSEM600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing EM", "code": "ARCSEM200", "account_type": "liability_current"})
        cls.exp_journal = cls.env["account.journal"].create(
            {"name": "ARCS EM", "type": "general", "code": "ARCSEMX", "company_id": cls.company.id})
        cls.company.arcs_expense_journal_id = cls.exp_journal
        cls.company.arcs_expense_clearing_account_id = cls.clearing
        # Deliberately left OFF - proves Earmarked enforcement doesn't depend on it.
        cls.company.arcs_enforce_program_ceilings = False

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "GFATM", "code": "GFATM-EM", "donor_type": "multilateral"})

    def _grant(self, funding_model="earmarked", amount=10000.0):
        return self.env["arcs.grant"].create({
            "name": "Health EM", "grant_number": "GR-EM-%s" % funding_model,
            "donor_id": self.donor.id, "currency_id": self.company.currency_id.id,
            "funding_model": funding_model, "date_start": "2026-01-01",
            "date_end": "2026-12-31", "approved_amount": amount})

    def _budget_line(self, grant, amount=10000.0):
        budget = self.env["arcs.budget"].create({"grant_id": grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Activities",
            "account_ids": [(6, 0, self.exp_acc.ids)], "planned_amount": amount})
        budget.action_approve()
        return line

    def _activate_grant(self, grant):
        grant.action_submit()
        self.env["ir.attachment"].create({
            "name": "doc.pdf", "datas": b"ZHVtbXk=",
            "res_model": "arcs.grant", "res_id": grant.id})
        if "arcs.grant.agreement" in self.env:
            agr = self.env["arcs.grant.agreement"].create({
                "grant_id": grant.id, "signed_date": "2026-01-01"})
            self.env["ir.attachment"].create({
                "name": "agreement.pdf", "datas": b"ZHVtbXk=",
                "res_model": "arcs.grant.agreement", "res_id": agr.id})
            agr.action_activate()
        grant.action_approve()
        grant.action_activate()

    def _project_and_activity(self, grant, planned_cost=500.0):
        project = self.env["arcs.project"].create({
            "name": "WASH Project", "code": "WASH-EM-%s" % grant.id, "grant_id": grant.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31"})
        activity = self.env["arcs.activity"].create({
            "name": "Well Drilling", "project_id": project.id,
            "date_start": "2026-01-01", "date_end": "2026-06-30",
            "planned_cost": planned_cost,
        })
        return project, activity

    # ------------------------------------------------------------------ tests
    def test_expense_requires_activity_on_earmarked_grant(self):
        grant = self._grant()
        line = self._budget_line(grant)
        self._activate_grant(grant)
        self._project_and_activity(grant)
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        with self.assertRaises(UserError):
            exp.action_submit()

    def test_activity_ceiling_enforced_even_with_global_toggle_off(self):
        grant = self._grant()
        line = self._budget_line(grant)
        self._activate_grant(grant)
        project, activity = self._project_and_activity(grant, planned_cost=500.0)
        self.assertFalse(self.company.arcs_enforce_program_ceilings)  # confirm precondition

        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id, "activity_id": activity.id,
            "account_id": self.exp_acc.id, "amount": 800.0, "date": "2026-01-15"})
        exp.action_submit()
        with self.assertRaises(UserError):
            exp.action_approve()  # 800 > activity's 500, even though the budget line has 10,000

    def test_expense_within_activity_ceiling_succeeds(self):
        grant = self._grant()
        line = self._budget_line(grant)
        self._activate_grant(grant)
        project, activity = self._project_and_activity(grant, planned_cost=500.0)
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id, "activity_id": activity.id,
            "account_id": self.exp_acc.id, "amount": 300.0, "date": "2026-01-15"})
        exp.action_submit()
        exp.action_approve()
        self.assertEqual(exp.state, "approved")
        activity.invalidate_recordset()
        self.assertAlmostEqual(activity.available_amount, 200.0)

    def test_activity_from_another_grant_rejected(self):
        grant1 = self._grant(amount=10000.0)
        grant2 = self.env["arcs.grant"].create({
            "name": "Health EM2", "grant_number": "GR-EM-2", "donor_id": self.donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "earmarked",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 10000.0})
        line1 = self._budget_line(grant1)
        self._budget_line(grant2)
        self._activate_grant(grant1)
        self._activate_grant(grant2)
        _, activity2 = self._project_and_activity(grant2, planned_cost=500.0)

        exp = self.env["arcs.expense"].create({
            "grant_id": grant1.id, "budget_line_id": line1.id, "activity_id": activity2.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()
        with self.assertRaises(UserError):
            exp.action_approve()

    def test_closure_blocked_while_project_not_closed(self):
        grant = self._grant()
        self._budget_line(grant)
        self._activate_grant(grant)
        self._project_and_activity(grant)
        with self.assertRaises(UserError):
            grant.action_close()

    def test_closure_succeeds_once_project_closed(self):
        grant = self._grant()
        self._budget_line(grant)
        self._activate_grant(grant)
        project, activity = self._project_and_activity(grant)
        project.action_activate()
        activity.action_submit()
        activity.action_approve()
        activity.action_implement()
        activity.action_close()
        project.action_close()
        self.assertEqual(project.state, "closed")
        grant.action_close()
        self.assertEqual(grant.state, "closed")

    def test_other_funding_models_unaffected_activity_stays_optional(self):
        grant = self._grant(funding_model="grant_based")
        line = self._budget_line(grant)
        self._activate_grant(grant)
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()  # no activity required
        exp.action_approve()
        self.assertEqual(exp.state, "approved")
        grant.action_close()  # no project/activity closure requirement either
        self.assertEqual(grant.state, "closed")

    def test_global_toggle_still_governs_non_earmarked_grants_normally(self):
        """Turning the global ceiling toggle ON should still do nothing extra
        for a non-Earmarked grant unless arcs_budget/arcs_expense themselves
        call get_available_locked() - this module never touches that
        toggle's own behavior for any other funding model."""
        self.company.arcs_enforce_program_ceilings = True
        grant = self._grant(funding_model="grant_based")
        line = self._budget_line(grant)
        self._activate_grant(grant)
        project, activity = self._project_and_activity(grant, planned_cost=50.0)
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id, "activity_id": activity.id,
            "account_id": self.exp_acc.id, "amount": 500.0, "date": "2026-01-15"})
        exp.action_submit()
        exp.action_approve()  # still succeeds - this module adds no check for grant_based
        self.assertEqual(exp.state, "approved")
