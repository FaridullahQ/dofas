import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsBudgetTransfer(TransactionCase):
    """An approved internal transfer must never change either line's Planned
    amount - only Transferred In / Transferred Out (and, derived from those,
    Available) move."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-XFER", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-XFER-1", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 2000.0})
        cls.budget = cls.env["arcs.budget"].create({"grant_id": cls.grant.id})
        cls.line_a = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line A", "planned_amount": 700.0})
        cls.line_b = cls.env["arcs.budget.line"].create({
            "budget_id": cls.budget.id, "name": "Line B", "planned_amount": 1000.0})
        cls.budget.action_approve()

    def _attachment(self):
        return self.env["ir.attachment"].create({
            "name": "memo.pdf", "datas": base64.b64encode(b"dummy memo"),
        })

    def _submit(self, transfer):
        transfer.reference = "MEMO-0001"
        transfer.message_post(attachment_ids=self._attachment().ids)
        transfer.action_submit()
        return transfer

    def _transfer(self, amount):
        t = self.env["arcs.budget.transfer"].create({
            "from_line_id": self.line_a.id, "to_line_id": self.line_b.id,
            "amount": amount, "reason": "Reallocate to cover printing costs",
        })
        return self._submit(t)

    def test_submit_requires_reference_and_attachment(self):
        t = self.env["arcs.budget.transfer"].create({
            "from_line_id": self.line_a.id, "to_line_id": self.line_b.id,
            "amount": 100.0, "reason": "Reallocate to cover printing costs",
        })
        with self.assertRaises(UserError):
            t.action_submit()  # no reference, no attachment
        t.reference = "MEMO-0002"
        with self.assertRaises(UserError):
            t.action_submit()  # reference set, still no attachment
        t.message_post(attachment_ids=self._attachment().ids)
        t.action_submit()
        self.assertEqual(t.state, "submitted")

    def test_from_line_domain_excludes_to_line_and_vice_versa(self):
        t = self.env["arcs.budget.transfer"].create({
            "to_line_id": self.line_b.id, "amount": 100.0, "reason": "test",
        })
        # The view-level domain (from_line_id excludes to_line_id, and vice
        # versa) is a UX aid that only affects the dropdown - the real
        # safety net is the existing _check_lines() constraint; confirm it
        # still rejects the same-line case even if a client bypassed the
        # domain and tried to set both to the same line directly.
        with self.assertRaises(ValidationError):
            t.from_line_id = self.line_b.id

    def test_approved_transfer_leaves_planned_amount_untouched(self):
        t = self._transfer(300.0)
        t.action_approve()

        self.line_a.invalidate_recordset()
        self.line_b.invalidate_recordset()

        # Planned amount is the original approved figure, unchanged.
        self.assertEqual(self.line_a.planned_amount, 700.0)
        self.assertEqual(self.line_b.planned_amount, 1000.0)

        # The effect is captured separately.
        self.assertEqual(self.line_a.transferred_out_amount, 300.0)
        self.assertEqual(self.line_a.transferred_in_amount, 0.0)
        self.assertEqual(self.line_b.transferred_in_amount, 300.0)
        self.assertEqual(self.line_b.transferred_out_amount, 0.0)

        # Net Planned / Available reflect the transfer.
        self.assertEqual(self.line_a.effective_planned_amount, 400.0)
        self.assertEqual(self.line_b.effective_planned_amount, 1300.0)
        self.assertEqual(self.line_a.available_amount, 400.0)
        self.assertEqual(self.line_b.available_amount, 1300.0)

        # Grant total planned is invariant - transfers only move money around.
        self.assertEqual(self.budget.planned_total, 1700.0)

    def test_cannot_transfer_more_than_available(self):
        # Reserve part of line A first so its live available drops below planned.
        self.line_a.reserve(500.0)
        t = self._transfer(300.0)  # 700 planned but only 200 available now
        with self.assertRaises(UserError):
            t.action_approve()

    def test_two_sequential_transfers_accumulate_cumulatively(self):
        self._transfer(200.0).action_approve()
        self._transfer(100.0).action_approve()
        self.line_a.invalidate_recordset()
        self.line_b.invalidate_recordset()
        self.assertEqual(self.line_a.transferred_out_amount, 300.0)
        self.assertEqual(self.line_b.transferred_in_amount, 300.0)
        self.assertEqual(self.line_a.planned_amount, 700.0)
        self.assertEqual(self.line_b.planned_amount, 1000.0)

    def test_reversal_is_a_new_transfer_and_both_entries_stay_visible(self):
        """A 'reversal' is just a transfer in the opposite direction - the
        original entry is not deleted or netted away, matching the ledger
        (append-only) convention used elsewhere in this module."""
        self._transfer(300.0).action_approve()
        reversal = self.env["arcs.budget.transfer"].create({
            "from_line_id": self.line_b.id, "to_line_id": self.line_a.id,
            "amount": 300.0, "reason": "Reverting the earlier reallocation",
        })
        self._submit(reversal)
        reversal.action_approve()

        self.line_a.invalidate_recordset()
        self.line_b.invalidate_recordset()
        # Gross cumulative totals count both legs, not a net of zero.
        self.assertEqual(self.line_a.transferred_out_amount, 300.0)
        self.assertEqual(self.line_a.transferred_in_amount, 300.0)
        self.assertEqual(self.line_b.transferred_in_amount, 300.0)
        self.assertEqual(self.line_b.transferred_out_amount, 300.0)
        # Net effect is back to the original planned amounts either way.
        self.assertEqual(self.line_a.effective_planned_amount, 700.0)
        self.assertEqual(self.line_b.effective_planned_amount, 1000.0)
