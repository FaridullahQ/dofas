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
        cls.payable_account = cls.env["account.account"].create(
            {"name": "Advances Payable", "code": "ARCSADV220", "account_type": "liability_current"})
        cls.company.write({
            "arcs_advance_book": True,
            "arcs_advance_journal_id": cls.env["account.journal"].search(
                [("type", "=", "general")], limit=1).id,
            "arcs_advance_account_id": cls.adv_account.id,
            "arcs_advance_payable_account_id": cls.payable_account.id,
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
            "name": "Amina Yusuf", "employee_code": "ADV-EMP-1",
            "department_id": cls.department.id, "job_id": cls.job.id,
        })
        # No linked res.users login (common for field staff) - make sure a
        # debtor Partner is still resolvable via the same fallback
        # action_lock() relies on, deterministically, regardless of which
        # of work_contact_id/address_home_id this Odoo build auto-manages
        # for a bare employee.create().
        if not cls.env["arcs.advance"]._derive_employee_partner(cls.employee):
            for field_name in ("work_contact_id", "address_home_id"):
                if field_name in cls.employee._fields:
                    cls.employee[field_name] = cls.env["res.partner"].create(
                        {"name": cls.employee.name}).id
                    break

    def _draft_advance(self, amount=1000.0, allow_over=False):
        return self.env["arcs.advance"].create({
            "advance_type": "employee", "employee_id": self.employee.id,
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "currency_id": self.company.currency_id.id, "amount": amount,
            "allow_over_liquidation": allow_over,
        })

    def _issued_advance(self, amount=1000.0, allow_over=False):
        """Drives the full, now-mandatory two-step commitment: Lock (debits
        the holder, commits the amount) THEN Issue (actually disburses).
        Every existing test that used to just call action_issue() bare on a
        fresh draft now goes through both steps via this one helper."""
        advance = self._draft_advance(amount, allow_over)
        advance.action_lock()
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
        self.assertTrue(advance.lock_move_id)
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

    # ================================================================ locking

    def test_lock_debits_holder_before_any_cash_moves(self):
        """The core of this feature: locking posts a real accrual entry -
        Dr Advance (Receivable) / Cr Advances Payable - and the holder is
        debited immediately, well before any cash account is touched."""
        advance = self._draft_advance(1000.0)
        self.assertEqual(advance.state, "draft")
        self.assertFalse(advance.lock_move_id)

        advance.action_lock()
        self.assertEqual(advance.state, "locked")
        self.assertTrue(advance.lock_move_id)
        self.assertEqual(advance.lock_move_id.state, "posted")

        debit_line = advance.lock_move_id.line_ids.filtered(lambda l: l.debit)
        credit_line = advance.lock_move_id.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit_line.account_id, self.adv_account)
        self.assertEqual(credit_line.account_id, self.payable_account)
        self.assertEqual(debit_line.debit, 1000.0)
        self.assertEqual(credit_line.credit, 1000.0)
        # No cash account touched yet, and no disbursement entry posted.
        self.assertFalse(advance.move_id)

    def test_issue_blocked_before_lock(self):
        """Disbursement - directly, or via the wizard/button - is not
        reachable until the advance has been locked."""
        advance = self._draft_advance(500.0)
        with self.assertRaises(UserError):
            advance.action_issue()
        with self.assertRaises(UserError):
            advance.action_open_disbursement_wizard()

    def test_lock_requires_amount_and_partner(self):
        advance = self.env["arcs.advance"].create({
            "advance_type": "employee", "employee_id": self.employee.id,
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "currency_id": self.company.currency_id.id, "amount": 0.0,
        })
        with self.assertRaises(UserError):
            advance.action_lock()  # amount must be > 0

    def test_disbursement_clears_the_lock_liability_not_the_receivable(self):
        """After both steps, the DISBURSEMENT move's debit line is the
        Advances Payable account (clearing what lock booked) - never the
        Advance Receivable account again, which was already debited once,
        at lock time."""
        advance = self._draft_advance(1000.0)
        advance.action_lock()
        advance.action_issue()  # bare call, book toggle is on in setUpClass

        self.assertTrue(advance.move_id)
        debit_line = advance.move_id.line_ids.filtered(lambda l: l.debit)
        credit_line = advance.move_id.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit_line.account_id, self.payable_account)
        self.assertEqual(credit_line.account_id, self.company.arcs_advance_cash_account_id)

    def test_cancel_locked_advance_reverses_the_lock_entry(self):
        advance = self._draft_advance(800.0)
        advance.action_lock()
        lock_move = advance.lock_move_id
        self.assertEqual(lock_move.state, "posted")

        advance.action_cancel()
        self.assertEqual(advance.state, "cancelled")
        # The original lock entry is never deleted (permanent audit trail),
        # but a standard Odoo reversal was posted against it.
        self.assertEqual(lock_move.state, "posted")
        reversals = self.env["account.move"].search([
            ("reversed_entry_id", "=", lock_move.id)])
        self.assertTrue(reversals)
        self.assertEqual(reversals.state, "posted")

    def test_action_issue_bare_call_after_lock_respects_book_toggle(self):
        """Once locked (always a real posted accrual entry, regardless of
        the toggle - that's the whole point of this feature), the bare
        zero-argument action_issue() call for the DISBURSEMENT leg still
        respects the 'Book Advances to the Ledger' toggle exactly as
        before, for any caller not going through the new wizard."""
        self.company.arcs_advance_book = False
        advance = self._draft_advance(500.0)
        advance.action_lock()
        self.assertTrue(advance.lock_move_id)  # always posted, toggle or not

        advance.action_issue()
        self.assertEqual(advance.state, "issued")
        self.assertFalse(advance.move_id)  # toggle off -> no disbursement move, as always

        self.company.arcs_advance_book = True
        advance2 = self._draft_advance(500.0)
        advance2.action_lock()
        advance2.action_issue()
        self.assertTrue(advance2.move_id)  # toggle on -> posts, as always
        self.assertEqual(advance2.move_id.journal_id, self.company.arcs_advance_journal_id)

    def test_disbursement_wizard_always_posts_regardless_of_toggle(self):
        """The wizard path always posts a real disbursement entry, even
        with the ledger-booking toggle off - the toggle only ever governed
        the legacy bare-call path."""
        self.company.arcs_advance_book = False
        advance = self._draft_advance(500.0)
        advance.action_lock()

        action = advance.action_open_disbursement_wizard()
        self.assertEqual(action["res_model"], "arcs.advance.disbursement.wizard")
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            action["context"]).create({})

        with self.assertRaises(UserError):
            wizard.action_confirm()  # no journal, no attachment yet

        wizard.journal_id = self.cash_journal.id
        with self.assertRaises(UserError):
            wizard.action_confirm()  # journal set, still no attachment

        wizard.attachment_ids = [(6, 0, self._attachment().ids)]
        wizard.action_confirm()

        advance.invalidate_recordset()
        self.assertEqual(advance.state, "issued")
        self.assertTrue(advance.move_id)
        self.assertEqual(advance.move_id.journal_id, self.cash_journal)
        cash_line = advance.move_id.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(cash_line.account_id, self.cash_journal.default_account_id)
        debit_line = advance.move_id.line_ids.filtered(lambda l: l.debit)
        # Disbursement debits the Payable/Clearing account (lock already
        # debited the Receivable account) - see
        # test_lock_debits_holder_before_any_cash_moves for that leg.
        self.assertEqual(debit_line.account_id, self.payable_account)
        self.assertEqual(debit_line.debit, 500.0)

    def test_disbursement_wizard_blocked_unless_locked(self):
        draft_advance = self._draft_advance(400.0)
        with self.assertRaises(UserError):
            draft_advance.action_open_disbursement_wizard()

        issued_advance = self._issued_advance(400.0)  # already fully issued
        with self.assertRaises(UserError):
            issued_advance.action_open_disbursement_wizard()
