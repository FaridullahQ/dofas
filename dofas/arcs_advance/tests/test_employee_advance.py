import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsEmployeeAdvance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "ARCSADV600", "account_type": "expense"})
        cls.adv_account = cls.env["account.account"].create(
            {"name": "Advances to Staff", "code": "ARCSADV120", "account_type": "asset_current"})
        cls.company.write({
            "arcs_advance_book": True,
            "arcs_advance_journal_id": cls.env["account.journal"].search(
                [("type", "=", "general")], limit=1).id,
            "arcs_advance_account_id": cls.adv_account.id,
            "arcs_advance_cash_account_id": cls.env["account.journal"].search(
                [("type", "=", "cash")], limit=1).default_account_id.id,
            "arcs_advance_clearing_account_id": cls.exp_acc.id,
            "arcs_expense_clearing_account_id": cls.exp_acc.id,
        })
        cls.cash_journal = cls.env["account.journal"].search([("type", "=", "cash")], limit=1)

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-ADV", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-ADV-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.budget = cls.env["arcs.budget"].create({"grant_id": cls.grant.id})
        cls.line = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line A",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 2000.0})
        cls.budget.action_approve()
        cls.grant.action_submit()
        cls.grant.action_approve()
        cls.grant.action_activate()

        cls.department = cls.env["hr.department"].create({"name": "Programs"})
        cls.job = cls.env["hr.job"].create({"name": "Field Officer"})
        cls.employee = cls.env["hr.employee"].create({
            "name": "Amina Yusuf", "department_id": cls.department.id, "job_id": cls.job.id,
        })

    def _issued_advance(self, amount=1000.0, allow_over=False):
        advance = self.env["arcs.advance"].create({
            "advance_type": "employee", "employee_id": self.employee.id,
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "currency_id": self.company.currency_id.id, "amount": amount,
            "allow_over_liquidation": allow_over,
        })
        advance.action_issue()
        return advance

    def _posted_expense(self, amount):
        expense = self.env["arcs.expense"].create({
            "name": "Item", "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "amount": amount, "account_id": self.exp_acc.id,
        })
        expense.action_submit()
        expense.action_approve()
        expense.action_post()
        return expense

    def _attachment(self):
        return self.env["ir.attachment"].create({
            "name": "slip.pdf", "datas": base64.b64encode(b"dummy slip"),
        })

    def test_employee_link_derives_department_and_job(self):
        advance = self._issued_advance()
        self.assertEqual(advance.department_id, self.department)
        self.assertEqual(advance.job_id, self.job)
        self.assertTrue(advance.move_id)

    def test_liquidation_blocked_above_advance_by_default(self):
        advance = self._issued_advance(1000.0, allow_over=False)
        expense = self._posted_expense(1200.0)
        with self.assertRaises(ValidationError):
            self.env["arcs.advance.liquidation"].create({
                "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)],
            })

    def test_overspend_liquidation_allowed_when_flagged(self):
        advance = self._issued_advance(1000.0, allow_over=True)
        expense = self._posted_expense(1200.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()
        advance.invalidate_recordset()
        self.assertEqual(advance.reported_amount, 1200.0)
        self.assertEqual(advance.outstanding_amount, -200.0)

    def test_settlement_return_path(self):
        advance = self._issued_advance(1000.0)
        expense = self._posted_expense(700.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()
        advance.invalidate_recordset()
        self.assertEqual(advance.outstanding_amount, 300.0)

        wizard = self.env["arcs.advance.settlement.wizard"].with_context(
            default_advance_id=advance.id).create({})
        self.assertEqual(wizard.direction, "return")
        self.assertEqual(wizard.settlement_amount, 300.0)
        wizard.journal_id = self.cash_journal.id

        with self.assertRaises(UserError):
            wizard.action_confirm()  # no attachment yet

        wizard.attachment_ids = [(6, 0, self._attachment().ids)]
        wizard.action_confirm()

        advance.invalidate_recordset()
        self.assertEqual(advance.returned_amount, 300.0)
        self.assertEqual(advance.outstanding_amount, 0.0)
        self.assertEqual(advance.state, "closed")  # auto-closed once settled to zero

    def test_settlement_reimbursement_path(self):
        advance = self._issued_advance(1000.0, allow_over=True)
        expense = self._posted_expense(1300.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()
        advance.invalidate_recordset()
        self.assertEqual(advance.outstanding_amount, -300.0)

        wizard = self.env["arcs.advance.settlement.wizard"].with_context(
            default_advance_id=advance.id).create({})
        self.assertEqual(wizard.direction, "reimburse")
        self.assertEqual(wizard.settlement_amount, 300.0)
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, self._attachment().ids)]
        wizard.action_confirm()

        advance.invalidate_recordset()
        self.assertEqual(advance.reimbursed_amount, 300.0)
        self.assertEqual(advance.outstanding_amount, 0.0)
        self.assertEqual(advance.state, "closed")

    def test_close_blocked_while_outstanding_either_direction(self):
        advance = self._issued_advance(1000.0, allow_over=True)
        with self.assertRaises(UserError):
            advance.action_close()  # +1000 outstanding
        expense = self._posted_expense(1300.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()
        with self.assertRaises(UserError):
            advance.action_close()  # -300 outstanding (owed to employee)
