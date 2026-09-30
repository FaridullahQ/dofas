from odoo import models


class ArcsExpense(models.Model):
    _inherit = "arcs.expense"

    def action_submit(self):
        res = super().action_submit()
        for e in self:
            e.grant_id._governance_create_verifications("expense_approval", e)
        return res

    def action_approve(self):
        for e in self:
            e.grant_id._governance_check_gate("expense_approval", e)
        return super().action_approve()
