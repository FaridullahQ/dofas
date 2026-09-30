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


@tagged("post_install", "-at_install", "arcs")
class TestArcsAdvanceSummaryVoucher(TestArcsEmployeeAdvance):
    """The printable Advance Summary - for physical review/signature before
    Issue Advance - reuses arcs_base's shared voucher renderer, exactly
    like the Expense/Fund/Asset vouchers already do. Before Issue there is
    no disbursement move yet, so it must preview the entry that Issue is
    about to post (Dr Payable/Clearing, Cr the intended bank/cash account)
    rather than come up empty."""

    def test_title_and_subtitle(self):
        advance = self._draft_advance()
        self.assertEqual(advance._voucher_title(), "Cash Advance Summary")
        self.assertTrue(advance._voucher_subtitle())

    def test_employee_party_label_and_name(self):
        advance = self._draft_advance()
        self.assertEqual(advance._voucher_party_label(), "Employee")
        name = advance._voucher_party_name()
        self.assertIn(self.employee.name, name)
        self.assertIn(self.employee.employee_code, name)
        self.assertIn(self.job.name, name)
        self.assertIn(self.department.name, name)

    def test_zone_party_label_and_name(self):
        zone = self.env["arcs.zone"].create({"name": "Central Region", "code": "ADV-ZN"})
        advance = self.env["arcs.advance"].create({
            "advance_type": "zone", "zone_id": zone.id,
            "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "currency_id": self.company.currency_id.id, "amount": 300.0,
        })
        self.assertEqual(advance._voucher_party_label(), "Region / Province")
        self.assertEqual(advance._voucher_party_name(), "Central Region")

    def test_context_line_includes_purpose_and_funding(self):
        advance = self._draft_advance()
        advance.note = "Field visit fuel and lodging"
        line = advance._voucher_context_line()
        self.assertIn("Field visit fuel and lodging", line)
        self.assertIn(self.grant.name, line)
        self.assertIn(self.line.name, line)

    def test_context_line_false_when_nothing_to_show(self):
        advance = self.env["arcs.advance"].create({
            "advance_type": "employee", "employee_id": self.employee.id,
            "currency_id": self.company.currency_id.id, "amount": 100.0,
        })
        self.assertFalse(advance._voucher_context_line())

    def test_voucher_lines_preview_before_issue_uses_company_defaults(self):
        """No disbursement_journal_id chosen yet - falls back to the
        company's configured Advance Journal/Cash Account, exactly what
        action_issue() itself would fall back to."""
        advance = self._draft_advance(750.0)
        advance.action_lock()
        self.assertFalse(advance.move_id)
        lines = advance._voucher_lines()
        self.assertEqual(len(lines), 2)
        debit_line = next(l for l in lines if l["debit"])
        credit_line = next(l for l in lines if l["credit"])
        self.assertEqual(debit_line["debit"], 750.0)
        self.assertEqual(credit_line["credit"], 750.0)
        self.assertEqual(debit_line["account"], self.payable_account.display_name)
        self.assertFalse(advance._voucher_is_posted())

    def test_voucher_lines_preview_uses_chosen_disbursement_journal(self):
        advance = self._draft_advance(750.0)
        advance.disbursement_journal_id = self.cash_journal
        advance.action_lock()
        lines = advance._voucher_lines()
        credit_line = next(l for l in lines if l["credit"])
        self.assertEqual(credit_line["account"], self.cash_journal.default_account_id.display_name)
        self.assertIn(self.cash_journal.name, credit_line["description"])

    def test_disbursement_account_follows_journal(self):
        advance = self._draft_advance()
        self.assertFalse(advance.disbursement_account_id)
        advance.disbursement_journal_id = self.cash_journal
        self.assertEqual(advance.disbursement_account_id, self.cash_journal.default_account_id)

    def test_voucher_lines_reflect_real_move_once_issued(self):
        """Once actually disbursed, reprinting must show the real posted
        entry - not the pre-issue preview anymore."""
        advance = self._draft_advance(750.0)
        advance.disbursement_journal_id = self.cash_journal
        advance.action_lock()
        advance.action_issue(journal_id=self.cash_journal.id)
        self.assertTrue(advance._voucher_is_posted())
        lines = advance._voucher_lines()
        self.assertEqual({l["account"] for l in lines},
                         {self.payable_account.display_name,
                          self.cash_journal.default_account_id.display_name})

    def test_action_print_voucher_returns_report_action(self):
        advance = self._draft_advance()
        action = advance.action_print_voucher()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(action["report_name"], "arcs_advance.report_advance_summary")

    def test_wizard_prefills_journal_from_advance(self):
        advance = self._draft_advance(500.0)
        advance.disbursement_journal_id = self.cash_journal
        advance.action_lock()
        action = advance.action_open_disbursement_wizard()
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            action["context"]).create({})
        self.assertEqual(wizard.journal_id, self.cash_journal)

    def test_wizard_journal_stays_required_when_not_pre_chosen(self):
        """No disbursement_journal_id set on the advance - the wizard's
        journal is simply left blank (still required to confirm), exactly
        the pre-existing behaviour, unaffected by this feature."""
        advance = self._draft_advance(500.0)
        advance.action_lock()
        action = advance.action_open_disbursement_wizard()
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            action["context"]).create({})
        self.assertFalse(wizard.journal_id)


@tagged("post_install", "-at_install", "arcs")
class TestArcsAdvanceExpenseAndSettlementTracking(TestArcsEmployeeAdvance):
    """Requirement: the expense(s) justified against an advance and every
    settlement journal entry must be reachable from the advance record
    itself via smart buttons, and every one of the advance's own journal
    entries (Lock, Issue, Liquidation, Settlement) should carry the same
    analytic tag as the funding Budget Line, so by-fund analytic reports
    pick advances up correctly."""

    def test_expenses_smart_button_aggregates_across_liquidations(self):
        advance = self._issued_advance(1000.0)
        expense_a = self._posted_expense(300.0)
        liq_a = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense_a.ids)]})
        liq_a.action_submit(); liq_a.action_approve(); liq_a.action_post()
        expense_b = self._posted_expense(200.0)
        liq_b = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense_b.ids)]})
        liq_b.action_submit(); liq_b.action_approve(); liq_b.action_post()

        advance.invalidate_recordset()
        self.assertEqual(advance.expense_count, 2)
        self.assertEqual(set(advance.expense_ids.ids), {expense_a.id, expense_b.id})
        action = advance.action_view_expenses()
        self.assertEqual(action["domain"], [("id", "in", advance.expense_ids.ids)])

    def test_expenses_smart_button_empty_with_no_liquidations(self):
        advance = self._issued_advance(500.0)
        self.assertEqual(advance.expense_count, 0)
        self.assertFalse(advance.expense_ids)

    def test_settlement_move_tracked_and_viewable(self):
        advance = self._issued_advance(1000.0)
        expense = self._posted_expense(700.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)]})
        liq.action_submit(); liq.action_approve(); liq.action_post()

        wizard = self.env["arcs.advance.settlement.wizard"].with_context(
            default_advance_id=advance.id).create({})
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, self._attachment().ids)]
        wizard.action_confirm()

        advance.invalidate_recordset()
        self.assertEqual(advance.settlement_move_count, 1)
        move = advance.settlement_move_ids
        self.assertEqual(move.state, "posted")
        action = advance.action_view_settlement_moves()
        self.assertEqual(action["domain"], [("id", "in", move.ids)])

    def test_multiple_partial_settlements_all_tracked(self):
        """Partial settlements can happen more than once - every one of
        them must accumulate in settlement_move_ids, not just the last."""
        advance = self._issued_advance(1000.0)
        expense = self._posted_expense(400.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)]})
        liq.action_submit(); liq.action_approve(); liq.action_post()
        advance.invalidate_recordset()  # outstanding = 600.0

        for partial in (200.0, 400.0):
            wizard = self.env["arcs.advance.settlement.wizard"].with_context(
                default_advance_id=advance.id).create({})
            wizard.settlement_amount = partial
            wizard.journal_id = self.cash_journal.id
            wizard.attachment_ids = [(6, 0, self._attachment().ids)]
            wizard.action_confirm()
            advance.invalidate_recordset()

        self.assertEqual(advance.settlement_move_count, 2)
        self.assertEqual(advance.state, "closed")

    def test_lock_and_issue_moves_carry_analytic_distribution(self):
        advance = self._issued_advance(1000.0)
        analytic_id = str(self.grant.analytic_account_id.id)
        for move in (advance.lock_move_id, advance.move_id):
            for line in move.line_ids:
                self.assertIn(analytic_id, line.analytic_distribution or {})

    def test_liquidation_move_carries_analytic_distribution(self):
        advance = self._issued_advance(1000.0)
        expense = self._posted_expense(300.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)]})
        liq.action_submit(); liq.action_approve(); liq.action_post()
        analytic_id = str(self.grant.analytic_account_id.id)
        for line in liq.move_id.line_ids:
            self.assertIn(analytic_id, line.analytic_distribution or {})

    def test_settlement_move_carries_analytic_distribution(self):
        advance = self._issued_advance(1000.0)
        expense = self._posted_expense(700.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": advance.id, "expense_ids": [(6, 0, expense.ids)]})
        liq.action_submit(); liq.action_approve(); liq.action_post()
        wizard = self.env["arcs.advance.settlement.wizard"].with_context(
            default_advance_id=advance.id).create({})
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, self._attachment().ids)]
        wizard.action_confirm()
        advance.invalidate_recordset()
        analytic_id = str(self.grant.analytic_account_id.id)
        for line in advance.settlement_move_ids.line_ids:
            self.assertIn(analytic_id, line.analytic_distribution or {})

    def test_no_analytic_distribution_when_no_budget_line(self):
        """An advance is allowed to have no Budget Line at all - its moves
        must still post fine, simply without an analytic tag."""
        advance = self.env["arcs.advance"].create({
            "advance_type": "employee", "employee_id": self.employee.id,
            "currency_id": self.company.currency_id.id, "amount": 200.0,
        })
        self.assertEqual(advance._advance_analytic_distribution(), {})
        advance.action_lock()
        for line in advance.lock_move_id.line_ids:
            self.assertFalse(line.analytic_distribution)


@tagged("post_install", "-at_install", "arcs")
class TestArcsAdvanceOutstandingWarning(TestArcsEmployeeAdvance):
    """Requirement: issuing a new advance to an employee who still has an
    unsettled one should notify whoever is issuing it - a non-blocking
    heads-up, not a hard stop, since a second concurrent advance can be
    entirely legitimate."""

    def test_onchange_warns_when_employee_has_outstanding_advance(self):
        self._issued_advance(1000.0)  # left fully outstanding, untouched
        new_advance = self.env["arcs.advance"].new({"advance_type": "employee"})
        new_advance.employee_id = self.employee
        result = new_advance._onchange_employee()
        self.assertTrue(result and result.get("warning"))
        self.assertIn(self.employee.name, result["warning"]["message"])

    def test_onchange_silent_when_no_outstanding_advance(self):
        new_advance = self.env["arcs.advance"].new({"advance_type": "employee"})
        new_advance.employee_id = self.employee
        result = new_advance._onchange_employee()
        self.assertFalse(result)

    def test_onchange_silent_once_prior_advance_fully_settled(self):
        prior = self._issued_advance(500.0)
        expense = self._posted_expense(500.0)
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": prior.id, "expense_ids": [(6, 0, expense.ids)]})
        liq.action_submit(); liq.action_approve(); liq.action_post()
        prior.invalidate_recordset()
        self.assertEqual(prior.outstanding_amount, 0.0)

        new_advance = self.env["arcs.advance"].new({"advance_type": "employee"})
        new_advance.employee_id = self.employee
        result = new_advance._onchange_employee()
        self.assertFalse(result)

    def test_lock_posts_chatter_note_when_employee_has_outstanding_advance(self):
        """Belt-and-suspenders: even an advance created without ever going
        through the onchange (e.g. programmatically, from an approved
        Acquisition request) leaves an audit trail at Lock time."""
        self._issued_advance(1000.0)
        second = self._draft_advance(400.0)
        messages_before = len(second.message_ids)
        second.action_lock()
        self.assertGreater(len(second.message_ids), messages_before)
        self.assertTrue(any(
            self.employee.name in (m.body or "") and "unsettled" in (m.body or "")
            for m in second.message_ids))

    def test_lock_silent_when_no_other_outstanding_advance(self):
        advance = self._draft_advance(400.0)
        advance.action_lock()
        self.assertFalse(any(
            "unsettled" in (m.body or "") for m in advance.message_ids))
