import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "mcit")
class TestMcitSpendRequestEmployeeAdvance(TransactionCase):
    """Approve an acquisition, disburse its employee advance, spend against
    it, and settle both the underspend and overspend cases end to end."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "MCITREQADV600", "account_type": "expense"})
        cls.adv_account = cls.env["account.account"].create(
            {"name": "Advances to Staff", "code": "MCITREQADV120", "account_type": "asset_current"})
        cls.company.write({
            "mcit_advance_account_id": cls.adv_account.id,
            "mcit_expense_clearing_account_id": cls.adv_account.id,
        })
        cls.cash_journal = cls.env["account.journal"].search([("type", "=", "cash")], limit=1)

        cls.donor = cls.env["mcit.donor"].create(
            {"name": "UNDP", "code": "UNDP-REQADV", "donor_type": "multilateral"})
        cls.grant = cls.env["mcit.grant"].create({
            "name": "Health", "grant_number": "GR-REQADV-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 5000.0})
        cls.budget = cls.env["mcit.budget"].create({"grant_id": cls.grant.id})
        cls.line = cls.env["mcit.budget.line"].create({
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
        request = self.env["mcit.spend.request"].create({
            "budget_line_id": self.line.id, "requested_by": self.employee.id,
            "line_ids": [(0, 0, {"name": "Equipment", "quantity": 1, "unit_estimate": quoted_amount})],
        })
        request.action_submit()
        wizard = self.env["mcit.spend.request.quotation.wizard"].create({
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
        expense = self.env["mcit.expense"].create({
            "name": "Item", "grant_id": self.grant.id, "budget_line_id": self.line.id,
            "amount": amount, "account_id": self.exp_acc.id, "request_id": request.id,
        })
        expense.action_submit()
        expense.action_approve()
        expense.action_post()
        return expense

    def test_requested_by_defaults_from_current_user_employee(self):
        request = self.env["mcit.spend.request"].create({"budget_line_id": self.line.id})
        self.assertEqual(request.requested_by._name, "hr.employee")

    def test_disburse_advance_links_and_pays_employee(self):
        request = self._approved_request(1000.0)
        self.assertFalse(request.advance_id)
        request.action_disburse_advance()

        self.assertTrue(request.advance_id)
        self.assertEqual(request.advance_id.employee_id, self.employee)
        self.assertEqual(request.advance_id.state, "issued")
        self.assertEqual(request.advance_id.amount, 1000.0)
        self.assertEqual(request.advance_id.spend_request_id, request)
        self.assertTrue(request.advance_id.allow_over_liquidation)

        with self.assertRaises(UserError):
            request.action_disburse_advance()  # already disbursed

    def test_underspend_settles_with_return(self):
        request = self._approved_request(1000.0)
        request.action_disburse_advance()
        expense = self._posted_expense_for(request, 700.0)

        action = request.action_create_liquidation_for_advance()
        self.assertEqual(action["context"]["default_advance_id"], request.advance_id.id)
        self.assertIn(expense.id, action["context"]["default_expense_ids"][0][2])
        liq = self.env["mcit.advance.liquidation"].create({
            "advance_id": request.advance_id.id, "expense_ids": [(6, 0, [expense.id])],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()

        self.assertEqual(request.advance_outstanding_amount, 300.0)

        wizard_action = request.action_settle_advance()
        wizard = self.env["mcit.advance.settlement.wizard"].with_context(
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
        request.action_disburse_advance()
        expense = self._posted_expense_for(request, 1250.0)

        liq = self.env["mcit.advance.liquidation"].create({
            "advance_id": request.advance_id.id, "expense_ids": [(6, 0, [expense.id])],
        })
        liq.action_submit()
        liq.action_approve()
        liq.action_post()

        self.assertEqual(request.advance_outstanding_amount, -250.0)

        wizard_action = request.action_settle_advance()
        wizard = self.env["mcit.advance.settlement.wizard"].with_context(
            wizard_action["context"]).create({})
        self.assertEqual(wizard.direction, "reimburse")
        wizard.journal_id = self.cash_journal.id
        wizard.attachment_ids = [(6, 0, [self.env["ir.attachment"].create({
            "name": "slip.pdf", "datas": base64.b64encode(b"dummy"),
        }).id])]
        wizard.action_confirm()

        self.assertEqual(request.advance_id.reimbursed_amount, 250.0)
        self.assertEqual(request.advance_id.state, "closed")
