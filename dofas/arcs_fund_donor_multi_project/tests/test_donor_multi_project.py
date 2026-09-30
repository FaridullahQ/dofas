from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsDonorMultiProject(TransactionCase):
    """Covers the grant-level sibling-sharing check (independent of and
    additional to the existing Program-level one), the project-required
    guard, the project-ceiling hard stop, the closure guard, and confirms
    every other funding model - and the untouched Program-level sharing
    logic - is completely unaffected."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.plan = cls.env["account.analytic.plan"].create({"name": "ARCS Grants DMP"})
        cls.company.arcs_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme DMP", "code": "ARCSDM600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing DMP", "code": "ARCSDM200", "account_type": "liability_current"})
        cls.exp_journal = cls.env["account.journal"].create(
            {"name": "ARCS DMP", "type": "general", "code": "ARCSDMX", "company_id": cls.company.id})
        cls.company.arcs_expense_journal_id = cls.exp_journal
        cls.company.arcs_expense_clearing_account_id = cls.clearing

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "Big Foundation", "code": "BF-DMP", "donor_type": "foundation"})

    def _grant(self, funding_model="donor_multi_project", amount=10000.0):
        return self.env["arcs.grant"].create({
            "name": "Multi-Project Grant", "grant_number": "GR-DMP-%s" % funding_model,
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

    def _project(self, grant, planned_cost, code_suffix):
        return self.env["arcs.project"].create({
            "name": "Project %s" % code_suffix, "code": "DMP-%s-%s" % (grant.id, code_suffix),
            "grant_id": grant.id, "date_start": "2026-01-01", "date_end": "2026-12-31",
            "planned_cost": planned_cost,
        })

    # ------------------------------------------------------------------ tests
    def test_sibling_projects_cannot_exceed_grant_approved_amount(self):
        grant = self._grant(amount=1000.0)
        self._budget_line(grant)
        self._activate_grant(grant)
        self._project(grant, 600.0, "A")
        with self.assertRaises(ValidationError):
            self._project(grant, 500.0, "B")  # 600 + 500 = 1100 > 1000

        proj_b = self._project(grant, 400.0, "B")  # 600 + 400 = 1000, exactly fits
        self.assertEqual(proj_b.planned_cost, 400.0)

    def test_expense_requires_project_on_this_funding_model(self):
        grant = self._grant()
        line = self._budget_line(grant)
        self._activate_grant(grant)
        self._project(grant, 500.0, "A")
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        with self.assertRaises(UserError):
            exp.action_submit()

    def test_expense_blocked_beyond_project_ceiling(self):
        grant = self._grant()
        line = self._budget_line(grant)
        self._activate_grant(grant)
        project = self._project(grant, 500.0, "A")
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id, "project_id": project.id,
            "account_id": self.exp_acc.id, "amount": 800.0, "date": "2026-01-15"})
        exp.action_submit()
        with self.assertRaises(UserError):
            exp.action_approve()  # 800 > this project's own 500, even though budget line has 10,000

    def test_expense_within_project_ceiling_succeeds(self):
        grant = self._grant()
        line = self._budget_line(grant)
        self._activate_grant(grant)
        project = self._project(grant, 500.0, "A")
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id, "project_id": project.id,
            "account_id": self.exp_acc.id, "amount": 300.0, "date": "2026-01-15"})
        exp.action_submit()
        exp.action_approve()
        self.assertEqual(exp.state, "approved")
        project.invalidate_recordset()
        self.assertAlmostEqual(project.available_amount, 200.0)

    def test_project_from_another_grant_rejected(self):
        grant1 = self._grant()
        grant2 = self.env["arcs.grant"].create({
            "name": "Other Grant", "grant_number": "GR-DMP-2", "donor_id": self.donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "donor_multi_project",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 10000.0})
        line1 = self._budget_line(grant1)
        self._budget_line(grant2)
        self._activate_grant(grant1)
        self._activate_grant(grant2)
        project2 = self._project(grant2, 500.0, "X")

        exp = self.env["arcs.expense"].create({
            "grant_id": grant1.id, "budget_line_id": line1.id, "project_id": project2.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()
        with self.assertRaises(UserError):
            exp.action_approve()

    def test_closure_blocked_while_project_not_closed(self):
        grant = self._grant()
        self._budget_line(grant)
        self._activate_grant(grant)
        self._project(grant, 500.0, "A")
        with self.assertRaises(UserError):
            grant.action_close()

    def test_closure_succeeds_once_projects_closed(self):
        grant = self._grant()
        self._budget_line(grant)
        self._activate_grant(grant)
        project = self._project(grant, 500.0, "A")
        project.action_activate()
        project.action_close()
        self.assertEqual(project.state, "closed")
        grant.action_close()
        self.assertEqual(grant.state, "closed")

    def test_other_funding_models_unaffected(self):
        grant = self._grant(funding_model="grant_based")
        line = self._budget_line(grant)
        self._activate_grant(grant)
        # Sibling projects on a grant_based grant are NOT checked against the
        # grant's approved amount by this module - unlimited by this rule.
        self._project(grant, 8000.0, "A")
        self._project(grant, 8000.0, "B")  # would be blocked on donor_multi_project; fine here

        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()  # no project required
        exp.action_approve()
        self.assertEqual(exp.state, "approved")
        grant.action_close()  # no project-closure requirement either
        self.assertEqual(grant.state, "closed")

    def test_program_level_sharing_still_works_unchanged(self):
        """This module adds an independent, additional grant-level check -
        it must not touch or weaken the pre-existing Program-level sibling
        sharing check for projects that use a Program."""
        grant = self._grant(funding_model="grant_based")  # Program-level check is model-agnostic
        self._budget_line(grant)
        self._activate_grant(grant)
        program = self.env["arcs.program"].create({
            "name": "Shared Program", "code": "PROG-DMP-1", "planned_cost": 1000.0})
        self.env["arcs.project"].create({
            "name": "P1", "code": "PROG-DMP-P1", "grant_id": grant.id, "program_id": program.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31", "planned_cost": 700.0})
        with self.assertRaises(ValidationError):
            self.env["arcs.project"].create({
                "name": "P2", "code": "PROG-DMP-P2", "grant_id": grant.id,
                "program_id": program.id, "date_start": "2026-01-01",
                "date_end": "2026-12-31", "planned_cost": 400.0})  # 700+400 > program's 1000
