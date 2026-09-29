from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # --- Asset / Inventory wiring (company level) ---------------------------
    asset_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Asset Warehouse",
        help="Warehouse whose internal-transfer operation type is used when the "
             "asset register moves units between Inventory locations.")
    asset_custody_location_id = fields.Many2one(
        "stock.location", string="Custody (In-Use) Location",
        domain="[('usage', '=', 'internal')]",
        help="Default Inventory location where an asset lives while it is in use "
             "with a custodian. Used as the starting on-hand location.")
    asset_store_location_id = fields.Many2one(
        "stock.location", string="Store Location",
        domain="[('usage', '=', 'internal')]",
        help="Inventory location the asset is moved into when you click "
             "'Move to Store'. This must be an internal location.")
    asset_disposal_location_id = fields.Many2one(
        "stock.location", string="Disposal / Loss Location",
        domain="[('usage', 'in', ('inventory', 'internal', 'customer'))]",
        help="Location the unit is moved to when an asset is disposed or marked "
             "lost (e.g. an Inventory-Loss virtual location). Removes it from "
             "on-hand store/custody stock.")
    asset_product_category_id = fields.Many2one(
        "product.category", string="Asset Product Category",
        help="Product category assigned to the auto-created inventory product for "
             "each asset. Leave empty to use the default category.")
    asset_book_disposal = fields.Boolean(
        string="Book Disposal Journal Entry",
        help="If set, disposing an asset also posts a journal entry using the "
             "accounts below (loss/gain on disposal).")
    asset_disposal_journal_id = fields.Many2one(
        "account.journal", string="Disposal Journal",
        domain="[('type', '=', 'general')]",
        help="Journal used for the disposal entry when booking is enabled.")
    asset_disposal_income_account_id = fields.Many2one(
        "account.account", string="Disposal Proceeds Account",
        help="Account credited with the disposal value (proceeds) when booking "
             "the disposal entry.")
    asset_disposal_loss_account_id = fields.Many2one(
        "account.account", string="Disposal Write-off Account",
        help="Account debited when writing off the asset book value on disposal.")
