from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class ArcsGrant(models.Model):
    _inherit = "arcs.grant"

    revolving_cycle_ids = fields.One2many(
        "arcs.revolving.cycle", "grant_id", string="Revolving Fund Cycles")
    revolving_cycle_count = fields.Integer(compute="_compute_revolving_counts")
    total_committed_amount = fields.Monetary(
        compute="_compute_revolving_counts", currency_field="currency_id",
        string="Total Committed (Revolving)")
    remaining_to_commit = fields.Monetary(
        compute="_compute_revolving_counts", currency_field="currency_id",
        string="Remaining to Commit")

    def _compute_revolving_counts(self):
        for g in self:
            cycles = g.revolving_cycle_ids.filtered(lambda c: c.state != "cancelled")
            g.revolving_cycle_count = len(g.revolving_cycle_ids)
            g.total_committed_amount = sum(cycles.mapped("amount_committed"))
            g.remaining_to_commit = (g.approved_amount or 0.0) - g.total_committed_amount

    def action_view_revolving_cycles(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Revolving Fund Cycles"),
            "res_model": "arcs.revolving.cycle",
            "view_mode": "tree,form",
            "domain": [("grant_id", "=", self.id)],
            "context": {"default_grant_id": self.id},
        }

    # --------------------------------------------------- funding-model hooks
    # Overrides of the two neutral extension points added to arcs_grant core
    # (see arcs_grant/models/arcs_grant.py). Every check below is gated on
    # funding_model == 'revolving_fund' and falls back to super() otherwise,
    # so grants on any other funding model are completely unaffected.
    def _funding_model_check_expense_availability(self, expense):
        self.ensure_one()
        if self.funding_model != "revolving_fund":
            return super()._funding_model_check_expense_availability(expense)
        cycle = expense.revolving_cycle_id
        if not cycle:
            raise UserError(_(
                "This grant uses the Revolving Fund model: link the expense "
                "to an open Revolving Fund Cycle before approving it."))
        if cycle.state != "utilizing":
            raise UserError(_(
                "Revolving Fund Cycle '%(c)s' is not open for spending "
                "(current state: %(s)s).",
                c=cycle.name, s=dict(cycle._fields["state"].selection).get(
                    cycle.state, cycle.state)))
        rounding = self.currency_id.rounding
        if float_compare(expense.amount, cycle.amount_available,
                         precision_rounding=rounding) > 0:
            raise UserError(_(
                "Insufficient funds on Revolving Fund Cycle '%(c)s'. "
                "Available: %(a).2f %(cur)s - requested: %(r).2f %(cur)s. On a "
                "Revolving Fund grant, expenses can never exceed the funds "
                "actually transferred for the current cycle.",
                c=cycle.name, a=cycle.amount_available, r=expense.amount,
                cur=self.currency_id.name))
        return True

    def _funding_model_check_closure_allowed(self):
        self.ensure_one()
        if self.funding_model != "revolving_fund":
            return super()._funding_model_check_closure_allowed()
        open_cycle = self.revolving_cycle_ids.filtered(
            lambda c: c.state not in ("closed", "cancelled"))
        if open_cycle:
            raise UserError(_(
                "Cannot close grant '%(g)s': Revolving Fund Cycle '%(c)s' is "
                "still open (state: %(s)s). Close or cancel it first.",
                g=self.display_name, c=open_cycle[0].name, s=dict(
                    open_cycle[0]._fields["state"].selection).get(
                    open_cycle[0].state, open_cycle[0].state)))
        return True
