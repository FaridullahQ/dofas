from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsMultiDonorProject(TransactionCase):
    """Covers the full shared-cost lifecycle, the guarantees that make
    double-charging structurally impossible, the various validation guards,
    and confirms every other funding model is completely unaffected."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.plan = cls.env["account.analytic.plan"].create({"name": "ARCS Grants MD"})
        cls.company.arcs_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme MD", "code": "ARCSMD600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing MD", "code": "ARCSMD200", "account_type": "liability_current"})
        cls.exp_journal = cls.env["account.journal"].create(
            {"name": "ARCS MD", "type": "general", "code": "ARCSMDX", "company_id": cls.company.id})
        cls.company.arcs_expense_journal_id = cls.exp_journal
        cls.company.arcs_expense_clearing_account_id = cls.clearing

        cls.donor_a = cls.env["arcs.donor"].create(
            {"name": "Donor A", "code": "MD-A", "donor_type": "foundation"})
        cls.donor_b = cls.env["arcs.donor"].create(
            {"name": "Donor B", "code": "MD-B", "donor_type": "foundation"})

    def _grant(self, donor, name):
        return self.env["arcs.grant"].create({
            "name": name, "grant_number": "GR-MD-%s" % name, "donor_id": donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "multi_donor",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 10000.0})

    def _budget_line(self, grant):
        budget = self.env["arcs.budget"].create({"grant_id": grant.id})
        line = self.env["arcs.budget.line"].create({
            "budget_id": budget.id, "name": "Shared Activities",
            "account_ids": [(6, 0, self.exp_acc.ids)], "planned_amount": 10000.0})
        budget.action_approve()
        return line

    def _activate_grant(self, grant):
        grant.action_submit()
        self.env["ir.attachment"].create({
            "name": "doc.pdf", "datas": b"ZHVtbXk=",
            "res_model": "arcs.grant", "res_id": grant.id})
        if "arcs.grant.agreement" in self.env:
            # arcs_grant_governance is installed alongside this module (as it
            # will be in the real ARCS environment) - a multi_donor grant is
            # is_restricted by definition, so it needs an active Agreement
            # Version before Approve succeeds, exactly like every other
            # restricted funding model. Reused, not rebuilt here.
            agr = self.env["arcs.grant.agreement"].create({
                "grant_id": grant.id, "signed_date": "2026-01-01"})
            self.env["ir.attachment"].create({
                "name": "agreement.pdf", "datas": b"ZHVtbXk=",
                "res_model": "arcs.grant.agreement", "res_id": agr.id})
            agr.action_activate()
        grant.action_approve()
        grant.action_activate()

    def _setup_project(self, pct_a=60.0, pct_b=40.0):
        grant_a = self._grant(self.donor_a, "A")
        grant_b = self._grant(self.donor_b, "B")
        line_a = self._budget_line(grant_a)
        line_b = self._budget_line(grant_b)
        self._activate_grant(grant_a)
        self._activate_grant(grant_b)
        project = self.env["arcs.multi.donor.project"].create({"name": "Shared WASH Project"})
        self.env["arcs.multi.donor.project.member"].create({
            "project_id": project.id, "grant_id": grant_a.id, "allocation_pct": pct_a})
        self.env["arcs.multi.donor.project.member"].create({
            "project_id": project.id, "grant_id": grant_b.id, "allocation_pct": pct_b})
        return project, grant_a, grant_b, line_a, line_b

    # ------------------------------------------------------------------ tests
    def test_project_activation_requires_100_percent_and_two_members(self):
        project, grant_a, grant_b, _, _ = self._setup_project(pct_a=60.0, pct_b=30.0)
        with self.assertRaises(UserError):
            project.action_activate()  # only sums to 90%

        member_b = project.member_ids.filtered(lambda m: m.grant_id == grant_b)
        member_b.allocation_pct = 40.0
        project.action_activate()
        self.assertEqual(project.state, "active")

    def test_single_member_project_cannot_activate(self):
        grant_a = self._grant(self.donor_a, "Solo")
        self._budget_line(grant_a)
        self._activate_grant(grant_a)
        project = self.env["arcs.multi.donor.project"].create({"name": "Solo Project"})
        self.env["arcs.multi.donor.project.member"].create({
            "project_id": project.id, "grant_id": grant_a.id, "allocation_pct": 100.0})
        with self.assertRaises(UserError):
            project.action_activate()

    def test_full_shared_cost_lifecycle_sums_exactly(self):
        project, grant_a, grant_b, line_a, line_b = self._setup_project(60.0, 40.0)
        project.action_activate()

        cost = self.env["arcs.multi.donor.shared.cost"].create({
            "project_id": project.id, "date": "2026-02-01",
            "currency_id": self.company.currency_id.id, "total_amount": 1000.0,
            "description": "Shared logistics",
        })
        self.assertTrue(cost.name.startswith("SC-"))

        cost.action_generate_default_split()
        self.assertEqual(len(cost.split_line_ids), 2)
        line_for_a = cost.split_line_ids.filtered(lambda l: l.grant_id == grant_a)
        line_for_b = cost.split_line_ids.filtered(lambda l: l.grant_id == grant_b)
        self.assertAlmostEqual(line_for_a.allocation_pct, 60.0)
        self.assertAlmostEqual(line_for_a.amount, 600.0)
        self.assertAlmostEqual(line_for_b.amount, 400.0)

        line_for_a.budget_line_id = line_a.id
        line_for_a.account_id = self.exp_acc.id
        line_for_b.budget_line_id = line_b.id
        line_for_b.account_id = self.exp_acc.id

        cost.action_split()
        self.assertEqual(cost.state, "split")

        # The core guarantee: the two generated expenses' amounts sum to
        # EXACTLY the original total - never the full amount charged twice.
        generated = cost.split_line_ids.mapped("expense_id")
        self.assertEqual(len(generated), 2)
        self.assertAlmostEqual(sum(generated.mapped("amount")), 1000.0)
        for exp in generated:
            self.assertLess(exp.amount, 1000.0)  # neither one got the full amount
            self.assertEqual(exp.shared_cost_id, cost)

        for exp in generated:
            exp.action_submit()
            exp.action_approve()
            exp.action_post()

        cost.action_mark_posted()
        self.assertEqual(cost.state, "posted")

    def test_split_blocked_if_lines_do_not_sum_to_total(self):
        project, grant_a, grant_b, line_a, line_b = self._setup_project(60.0, 40.0)
        project.action_activate()
        cost = self.env["arcs.multi.donor.shared.cost"].create({
            "project_id": project.id, "date": "2026-02-01",
            "currency_id": self.company.currency_id.id, "total_amount": 1000.0,
        })
        cost.action_generate_default_split()
        line_for_a = cost.split_line_ids.filtered(lambda l: l.grant_id == grant_a)
        line_for_a.allocation_pct = 50.0  # now sums to 90%, not 100%
        line_for_a.budget_line_id = line_a.id
        line_for_a.account_id = self.exp_acc.id
        (cost.split_line_ids - line_for_a).write({
            "budget_line_id": line_b.id, "account_id": self.exp_acc.id})
        with self.assertRaises(UserError):
            cost.action_split()

    def test_per_cost_override_of_project_split_is_allowed(self):
        """The project's own split is 60/40, but this specific shared cost
        was agreed 50/50 - the recommended design explicitly allows this."""
        project, grant_a, grant_b, line_a, line_b = self._setup_project(60.0, 40.0)
        project.action_activate()
        cost = self.env["arcs.multi.donor.shared.cost"].create({
            "project_id": project.id, "date": "2026-02-01",
            "currency_id": self.company.currency_id.id, "total_amount": 800.0,
        })
        cost.action_generate_default_split()
        for line in cost.split_line_ids:
            line.allocation_pct = 50.0
            line.budget_line_id = line_a.id if line.grant_id == grant_a else line_b.id
            line.account_id = self.exp_acc.id
        cost.action_split()
        self.assertAlmostEqual(cost.split_total_amount, 800.0)
        for line in cost.split_line_ids:
            self.assertAlmostEqual(line.amount, 400.0)

    def test_reset_to_draft_blocked_once_shared_cost_exists(self):
        project, grant_a, grant_b, line_a, line_b = self._setup_project(60.0, 40.0)
        project.action_activate()
        self.env["arcs.multi.donor.shared.cost"].create({
            "project_id": project.id, "date": "2026-02-01",
            "currency_id": self.company.currency_id.id, "total_amount": 500.0,
        })
        with self.assertRaises(UserError):
            project.action_reset_draft()

    def test_member_percentage_locked_once_active(self):
        project, grant_a, grant_b, line_a, line_b = self._setup_project(60.0, 40.0)
        project.action_activate()
        member_a = project.member_ids.filtered(lambda m: m.grant_id == grant_a)
        with self.assertRaises(UserError):
            member_a.allocation_pct = 70.0

    def test_grant_cannot_join_two_open_projects(self):
        project1, grant_a, grant_b, _, _ = self._setup_project(60.0, 40.0)
        project2 = self.env["arcs.multi.donor.project"].create({"name": "Second Project"})
        self.env["arcs.multi.donor.project.member"].create({
            "project_id": project2.id, "grant_id": grant_b.id, "allocation_pct": 50.0})
        with self.assertRaises(ValidationError):
            self.env["arcs.multi.donor.project.member"].create({
                "project_id": project2.id, "grant_id": grant_a.id, "allocation_pct": 50.0})

    def test_other_funding_models_unaffected(self):
        grant = self.env["arcs.grant"].create({
            "name": "Health GB MD", "grant_number": "GR-MD-GB", "donor_id": self.donor_a.id,
            "currency_id": self.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        line = self._budget_line(grant)
        self._activate_grant(grant)
        exp = self.env["arcs.expense"].create({
            "grant_id": grant.id, "budget_line_id": line.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()
        exp.action_approve()
        self.assertEqual(exp.state, "approved")
        self.assertFalse(exp.shared_cost_id)
        self.assertFalse(grant.multi_donor_project_id)
