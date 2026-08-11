from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ArcsAuditLog(models.Model):
    """Append-only audit / approval log. The compliance system of record:
    create + read only, never edited or deleted (superuser excepted)."""

    _name = "arcs.audit.log"
    _description = "ARCS Immutable Audit Log"
    _order = "create_date desc, id desc"

    res_ref = fields.Reference(
        selection="_selection_referenceable", string="Document",
        required=True, index=True,
    )
    action = fields.Char(required=True, readonly=True)
    from_state = fields.Char(readonly=True)
    to_state = fields.Char(readonly=True)
    user_id = fields.Many2one(
        "res.users", string="Performed By", readonly=True,
        default=lambda self: self.env.user,
    )
    event_date = fields.Datetime(readonly=True, default=fields.Datetime.now)
    comment = fields.Text(readonly=True)

    @api.model
    def _selection_referenceable(self):
        result = []
        for name in sorted(self.env.registry.models):
            if name == "arcs.approval.mixin":
                continue
            Model = self.env.registry[name]
            if hasattr(Model, "_transition") and not Model._abstract:
                result.append((name, self.env[name]._description))
        return result

    def write(self, vals):
        raise UserError(_("Audit history is immutable and cannot be edited."))

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Audit history is immutable and cannot be deleted."))
        return super().unlink()
