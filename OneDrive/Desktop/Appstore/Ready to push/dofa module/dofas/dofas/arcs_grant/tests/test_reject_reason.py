from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "arcs")
class TestArcsGrantRejectReason(TransactionCase):
    """End-to-end proof of the generic reason-wizard mechanism (arcs_base):
    the Reject button opens arcs.reason.wizard, confirming it calls the real
    action_reject(reason=...), the state actually changes, and the typed
    reason lands on the grant's own chatter - not just the internal audit
    log."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.donor = cls.env["arcs.donor"].create(
            {"name": "UNDP", "code": "UNDP-RJ", "donor_type": "multilateral"})
        cls.grant = cls.env["arcs.grant"].create({
            "name": "Health", "grant_number": "GR-RJ-1", "donor_id": cls.donor.id,
            "currency_id": cls.env.company.currency_id.id, "funding_model": "grant_based",
            "date_start": "2026-01-01", "date_end": "2026-12-31", "approved_amount": 2000.0})
        cls.grant.action_submit()

    def test_reject_wizard_opens_with_correct_context(self):
        action = self.grant.action_reject_wizard()
        self.assertEqual(action["res_model"], "arcs.reason.wizard")
        ctx = action["context"]
        self.assertEqual(ctx["default_res_model"], "arcs.grant")
        self.assertEqual(ctx["default_res_id"], self.grant.id)
        self.assertEqual(ctx["default_target_action"], "action_reject")

    def test_confirm_rejects_and_posts_reason_to_chatter(self):
        self.assertEqual(self.grant.state, "review")
        wizard = self.env["arcs.reason.wizard"].with_context(
            default_res_model="arcs.grant", default_res_id=self.grant.id,
            default_target_action="action_reject",
        ).create({"reason": "Budget narrative is incomplete, please revise."})
        wizard.action_confirm()

        self.assertEqual(self.grant.state, "draft")
        messages = self.grant.message_ids.mapped("body")
        self.assertTrue(any(
            "Budget narrative is incomplete" in (m or "") for m in messages))

    def test_reason_also_recorded_in_audit_log(self):
        wizard = self.env["arcs.reason.wizard"].with_context(
            default_res_model="arcs.grant", default_res_id=self.grant.id,
            default_target_action="action_reject",
        ).create({"reason": "Missing signed agreement."})
        wizard.action_confirm()

        log = self.env["arcs.audit.log"].search([
            ("res_ref", "=", "arcs.grant,%s" % self.grant.id),
            ("action", "=", "reject"),
        ], limit=1, order="id desc")
        self.assertTrue(log)
        self.assertEqual(log.comment, "Missing signed agreement.")
