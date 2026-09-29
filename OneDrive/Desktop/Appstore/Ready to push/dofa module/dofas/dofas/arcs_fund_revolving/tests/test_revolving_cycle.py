import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsRevolvingCycle(TransactionCase):
    """Simulates the full 8-step Revolving Fund cycle end to end - commitment,
    fund transfer, utilization (including the cash-basis hard stop), the
    utilization report, replenishment request, closure, and opening the next
    cycle - and confirms every other funding model is left untouched."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # Accounting setup shared by expenses and fund receipts.
        cls.plan = cls.env["account.analytic.plan"].create({"name": "ARCS Grants RF"})
        cls.company.arcs_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme RF", "code": "ARCSRF600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing RF", "code": "ARCSRF200", "account_type": "liability_current"})
        cls.exp_journal = cls.env["account.journal"].create(
            {"name": "ARCS RF", "type": "general", "code": "ARCSRFX", "company_id": cls.company.id})
        cls.company.arcs_expense_journal_id = cls.exp_journal
        cls.company.arcs_expense_clearing_account_id = cls.clearing

        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "ARCS RF Bank", "type": "bank", "code": "ARCSRFB", "company_id": cls.company.id})
        cls.income_acc = cls.env["account.account"].create({
            "name": "Donor Income RF", "code": "ARCSRF100",
            "account_type": "asset_cash"})

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-RF", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health RF", "grant_number": "GR-RF-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "revolving_fund",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        cls.budget = cls.env["arcs.budget"].create({"grant_id": cls.grant.id})
        cls.line = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Activities",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 1000.0})
        cls.budget.action_approve()
        cls.grant.action_submit()
        cls.grant.action_approve()
        cls.grant.action_activate()

    def _attachment(self, res_model, res_id):
        return self.env["ir.attachment"].create({
            "name": "proof.pdf", "datas": base64.b64encode(b"dummy"),
            "res_model": res_model, "res_id": res_id,
        })

    def _make_cycle(self, amount=250.0):
        cycle = self.env["arcs.revolving.cycle"].create({
            "grant_id": self.grant.id, "amount_committed": amount,
            "description": "Q1 tranche",
            "allocation_line_ids": [(0, 0, {
                "budget_line_id": self.line.id, "amount": amount})],
        })
        return cycle

    def _fund(self, cycle):
        receipt = self.env["arcs.fund.receipt"].create({
            "grant_id": self.grant.id, "currency_id": self.company.currency_id.id,
            "amount": cycle.amount_committed, "received_date": "2026-01-10",
            "bank_voucher_ref": "VCH-%s" % cycle.id,
            "journal_id": self.bank_journal.id,
            "receivable_account_id": self.income_acc.id,
            "revolving_cycle_id": cycle.id,
        })
        self._attachment("arcs.fund.receipt", receipt.id)
        receipt.action_post()
        return receipt

    def _expense(self, cycle, amount):
        return self.env["arcs.expense"].create({
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "account_id": self.exp_acc.id, "amount": amount, "date": "2026-01-15",
            "revolving_cycle_id": cycle.id,
        })

    # ------------------------------------------------------------------ tests
    def test_open_next_cycle_bootstraps_with_zero_amount(self):
        """Regression test: creating the next cycle deliberately starts it at
        Amount Committed = 0 (pending the user's real figure) - this must not
        trip the DB-level positivity check, only action_commit() should."""
        cycle = self._make_cycle(200.0)
        cycle.action_commit()
        self._fund(cycle)
        exp = self._expense(cycle, 200.0)
        exp.action_submit()
        exp.action_approve()
        report = self.env["arcs.donor.report"].create({
            "grant_id": self.grant.id, "report_type": "fund_utilization",
            "revolving_cycle_id": cycle.id,
        })
        self._attachment("arcs.donor.report", report.id)
        report.action_submit()
        report.action_approve()
        cycle.action_request_replenishment()
        cycle.action_close()

        next_action = cycle.action_create_next_cycle()
        next_cycle = self.env["arcs.revolving.cycle"].browse(next_action["res_id"])
        self.assertEqual(next_cycle.amount_committed, 0.0)
        self.assertEqual(next_cycle.allocation_line_ids.amount, 0.0)
        # And committing it while still at zero must be blocked cleanly.
        with self.assertRaises(UserError):
            next_cycle.action_commit()

    def test_full_cycle_end_to_end(self):
        cycle = self._make_cycle(250.0)
        self.assertEqual(cycle.state, "draft")
        self.assertEqual(cycle.sequence_no, 1)
        self.assertTrue(cycle.name.startswith("COM-"))

        cycle.action_commit()
        self.assertEqual(cycle.state, "committed")

        self._fund(cycle)
        self.assertEqual(cycle.state, "utilizing")
        self.assertAlmostEqual(cycle.amount_available, 250.0)

        exp = self._expense(cycle, 150.0)
        exp.action_submit()
        exp.action_approve()
        cycle.invalidate_recordset()
        self.assertAlmostEqual(cycle.amount_spent, 150.0)
        self.assertAlmostEqual(cycle.amount_available, 100.0)

        report = self.env["arcs.donor.report"].create({
            "grant_id": self.grant.id, "report_type": "fund_utilization",
            "revolving_cycle_id": cycle.id,
        })
        self._attachment("arcs.donor.report", report.id)
        report.action_submit()
        self.assertEqual(cycle.state, "reporting")
        report.action_approve()

        cycle.action_request_replenishment()
        self.assertEqual(cycle.state, "replenishment_requested")
        self.assertAlmostEqual(cycle.replenishment_amount_requested, 150.0)

        cycle.action_close()
        self.assertEqual(cycle.state, "closed")

        next_action = cycle.action_create_next_cycle()
        next_cycle = self.env["arcs.revolving.cycle"].browse(next_action["res_id"])
        self.assertEqual(next_cycle.state, "draft")
        self.assertEqual(next_cycle.sequence_no, 2)
        self.assertEqual(next_cycle.allocation_line_ids.budget_line_id, self.line)

    def test_cash_basis_hard_stop_per_cycle(self):
        cycle = self._make_cycle(200.0)
        cycle.action_commit()
        self._fund(cycle)
        exp = self._expense(cycle, 250.0)
        exp.action_submit()
        with self.assertRaises(UserError):
            exp.action_approve()

    def test_expense_requires_cycle_on_revolving_grant(self):
        cycle = self._make_cycle(200.0)
        cycle.action_commit()
        self._fund(cycle)
        exp = self.env["arcs.expense"].create({
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "account_id": self.exp_acc.id, "amount": 50.0, "date": "2026-01-15",
        })
        with self.assertRaises(UserError):
            exp.action_submit()

    def test_only_one_open_cycle_per_grant(self):
        cycle1 = self._make_cycle(200.0)
        cycle1.action_commit()
        with self.assertRaises(ValidationError):
            self._make_cycle(200.0).action_commit()

    def test_cumulative_commitment_cannot_exceed_grant(self):
        # Fully close one 600-committed cycle (closed cycles still count
        # toward the cumulative total - only cancelled ones don't), then
        # confirm a second cycle that would push the total past the grant's
        # Approved Amount (1000.0) is rejected.
        cycle1 = self._make_cycle(600.0)
        cycle1.action_commit()
        self._fund(cycle1)
        exp = self._expense(cycle1, 600.0)
        exp.action_submit()
        exp.action_approve()
        report = self.env["arcs.donor.report"].create({
            "grant_id": self.grant.id, "report_type": "fund_utilization",
            "revolving_cycle_id": cycle1.id,
        })
        self._attachment("arcs.donor.report", report.id)
        report.action_submit()
        report.action_approve()
        cycle1.action_request_replenishment()
        cycle1.action_close()

        with self.assertRaises(ValidationError):
            self.env["arcs.revolving.cycle"].create({
                "grant_id": self.grant.id, "amount_committed": 500.0,
                "allocation_line_ids": [(0, 0, {
                    "budget_line_id": self.line.id, "amount": 500.0})],
            })

    def test_grant_closure_blocked_while_cycle_open(self):
        self._make_cycle(200.0).action_commit()
        with self.assertRaises(UserError):
            self.grant.action_close()

    def test_other_funding_models_unaffected(self):
        """A grant_based grant must never require a revolving cycle, and its
        closure must never be blocked by the new hook."""
        grant2 = self.env["arcs.grant"].create({
            "name": "Health GB", "grant_number": "GR-GB-1", "donor_id": self.donor.id,
            "currency_id": self.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        budget2 = self.env["arcs.budget"].create({"grant_id": grant2.id})
        line2 = self.env["arcs.budget.line"].create({
            "budget_id": budget2.id, "name": "Activities",
            "account_ids": [(6, 0, self.exp_acc.ids)], "planned_amount": 1000.0})
        budget2.action_approve()
        grant2.action_submit(); grant2.action_approve(); grant2.action_activate()

        exp = self.env["arcs.expense"].create({
            "grant_id": grant2.id, "budget_line_id": line2.id,
            "account_id": self.exp_acc.id, "amount": 100.0, "date": "2026-01-15"})
        exp.action_submit()
        exp.action_approve()  # must not require a revolving_cycle_id
        self.assertEqual(exp.state, "approved")
        grant2.action_close()  # must not be blocked by the revolving-fund hook
        self.assertEqual(grant2.state, "closed")
