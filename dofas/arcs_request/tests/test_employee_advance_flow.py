import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsSpendRequestEmployeeAdvance(TransactionCase):
    """Approve an acquisition, disburse its employee advance, spend against
    it, and settle both the underspend and overspend cases end to end."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "ARCSREQADV600", "account_type": "expense"})
        cls.adv_account = cls.env["account.account"].create(
            {"name": "Advances to Staff", "code": "ARCSREQADV120", "account_type": "asset_current"})
        cls.payable_account = cls.env["account.account"].create(
            {"name": "Advances Payable", "code": "ARCSREQADV220", "account_type": "liability_current"})
        cls.company.write({
            "arcs_advance_journal_id": cls.env["account.journal"].search(
                [("type", "=", "general")], limit=1).id,
            "arcs_advance_account_id": cls.adv_account.id,
            "arcs_advance_payable_account_id": cls.payable_account.id,
            "arcs_expense_clearing_account_id": cls.adv_account.id,
        })
        cls.cash_journal = cls.env["account.journal"].search([("type", "=", "cash")], limit=1)

        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-REQADV", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-REQADV-1", "donor_id": cls.donor.id,
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
        cls.employee = cls.env["hr.employee"].create({
            "name": "Amina Yusuf", "employee_code": "REQADV-EMP-1",
            "department_id": cls.department.id})
        # This employee deliberately has no linked res.users login (the
        # common case for field staff) - locking their advance must still
        # resolve a real debtor Partner via arcs.advance's own fallback
        # (work_contact_id / address_home_id), not fail outright. Make that
        # deterministic here regardless of which of those two fields this
        # Odoo build happens to auto-manage for a bare employee.create().
        Advance = cls.env["arcs.advance"]
        if not Advance._derive_employee_partner(cls.employee):
            for field_name in ("work_contact_id", "address_home_id"):
                if field_name in cls.employee._fields:
                    cls.employee[field_name] = cls.env["res.partner"].create(
                        {"name": cls.employee.name}).id
                    break

        cls.vendor = cls.env["res.partner"].create({"name": "Acme Supplies"})
        cls.attachment = cls.env["ir.attachment"].create({
            "name": "quote.pdf", "datas": base64.b64encode(b"dummy quotation"),
        })

    def _approved_request(self, quoted_amount=1000.0):
        request = self.env["arcs.spend.request"].create({
            "budget_line_id": self.line.id, "requested_by": self.employee.id,
            "line_ids": [(0, 0, {"name": "Equipment", "quantity": 1, "unit_estimate": quoted_amount})],
        })
        request.action_submit()
        wizard = self.env["arcs.spend.request.quotation.wizard"].create({
            "request_id": request.id, "vendor_id": self.vendor.id, "quotation_ref": "QTN-1",
            "attachment_ids": [(6, 0, self.attachment.ids)],
            "line_ids": [(0, 0, {
                "request_line_id": request.line_ids[0].id, "quoted_unit_price": quoted_amount,
            })],
        })
        wizard.action_confirm()
        request.action_commit()
        request.action_approve()
        return request

    def _posted_expense_for(self, request, amount):
        expense = self.env["arcs.expense"].create({
            "name": "Item", "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "amount": amount, "account_id": self.exp_acc.id, "request_id": request.id,
        })
        expense.action_submit()
        expense.action_approve()
        expense.action_post()
        return expense

    def _disburse(self, request):
        """Drives the full flow, mirroring exactly what a user does in the
        UI: action_disburse_advance() creates the advance and opens ITS
        OWN FORM (still Draft); from there, Lock it (debits the employee
        via a real accrual entry) and only then open the Disbursement
        wizard, fill in the journal + required attachment, and confirm."""
        action = request.action_disburse_advance()
        self.assertEqual(action["res_model"], "arcs.advance")
        self.assertEqual(action["res_id"], request.advance_id.id)
        request.advance_id.action_lock()

        wizard_action = request.advance_id.action_open_disbursement_wizard()
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            wizard_action["context"]).create({})
        self.assertEqual(wizard.advance_id, request.advance_id)
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, [self.env["ir.attachment"].create({
            "name": "voucher.pdf", "datas": base64.b64encode(b"dummy"),
        }).id])]
        wizard.action_confirm()
        return wizard

    def test_requested_by_defaults_from_current_user_employee(self):
        request = self.env["arcs.spend.request"].create({"budget_line_id": self.line.id})
        self.assertEqual(request.requested_by._name, "hr.employee")

    def test_disburse_advance_creates_and_opens_advance_form(self):
        """action_disburse_advance() no longer locks silently on the
        employee's behalf - it creates the (still Draft) advance and opens
        its own form, so Finance can review every detail - including the
        Employee Code, to confirm it's the right person, and the debtor
        Partner, which isn't always derivable automatically - before
        locking it themselves. This is what makes a missing Partner
        recoverable instead of a dead-end error dialog."""
        request = self._approved_request(1000.0)
        self.assertFalse(request.advance_id)
        action = request.action_disburse_advance()

        self.assertTrue(request.advance_id)
        self.assertEqual(request.advance_id.state, "draft")  # not locked yet
        self.assertFalse(request.advance_id.lock_move_id)
        self.assertEqual(request.advance_id.employee_id, self.employee)
        self.assertEqual(request.advance_id.amount, 1000.0)
        self.assertEqual(request.advance_id.spend_request_id, request)
        self.assertTrue(request.advance_id.allow_over_liquidation)
        self.assertFalse(request.advance_id.move_id)
        # Opens the advance's own form, not the disbursement wizard directly.
        self.assertEqual(action["res_model"], "arcs.advance")
        self.assertEqual(action["res_id"], request.advance_id.id)

        # Calling it again (e.g. Finance navigated away) just re-opens the
        # SAME advance's form - a resume path, not an error - as long as it
        # hasn't been fully issued yet.
        same_advance = request.advance_id
        action2 = request.action_disburse_advance()
        self.assertEqual(action2["res_id"], same_advance.id)
        self.assertEqual(request.advance_id, same_advance)  # no second advance created

    def test_disburse_advance_blocked_once_issued(self):
        request = self._approved_request(1000.0)
        self._disburse(request)
        self.assertEqual(request.advance_id.state, "issued")
        with self.assertRaises(UserError):
            request.action_disburse_advance()

    def test_disburse_advance_links_and_pays_employee(self):
        request = self._approved_request(1000.0)
        self._disburse(request)

        self.assertEqual(request.advance_id.state, "issued")
        self.assertTrue(request.advance_id.move_id)
        move = request.advance_id.move_id
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.journal_id, self.cash_journal)
        # The cash leg used the journal's own account, not a fixed company default.
        cash_lines = move.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(cash_lines.account_id, self.cash_journal.default_account_id)
        # The DISBURSEMENT move clears the Payable/Clearing liability booked
        # at lock time - it never debits the Advance Receivable account a
        # second time.
        debit_lines = move.line_ids.filtered(lambda l: l.debit)
        self.assertEqual(debit_lines.account_id, self.payable_account)
        self.assertEqual(debit_lines.debit, 1000.0)

        # And the LOCK entry (posted when Finance clicked 'Lock Advance' on
        # the advance's own form) is the one that actually debited the
        # employee.
        lock_move = request.advance_id.lock_move_id
        self.assertTrue(lock_move)
        lock_debit = lock_move.line_ids.filtered(lambda l: l.debit)
        self.assertEqual(lock_debit.account_id, self.adv_account)
        self.assertEqual(lock_debit.debit, 1000.0)

    def test_complete_disbursement_resumes_after_navigating_away(self):
        request = self._approved_request(1000.0)
        request.action_disburse_advance()  # advance created (Draft), form opened
        self.assertEqual(request.advance_id.state, "draft")

        # Finance navigated away before locking anything - resuming just
        # reopens the same advance's form, from wherever it's currently at.
        action = request.action_complete_disbursement()
        self.assertEqual(action["res_model"], "arcs.advance")
        self.assertEqual(action["res_id"], request.advance_id.id)

        # And it actually works end to end from there, exactly like a user
        # clicking through the advance's own Lock -> Issue buttons:
        request.advance_id.action_lock()
        wizard_action = request.advance_id.action_open_disbursement_wizard()
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            wizard_action["context"]).create({})
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, [self.env["ir.attachment"].create({
            "name": "voucher.pdf", "datas": base64.b64encode(b"dummy"),
        }).id])]
        wizard.action_confirm()
        self.assertEqual(request.advance_id.state, "issued")

    def test_complete_disbursement_blocked_with_nothing_pending(self):
        request = self._approved_request(1000.0)
        with self.assertRaises(UserError):
            request.action_complete_disbursement()  # no advance at all yet

    def test_underspend_settles_with_return(self):
        request = self._approved_request(1000.0)
        self._disburse(request)
        expense = self._posted_expense_for(request, 700.0)

        action = request.action_create_liquidation_for_advance()
        self.assertEqual(action["context"]["default_advance_id"], request.advance_id.id)
        self.assertIn(expense.id, action["context"]["default_expense_ids"][0][2])
        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": request.advance_id.id, "expense_ids": [(6, 0, [expense.id])],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()

        self.assertEqual(request.advance_outstanding_amount, 300.0)

        wizard_action = request.action_settle_advance()
        wizard = self.env["arcs.advance.settlement.wizard"].with_context(
            wizard_action["context"]).create({})
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, [self.env["ir.attachment"].create({
            "name": "slip.pdf", "datas": base64.b64encode(b"dummy"),
        }).id])]
        wizard.action_confirm()

        self.assertEqual(request.advance_id.state, "closed")
        self.assertEqual(request.advance_outstanding_amount, 0.0)

    def test_overspend_settles_with_reimbursement(self):
        request = self._approved_request(1000.0)
        self._disburse(request)
        expense = self._posted_expense_for(request, 1250.0)

        liq = self.env["arcs.advance.liquidation"].create({
            "advance_id": request.advance_id.id, "expense_ids": [(6, 0, [expense.id])],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()

        self.assertEqual(request.advance_outstanding_amount, -250.0)

        wizard_action = request.action_settle_advance()
        wizard = self.env["arcs.advance.settlement.wizard"].with_context(
            wizard_action["context"]).create({})
        self.assertEqual(wizard.direction, "reimburse")
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, [self.env["ir.attachment"].create({
            "name": "slip.pdf", "datas": base64.b64encode(b"dummy"),
        }).id])]
        wizard.action_confirm()

        self.assertEqual(request.advance_id.reimbursed_amount, 250.0)
        self.assertEqual(request.advance_id.state, "closed")
