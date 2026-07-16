from odoo import api, fields, models


class McitCommitment(models.Model):
    _name = "mcit.commitment"
    _description = "Budget Commitment (Encumbrance)"
    _order = "create_date desc, id desc"

    budget_line_id = fields.Many2one("mcit.budget.line", required=True, ondelete="restrict", index=True)
    grant_id = fields.Many2one(related="budget_line_id.grant_id", store=True, index=True)
    company_id = fields.Many2one(related="budget_line_id.company_id", store=True)
    currency_id = fields.Many2one(related="budget_line_id.currency_id", store=True)
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    amount = fields.Monetary(currency_field="currency_id")
    company_amount = fields.Monetary(currency_field="company_currency_id")
    state = fields.Selection(
        [("confirmed", "Confirmed"), ("consumed", "Consumed"), ("released", "Released")],
        default="confirmed", required=True, index=True)
    source_ref = fields.Reference(selection="_selection_source", string="Source Document")

    @api.model
    def _selection_source(self):
        candidates = ["mcit.expense", "mcit.procurement"]
        return [(m, self.env[m]._description) for m in candidates if m in self.env]

    @api.depends("budget_line_id", "amount", "state", "currency_id")
    def _compute_display_name(self):
        for c in self:
            label = c.budget_line_id.name or "Commitment"
            symbol = c.currency_id.symbol or ""
            state_label = dict(c._fields["state"].selection).get(c.state, c.state or "")
            c.display_name = "%s — %s%s [%s]" % (
                label, symbol, "{:,.2f}".format(c.amount or 0.0), state_label)

    def action_consume(self):
        return self.write({"state": "consumed"})

    def action_release(self):
        return self.write({"state": "released"})