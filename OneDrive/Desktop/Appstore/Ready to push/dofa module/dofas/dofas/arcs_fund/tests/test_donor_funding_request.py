import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsDonorFundingRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create({
            "name": "UNDP", "code": "UNDP-DFR", "donor_type": "multilateral",
            "email": "grants@undp.example.org",
        })
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-DFR-1", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 2000.0})

    def _draft_request(self, amount=500.0):
        return self.env["arcs.donor.funding.request"].create({
            "grant_id": self.grant.id, "amount_requested": amount,
            "reason": "Cover a shortfall on office equipment.",
        })

    def _attachment(self):
        return self.env["ir.attachment"].create({
            "name": "justification.pdf", "datas": base64.b64encode(b"dummy justification"),
        })

    def _send_to_donor(self, request):
        request.reference = "MEMO-DFR-0001"
        request.message_post(attachment_ids=self._attachment().ids)
        request.action_request()
        return request

    def test_send_to_donor_requires_reference_and_attachment(self):
        request = self._draft_request()
        with self.assertRaises(UserError):
            request.action_request()  # no reference, no attachment
        request.reference = "MEMO-DFR-0002"
        with self.assertRaises(UserError):
            request.action_request()  # reference set, still no attachment
        request.message_post(attachment_ids=self._attachment().ids)
        request.action_request()
        self.assertEqual(request.state, "requested")

    def test_send_email_requires_request_sent_first(self):
        request = self._draft_request()
        with self.assertRaises(UserError):
            request.action_open_send_wizard()

    def test_send_to_donor_seeds_amount_approved(self):
        request = self._draft_request(500.0)
        self._send_to_donor(request)
        self.assertEqual(request.state, "requested")
        self.assertEqual(request.amount_approved, 500.0)

    def test_send_email_defaults_and_send(self):
        request = self._draft_request(500.0)
        self._send_to_donor(request)
        action = request.action_open_send_wizard()
        wizard = self.env["arcs.donor.funding.request.send.wizard"].with_context(
            action["context"]).create({})
        self.assertEqual(wizard.email_to, "grants@undp.example.org")
        self.assertIn(request.name, wizard.subject)
        self.assertIn("500.00", wizard.body)

        wizard.action_send()
        self.assertTrue(request.email_sent)
        self.assertTrue(request.email_sent_date)

    def test_approve_requires_amount(self):
        """Send to Donor now also requires an attachment, so by the time a
        request reaches 'requested' there is always at least one document on
        it - the approval-stage attachment gate (bank_receipt_attached) is
        therefore already satisfied by then; Finance is still expected to
        attach the actual bank receipt as an additional document when it
        arrives, but there's no separate state to test where the record has
        zero attachments at approval time anymore. What's still independently
        enforceable, and still tested here, is Amount Confirmed."""
        request = self._draft_request(500.0)
        self._send_to_donor(request)
        self.assertTrue(request.bank_receipt_attached)

        request.amount_approved = 0.0
        with self.assertRaises(UserError):
            request.action_donor_approve()

        request.amount_approved = 480.0  # donor sent slightly less than requested
        request.action_donor_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(request.amount_approved, 480.0)
        self.assertTrue(request.decision_date)
