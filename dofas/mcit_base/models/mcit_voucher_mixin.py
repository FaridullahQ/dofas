from odoo import fields, models


class McitVoucherMixin(models.AbstractModel):
    """Reusable journal/commitment voucher renderer. Any model that inherits
    this and overrides the hooks below gets a consistently-styled printable
    voucher (Template A: formal ledger layout with a debit/credit table and
    three signature blocks) via the shared mcit_base.report_voucher_document
    QWeb template, without duplicating markup per module."""

    _name = "mcit.voucher.mixin"
    _description = "Voucher Rendering Mixin"

    def _voucher_title(self):
        """Main heading, e.g. 'Expense Voucher'."""
        return "Journal Voucher"

    def _voucher_subtitle(self):
        return "Journal Entry Reference"

    def _voucher_number(self):
        self.ensure_one()
        return getattr(self, "name", "") or ""

    def _voucher_date(self):
        self.ensure_one()
        for field_name in ("date", "date_request", "received_date", "expense_date"):
            value = getattr(self, field_name, False)
            if value:
                return value
        return fields.Date.context_today(self)

    def _voucher_party_label(self):
        """e.g. 'Vendor' or 'Donor' - return False to omit the party line."""
        return False

    def _voucher_party_name(self):
        return False

    def _voucher_context_line(self):
        """Short free-text line under the header, e.g. project/activity."""
        return False

    def _voucher_currency(self):
        self.ensure_one()
        currency = getattr(self, "currency_id", False)
        return currency or self.env.company.currency_id

    def _voucher_is_posted(self):
        self.ensure_one()
        move = getattr(self, "move_id", False)
        return bool(move and move.state == "posted")

    def _voucher_lines(self):
        """Return a list of {account, description, debit, credit} dicts.
        Default: pull straight from a linked move_id when present (accurate
        reflection of what was actually posted). Models without a posted
        move (e.g. a budget commitment, an asset registration) must override
        this with a synthetic representative line and should make clear via
        _voucher_is_posted() that it is indicative, not a GL posting."""
        self.ensure_one()
        move = getattr(self, "move_id", False)
        if move:
            return [{
                "account": line.account_id.display_name,
                "description": line.name or "",
                "debit": line.debit,
                "credit": line.credit,
            } for line in move.line_ids]
        return []
