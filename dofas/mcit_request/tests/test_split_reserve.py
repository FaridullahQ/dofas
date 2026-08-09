import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "mcit")
class TestMcitSpendRequestSplitReserve(TransactionCase):
    """Approved amount 1000, primary budget line only has 700 available:
    confirm the split-across-budget-lines recovery reserves 700 on the
    primary line and 300 on a second line, affects both lines separately,
    and both show up on the printed voucher."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_acc = cls.env["account.account"].create(
            {"name": "Programme", "code": "MCITREQ600", "account_type": "expense"})

        cls.donor = cls.env["mcit.donor"].create(
            {"name": "UNDP", "code": "UNDP-SPLIT", "donor_type": "multilateral"})
        cls.grant = cls.env["mcit.grant"].create({
            "name": "Health", "grant_number": "GR-SPLIT-1", "donor_id": cls.donor.id,
            "currency_id": cls.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 2000.0})
        cls.budget = cls.env["mcit.budget"].create({"grant_id": cls.grant.id})
        cls.line_a = cls.env["mcit.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line A",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 700.0})
        cls.line_b = cls.env["mcit.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line B",
            "account_ids": [(6, 0, cls.exp_acc.ids)], "planned_amount": 1000.0})
        cls.budget.action_approve()
        cls.grant.action_submit()
        cls.grant.action_approve()
        cls.grant.action_activate()

        cls.vendor = cls.env["res.partner"].create({"name": "Acme Supplies"})
        cls.attachment = cls.env["ir.attachment"].create({
            "name": "quote.pdf", "datas": base64.b64encode(b"dummy quotation"),
        })

    def _submitted_request(self, item_amount):
        request = self.env["mcit.spend.request"].create({
            "budget_line_id": self.line_a.id,
            "line_ids": [(0, 0, {"name": "Equipment", "quantity": 1, "unit_estimate": item_amount})],
        })
        request.action_submit()
        return request

    def _confirm_real_price(self, request, amount):
        wizard = self.env["mcit.spend.request.quotation.wizard"].create({
            "request_id": request.id,
            "vendor_id": self.vendor.id,
            "quotation_ref": "QTN-0001",
            "attachment_ids": [(6, 0, self.attachment.ids)],
            "line_ids": [(0, 0, {
                "request_line_id": request.line_ids[0].id,
                "quoted_unit_price": amount,
            })],
        })
        wizard.action_confirm()

    def test_split_reserve_across_two_lines(self):
        request = self._submitted_request(1000.0)
        self._confirm_real_price(request, 1000.0)
        self.assertEqual(request.approved_amount, 1000.0)

        request.action_commit()
        self.assertEqual(request.state, "insufficient_funds")
        self.assertEqual(request.shortfall_amount, 300.0)

        wizard = self.env["mcit.spend.request.split.wizard"].with_context(
            default_request_id=request.id).create({
                "line_ids": [(0, 0, {"budget_line_id": self.line_b.id, "amount": 300.0})],
            })
        self.assertEqual(wizard.primary_amount, 700.0)
        self.assertEqual(wizard.total_allocated, 1000.0)
        self.assertEqual(wizard.remaining_to_allocate, 0.0)
        wizard.action_confirm()

        self.assertEqual(request.state, "committed")
        self.assertEqual(request.shortfall_amount, 0.0)
        self.assertTrue(request.is_split_reserve)
        self.assertEqual(request.commitment_count, 2)

        self.line_a.invalidate_recordset()
        self.line_b.invalidate_recordset()
        self.assertAlmostEqual(self.line_a.available_amount, 0.0)
        self.assertAlmostEqual(self.line_b.available_amount, 700.0)

        commitments = request.commitment_ids.filtered(lambda c: c.state == "confirmed")
        by_line = {c.budget_line_id: c.amount for c in commitments}
        self.assertAlmostEqual(by_line[self.line_a], 700.0)
        self.assertAlmostEqual(by_line[self.line_b], 300.0)

        # The voucher itemizes each budget line separately and still foots.
        vlines = request._voucher_lines()
        self.assertEqual(len(vlines), 4)  # 2 debit/credit pairs
        self.assertAlmostEqual(sum(l["debit"] for l in vlines), 1000.0)
        self.assertAlmostEqual(sum(l["credit"] for l in vlines), 1000.0)

    def test_split_must_add_up_exactly(self):
        request = self._submitted_request(1000.0)
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        self.assertEqual(request.state, "insufficient_funds")

        wizard = self.env["mcit.spend.request.split.wizard"].with_context(
            default_request_id=request.id).create({
                "line_ids": [(0, 0, {"budget_line_id": self.line_b.id, "amount": 250.0})],
            })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_reject_after_split_releases_both_lines(self):
        request = self._submitted_request(1000.0)
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        wizard = self.env["mcit.spend.request.split.wizard"].with_context(
            default_request_id=request.id).create({
                "line_ids": [(0, 0, {"budget_line_id": self.line_b.id, "amount": 300.0})],
            })
        wizard.action_confirm()

        request.action_reject()
        self.line_a.invalidate_recordset()
        self.line_b.invalidate_recordset()
        self.assertAlmostEqual(self.line_a.available_amount, 700.0)
        self.assertAlmostEqual(self.line_b.available_amount, 1000.0)
        released = request.commitment_ids
        self.assertTrue(all(c.state == "released" for c in released))

    def test_create_expense_splits_one_per_line(self):
        request = self._submitted_request(1000.0)
        self._confirm_real_price(request, 1000.0)
        request.action_commit()
        wizard = self.env["mcit.spend.request.split.wizard"].with_context(
            default_request_id=request.id).create({
                "line_ids": [(0, 0, {"budget_line_id": self.line_b.id, "amount": 300.0})],
            })
        wizard.action_confirm()
        request.action_approve()

        action = request.action_create_expense()
        expenses = self.env["mcit.expense"].search(action["domain"])
        self.assertEqual(len(expenses), 2)
        amounts = sorted(expenses.mapped("amount"))
        self.assertEqual(amounts, [300.0, 700.0])
        for expense in expenses:
            expense.action_submit()
            expense.action_approve()
            matched = request.commitment_ids.filtered(
                lambda c: c.budget_line_id == expense.budget_line_id)
            self.assertEqual(expense.commitment_id, matched)
