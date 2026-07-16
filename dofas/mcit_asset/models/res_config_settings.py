from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    asset_warehouse_id = fields.Many2one(
        related="company_id.asset_warehouse_id", readonly=False)
    asset_custody_location_id = fields.Many2one(
        related="company_id.asset_custody_location_id", readonly=False)
    asset_store_location_id = fields.Many2one(
        related="company_id.asset_store_location_id", readonly=False)
    asset_disposal_location_id = fields.Many2one(
        related="company_id.asset_disposal_location_id", readonly=False)
    asset_product_category_id = fields.Many2one(
        related="company_id.asset_product_category_id", readonly=False)
    asset_book_disposal = fields.Boolean(
        related="company_id.asset_book_disposal", readonly=False)
    asset_disposal_journal_id = fields.Many2one(
        related="company_id.asset_disposal_journal_id", readonly=False)
    asset_disposal_income_account_id = fields.Many2one(
        related="company_id.asset_disposal_income_account_id", readonly=False)
    asset_disposal_loss_account_id = fields.Many2one(
        related="company_id.asset_disposal_loss_account_id", readonly=False)
