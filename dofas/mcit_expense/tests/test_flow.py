from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "mcit")
class TestMcitFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.plan = cls.env["account.analytic.plan"].create({"name": "MCIT Grants"})
        cls.company.mcit_default_analytic_plan_id = cls.plan
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "MCIT600", "account_type": "expense"})
        cls.clearing = cls.env["account.account"].create(
            {"name": "Clearing", "code": "MCIT200", "account_type": "liability_current"})
        cls.journal = cls.env["account.journal"].create(
            {"name": "MCIT", "type": "general", "code": "MCITX", "company_id": cls.company.id})
        cls.company.mcit_expense_journal_id = cls.journal
        cls.company.mcit_expense_clearing_account_id = cls.clearing

        cls.donor = cls.env["mcit.donor"].create(
            {"name": "UNDP", "code": "UNDP", "donor_type": "multilateral"})
        cls.grant = cls.env["mcit.grant"].create({
            "name": "Health", "grant_number": "GR-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 1000.0})
        cls.budget = cls.env["mcit.budget"].create({"grant_id": cls.grant.id})
        cls.line = cls.env["mcit.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Salaries",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 1000.0})
        cls.budget.action_approve()
        cls.grant.action_submit()
        cls.grant.action_approve()
        cls.grant.action_activate()

    def _exp(self, amount):
        return self.env["mcit.expense"].create({
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "account_id": self.exp_acc.id, "amount": amount, "date": "2026-06-01"})

    def test_full_loop_and_actual(self):
        e = self._exp(600.0)
        e.action_submit(); e.action_approve()
        self.assertEqual(e.commitment_id.state, "confirmed")
        e.action_post()
        self.assertEqual(e.state, "posted")
        self.assertEqual(e.move_id.state, "posted")
        self.assertEqual(e.commitment_id.state, "consumed")
        self.line.invalidate_recordset()
        self.assertAlmostEqual(self.line.actual_amount, 600.0)
        self.assertAlmostEqual(self.line.available_amount, 400.0)

    def test_hard_stop(self):
        e1 = self._exp(600.0); e1.action_submit(); e1.action_approve(); e1.action_post()
        e2 = self._exp(500.0); e2.action_submit()
        with self.assertRaises(UserError):
            e2.action_approve()

    def test_cancel_releases(self):
        e = self._exp(1000.0); e.action_submit(); e.action_approve()
        self.line.invalidate_recordset()
        self.assertAlmostEqual(self.line.available_amount, 0.0)
        e.action_cancel()
        self.assertEqual(e.commitment_id.state, "released")
        self.line.invalidate_recordset()
        self.assertAlmostEqual(self.line.available_amount, 1000.0)

    def test_cash_availability(self):
        self.grant.enforce_cash_availability = True
        e = self._exp(100.0); e.action_submit()
        with self.assertRaises(UserError):
            e.action_approve()  # no funds received yet
        self.env["mcit.fund.receipt"].create({
            "grant_id": self.grant.id, "currency_id": self.company.currency_id.id,
            "amount": 500.0, "received_date": "2026-02-01"}).action_post()
        e.action_approve()  # now covered
        self.assertEqual(e.state, "approved")

    def test_date_outside_grant(self):
        with self.assertRaises(ValidationError):
            self.env["mcit.expense"].create({
                "grant_id": self.grant.id, "budget_line_id": self.line.id,
                "account_id": self.exp_acc.id, "amount": 10.0, "date": "2027-01-01"})

    def test_audit_immutable(self):
        self.grant.action_close()
        log = self.env["mcit.audit.log"].search(
            [("res_ref", "=", "mcit.grant,%s" % self.grant.id)], limit=1)
        self.assertTrue(log)
        with self.assertRaises(UserError):
            log.unlink()
