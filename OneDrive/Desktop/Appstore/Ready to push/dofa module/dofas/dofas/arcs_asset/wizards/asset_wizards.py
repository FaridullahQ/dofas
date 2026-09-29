from odoo import _, api, fields, models
from odoo.exceptions import UserError

DISPOSAL = [
    ("sold", "Sold"),
    ("donated", "Donated"),
    ("scrapped", "Scrapped"),
    ("returned_to_donor", "Returned to Donor"),
    ("other", "Other"),
]


class AssetTransferWizard(models.TransientModel):
    _name = "arcs.asset.transfer.wizard"
    _description = "Transfer Asset Wizard"

    asset_id = fields.Many2one(
        "arcs.asset", string="Asset", required=True, ondelete="cascade",
        help="Asset being transferred.")
    company_id = fields.Many2one(related="asset_id.company_id")
    current_location_id = fields.Many2one(
        related="asset_id.current_location_id", string="Current Location",
        help="Where the unit is right now.")
    dest_location_id = fields.Many2one(
        "stock.location", string="Transfer To (Location)", required=True,
        domain="[('usage', '=', 'internal')]",
        help="Internal Inventory location the asset will physically move to.")
    custodian_id = fields.Many2one(
        "res.partner", string="Lock To (Custodian)", required=True,
        help="Person or office that receives the asset. The unit is locked to "
             "them in Inventory; afterwards only an Asset Manager can move it.")
    transfer_date = fields.Date(
        string="Transfer Date", default=fields.Date.context_today, required=True,
        help="Effective date of the handover.")
    reference = fields.Char(
        string="Gate-pass / Reference",
        help="Handover note or gate-pass number for the audit trail.")

    def action_confirm(self):
        self.ensure_one()
        if self.dest_location_id == self.current_location_id:
            raise UserError(_("Choose a destination different from the current location."))
        self.asset_id._do_transfer({
            "dest_location_id": self.dest_location_id,
            "custodian_id": self.custodian_id,
            "transfer_date": self.transfer_date,
            "reference": self.reference,
        })
        return {"type": "ir.actions.act_window_close"}


class AssetDisposeWizard(models.TransientModel):
    _name = "arcs.asset.dispose.wizard"
    _description = "Dispose Asset Wizard"

    asset_id = fields.Many2one(
        "arcs.asset", string="Asset", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="asset_id.currency_id")
    disposal_date = fields.Date(
        string="Disposal Date", default=fields.Date.context_today, required=True,
        help="Date the asset left the organisation.")
    disposal_method = fields.Selection(
        DISPOSAL, string="Method", required=True,
        help="How the asset was disposed of.")
    disposal_value = fields.Monetary(
        string="Disposal Value", currency_field="currency_id",
        help="Proceeds received (0 for scrapped/donated). Cannot be negative.")
    reference = fields.Char(
        string="Authorisation Reference",
        help="Disposal authorisation or receipt reference.")

    @api.constrains("disposal_value")
    def _check_value(self):
        for w in self:
            if w.disposal_value and w.disposal_value < 0:
                raise UserError(_("Disposal Value cannot be negative."))

    def action_confirm(self):
        self.ensure_one()
        self.asset_id._do_dispose({
            "disposal_date": self.disposal_date,
            "disposal_method": self.disposal_method,
            "disposal_value": self.disposal_value,
            "reference": self.reference,
        })
        return {"type": "ir.actions.act_window_close"}


class AssetLostWizard(models.TransientModel):
    _name = "arcs.asset.lost.wizard"
    _description = "Mark Asset Lost Wizard"

    asset_id = fields.Many2one(
        "arcs.asset", string="Asset", required=True, ondelete="cascade")
    lost_date = fields.Date(
        string="Lost Date", default=fields.Date.context_today, required=True,
        help="Date the asset was reported lost or stolen.")
    reason = fields.Text(
        string="Loss Reason", required=True,
        help="Required explanation of how the asset was lost. Kept in the audit log.")

    def action_confirm(self):
        self.ensure_one()
        self.asset_id._do_lost({
            "lost_date": self.lost_date,
            "reason": self.reason,
        })
        return {"type": "ir.actions.act_window_close"}
