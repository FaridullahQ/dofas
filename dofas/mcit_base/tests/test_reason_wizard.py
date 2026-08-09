from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "mcit")
class TestMcitReasonWizard(TransactionCase):
    """Validation guards for the generic reason wizard, tested in isolation
    against res.partner (a harmless, always-available target) since
    mcit_base itself defines no concrete workflow model. The full happy
    path - a real action getting called with the reason threaded through to
    the chatter - is covered per-model in each module that uses it (e.g.
    mcit_grant's reject-with-reason test)."""

    def test_empty_reason_blocked(self):
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        wizard = self.env["mcit.reason.wizard"].create({
            "res_model": "res.partner", "res_id": partner.id,
            "target_action": "some_method", "reason": "   ",
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_nonexistent_record_blocked(self):
        wizard = self.env["mcit.reason.wizard"].create({
            "res_model": "res.partner", "res_id": 999999999,
            "target_action": "some_method", "reason": "Because.",
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_non_callable_action_blocked(self):
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        wizard = self.env["mcit.reason.wizard"].create({
            "res_model": "res.partner", "res_id": partner.id,
            "target_action": "not_a_real_method", "reason": "Because.",
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_discard_closes_without_acting(self):
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        wizard = self.env["mcit.reason.wizard"].create({
            "res_model": "res.partner", "res_id": partner.id,
            "target_action": "some_method", "reason": "Because.",
        })
        result = wizard.action_discard()
        self.assertEqual(result.get("type"), "ir.actions.act_window_close")
