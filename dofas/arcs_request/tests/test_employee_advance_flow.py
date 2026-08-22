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
        cls.company.write({
            "arcs_advance_account_id": cls.adv_account.id,
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
            "name": "Amina Yusuf", "department_id": cls.department.id})

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
        """Drives the full new disbursement flow: action_disburse_advance()
        creates the draft advance and opens the wizard; this fills in the
        journal + required attachment and confirms it - mirroring exactly
        what a user does in the UI."""
        action = request.action_disburse_advance()
        self.assertEqual(action["res_model"], "arcs.advance.disbursement.wizard")
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            action["context"]).create({})
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

    def test_disburse_advance_creates_draft_and_opens_wizard(self):
        request = self._approved_request(1000.0)
        self.assertFalse(request.advance_id)
        action = request.action_disburse_advance()

        # The draft advance is created and linked immediately...
        self.assertTrue(request.advance_id)
        self.assertEqual(request.advance_id.state, "draft")
        self.assertEqual(request.advance_id.employee_id, self.employee)
        self.assertEqual(request.advance_id.amount, 1000.0)
        self.assertEqual(request.advance_id.spend_request_id, request)
        self.assertTrue(request.advance_id.allow_over_liquidation)
        # ...but the money hasn't moved yet - that's the wizard's job.
        self.assertFalse(request.advance_id.move_id)
        self.assertEqual(action["res_model"], "arcs.advance.disbursement.wizard")

        with self.assertRaises(UserError):
            request.action_disburse_advance()  # already has an advance (draft or not)

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
        debit_lines = move.line_ids.filtered(lambda l: l.debit)
        self.assertEqual(debit_lines.account_id, self.adv_account)
        self.assertEqual(debit_lines.debit, 1000.0)

    def test_complete_disbursement_resumes_after_abandoned_wizard(self):
        request = self._approved_request(1000.0)
        request.action_disburse_advance()  # wizard opened but never confirmed
        self.assertEqual(request.advance_id.state, "draft")

        action = request.action_complete_disbursement()
        self.assertEqual(action["res_model"], "arcs.advance.disbursement.wizard")
        self.assertEqual(action["context"]["default_advance_id"], request.advance_id.id)

        # And it actually works end to end from there:
        wizard = self.env["arcs.advance.disbursement.wizard"].with_context(
            action["context"]).create({})
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
