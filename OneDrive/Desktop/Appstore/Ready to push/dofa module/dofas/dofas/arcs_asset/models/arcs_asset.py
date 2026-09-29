from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

CATEGORY = [
    ("equipment", "Equipment"),
    ("vehicle", "Vehicle"),
    ("it_equipment", "IT Equipment"),
    ("furniture", "Furniture"),
    ("other", "Other"),
]
DISPOSAL = [
    ("sold", "Sold"),
    ("donated", "Donated"),
    ("scrapped", "Scrapped"),
    ("returned_to_donor", "Returned to Donor"),
    ("other", "Other"),
]
TERMINAL_STATES = ("disposed", "lost")


class ArcsAsset(models.Model):
    _name = "arcs.asset"
    _description = "Grant-Funded Asset"
    _inherit = ["arcs.approval.mixin", "arcs.voucher.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "acquisition_date desc, id desc"
    _check_company_auto = True

    # ----------------------------------------------------------------- identity
    name = fields.Char(
        string="Asset", required=True, tracking=True,
        help="Short, recognisable name of the asset, e.g. 'Toyota Hilux 4x4' or "
             "'Dell Latitude 5440 Laptop'.")
    code = fields.Char(
        string="Asset Tag", required=True, copy=False, readonly=True,
        index=True, default=lambda s: _("New"),
        help="Unique inventory tag generated automatically. Also becomes the "
             "default serial number of the Inventory unit.")
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda s: s.env.company,
        help="Company that owns this asset register entry.")
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------- grant linkage
    grant_id = fields.Many2one(
        "arcs.grant", string="Grant", required=True, ondelete="restrict",
        tracking=True, check_company=True,
        help="Donor grant whose funds paid for this asset. Drives the currency "
             "and donor reporting.")
    project_id = fields.Many2one(
        "arcs.project", string="Project",
        domain="[('grant_id', '=', grant_id)]",
        help="Project under the grant that the asset belongs to (optional).")
    expense_id = fields.Many2one(
        "arcs.expense", string="Source Expense",
        domain="[('grant_id', '=', grant_id)]",
        help="The expenditure record that funded this asset, kept as an audit "
             "link between the payment and the asset.")
    donor_id = fields.Many2one(
        related="grant_id.donor_id", store=True, string="Donor",
        help="Donor behind the funding grant.")
    currency_id = fields.Many2one(
        "res.currency", string="Currency", compute="_compute_currency_id",
        store=True, readonly=True,
        help="Currency of the acquisition cost (taken from the grant, or the "
             "company currency if the grant has none).")

    # ------------------------------------------------------------- description
    category = fields.Selection(
        CATEGORY, string="Category", required=True, default="equipment",
        tracking=True,
        help="Type of asset. Used for grouping and donor asset reports.")
    acquisition_date = fields.Date(
        string="Acquisition Date", required=True,
        default=fields.Date.context_today, tracking=True,
        help="Date the asset was purchased or received. Cannot be in the future.")
    acquisition_cost = fields.Monetary(
        string="Acquisition Cost", currency_field="currency_id", tracking=True,
        help="Purchase value of the asset in the grant currency. Must be "
             "greater than zero. Auto-filled from the Source Expense amount "
             "when selected, but remains editable.")
    cost_expense_mismatch = fields.Boolean(
        string="Cost/Expense Mismatch", compute="_compute_cost_expense_mismatch",
        help="True when the Acquisition Cost no longer matches the Source "
             "Expense amount.")
    quantity = fields.Integer(
        string="Quantity", default=1,
        help="Number of identical units this record represents. For "
             "serial-tracked donor assets this is normally 1.")
    serial_number = fields.Char(
        string="Serial / Chassis No.", copy=False,
        help="Manufacturer serial, VIN or chassis number. If set, it becomes "
             "the Inventory lot/serial; otherwise the Asset Tag is used.")
    custodian_id = fields.Many2one(
        "res.partner", string="Custodian", tracking=True,
        help="Person or office currently responsible for the asset. After a "
             "Transfer this is the party the asset is locked to.")
    location_note = fields.Char(
        string="Physical Location",
        help="Free-text physical whereabouts, e.g. 'ARCS Herat Branch - Store 2'. "
             "The Inventory location is tracked separately below.")
    description = fields.Text(
        string="Description",
        help="Specification or notes about the asset (model, condition, "
             "accessories).")

    # --------------------------------------------------------- inventory link
    product_id = fields.Many2one(
        "product.product", string="Inventory Product", copy=False, readonly=True,
        help="Serial-tracked product auto-created to represent this asset inside "
             "Odoo Inventory (one product = one asset).")
    lot_id = fields.Many2one(
        "stock.lot", string="Inventory Lot/Serial", copy=False, readonly=True,
        help="The specific Inventory serial number for this physical unit.")
    current_location_id = fields.Many2one(
        "stock.location", string="Current Inventory Location", readonly=True,
        help="Where the unit physically sits in Inventory right now. Updated by "
             "Move to Store / Return to Use / Transfer.")
    on_hand_qty = fields.Float(
        string="On Hand", compute="_compute_on_hand_qty",
        help="Quantity currently on hand in internal Inventory locations "
             "(1 when registered, 0 once disposed or lost).")
    in_inventory = fields.Boolean(
        string="In Inventory", compute="_compute_on_hand_qty",
        help="True once the asset has been mirrored into Inventory with stock "
             "on hand.")
    locked_to_id = fields.Many2one(
        "res.partner", string="Locked To", readonly=True, copy=False, tracking=True,
        help="Party the asset has been transferred and locked to. While locked, "
             "only an Asset Manager can move or transfer it again.")
    move_line_count = fields.Integer(
        string="Move Count", compute="_compute_move_line_count",
        help="Number of validated Inventory moves recorded for this unit.")

    # --------------------------------------------------------- transfer record
    transfer_to = fields.Char(
        string="Transferred To", readonly=True, copy=False,
        help="Name of the party the asset was last transferred to (filled by the "
             "Transfer wizard).")
    transfer_partner_id = fields.Many2one(
        "res.partner", string="Transfer Recipient", readonly=True, copy=False,
        help="Recipient partner recorded on the last transfer.")
    transfer_location_id = fields.Many2one(
        "stock.location", string="Transfer Destination", readonly=True, copy=False,
        help="Inventory location the asset was last transferred to.")
    transfer_date = fields.Date(
        string="Transfer Date", readonly=True, copy=False,
        help="Date of the last transfer.")
    transfer_reference = fields.Char(
        string="Transfer Reference", readonly=True, copy=False,
        help="Handover note / gate-pass reference for the last transfer.")

    # --------------------------------------------------------- disposal record
    disposal_date = fields.Date(
        string="Disposal Date", readonly=True, copy=False,
        help="Date the asset was disposed.")
    disposal_method = fields.Selection(
        DISPOSAL, string="Disposal Method", readonly=True, copy=False,
        help="How the asset left the organisation.")
    disposal_value = fields.Monetary(
        string="Disposal Value", currency_field="currency_id", readonly=True,
        copy=False,
        help="Proceeds received on disposal (0 for scrapped/donated). Cannot be "
             "negative.")
    disposal_reference = fields.Char(
        string="Disposal Reference", readonly=True, copy=False,
        help="Authorisation or receipt reference for the disposal.")
    disposal_move_id = fields.Many2one(
        "account.move", string="Disposal Journal Entry", readonly=True, copy=False,
        help="Accounting entry posted for the disposal, when booking is enabled.")

    # --------------------------------------------------------------- lost record
    lost_date = fields.Date(
        string="Lost Date", readonly=True, copy=False,
        help="Date the asset was reported lost or stolen.")
    lost_reason = fields.Text(
        string="Loss Reason", readonly=True, copy=False,
        help="Explanation recorded when the asset was marked lost.")

    # ---------------------------------------------------------------- lifecycle
    state = fields.Selection(
        [("in_use", "In Use"),
         ("in_store", "In Store"),
         ("transferred", "Transferred"),
         ("disposed", "Disposed"),
         ("lost", "Lost")],
        string="Status", default="in_use", required=True, tracking=True,
        copy=False,
        help="Lifecycle status. Transitions are driven by the header buttons and "
             "recorded in the immutable audit log.")

    _sql_constraints = [
        ("code_company_uniq",
         "unique(code, company_id)",
         "The Asset Tag must be unique per company."),
    ]

    # ============================================================== COMPUTES
    @api.depends("grant_id", "company_id")
    def _compute_currency_id(self):
        for a in self:
            a.currency_id = (
                a.grant_id.currency_id
                or a.company_id.currency_id
                or self.env.company.currency_id
            )

    def _compute_on_hand_qty(self):
        Quant = self.env["stock.quant"].sudo()
        for a in self:
            qty = 0.0
            if a.product_id and a.lot_id:
                quants = Quant.search([
                    ("product_id", "=", a.product_id.id),
                    ("lot_id", "=", a.lot_id.id),
                    ("location_id.usage", "=", "internal"),
                ])
                qty = sum(quants.mapped("quantity"))
            a.on_hand_qty = qty
            a.in_inventory = bool(a.product_id and a.lot_id and qty > 0)

    def _compute_move_line_count(self):
        SML = self.env["stock.move.line"].sudo()
        for a in self:
            a.move_line_count = SML.search_count([
                ("lot_id", "=", a.lot_id.id),
                ("state", "=", "done"),
            ]) if a.lot_id else 0

    @api.depends("code", "name")
    def _compute_display_name(self):
        for a in self:
            if a.code and a.code != _("New"):
                a.display_name = "[%s] %s" % (a.code, a.name or "")
            else:
                a.display_name = a.name or _("New Asset")

    @api.depends("acquisition_cost", "expense_id.amount", "currency_id")
    def _compute_cost_expense_mismatch(self):
        for a in self:
            if a.expense_id and a.expense_id.amount:
                precision = a.currency_id.rounding if a.currency_id else 0.01
                a.cost_expense_mismatch = float_compare(
                    a.acquisition_cost or 0.0, a.expense_id.amount,
                    precision_rounding=precision) != 0
            else:
                a.cost_expense_mismatch = False

    # ============================================================== ONCHANGE
    @api.onchange("expense_id")
    def _onchange_expense_id(self):
        """Auto-fill Acquisition Cost from the Source Expense amount. Stays
        editable afterwards - _compute_cost_expense_mismatch() will flag it
        with a soft warning if it's later changed to diverge."""
        if self.expense_id and self.expense_id.amount:
            self.acquisition_cost = self.expense_id.amount

    # ============================================================ CONSTRAINTS
    @api.constrains("acquisition_cost", "quantity")
    def _check_amounts(self):
        for a in self:
            if a.acquisition_cost is not None and a.acquisition_cost <= 0:
                raise ValidationError(_("Acquisition Cost must be greater than zero."))
            if a.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))

    @api.constrains("acquisition_date")
    def _check_acquisition_date(self):
        today = fields.Date.context_today(self)
        for a in self:
            if a.acquisition_date and a.acquisition_date > today:
                raise ValidationError(_("Acquisition Date cannot be in the future."))

    @api.constrains("expense_id", "grant_id")
    def _check_expense_grant(self):
        for a in self:
            if a.expense_id and a.expense_id.grant_id != a.grant_id:
                raise ValidationError(
                    _("The source expense must belong to the same grant as the asset."))

    @api.constrains("disposal_value")
    def _check_disposal_value(self):
        for a in self:
            if a.disposal_value and a.disposal_value < 0:
                raise ValidationError(_("Disposal Value cannot be negative."))

    # ============================================================== ORM hooks
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals.get("code") == _("New"):
                seq = self.env["ir.sequence"].next_by_code("arcs.asset")
                vals["code"] = seq or _("New")
        return super().create(vals_list)

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault("code", _("New"))
        return super().copy(default)

    # ============================================ INVENTORY HELPERS (private)
    def _check_not_terminal(self):
        for a in self:
            if a.state in TERMINAL_STATES:
                raise UserError(
                    _("Asset '%s' is already %s and can no longer be moved.")
                    % (a.display_name, dict(a._fields["state"].selection).get(a.state)))

    def _check_can_move(self):
        """A locked asset may only be moved/transferred by an Asset Manager."""
        for a in self:
            if a.locked_to_id and not self.env.user.has_group(
                    "arcs_asset.group_asset_manager"):
                raise AccessError(_(
                    "Asset '%s' is locked to %s. Only an Asset Manager can move "
                    "or transfer it.") % (a.display_name, a.locked_to_id.display_name))

    def _custody_location(self):
        self.ensure_one()
        loc = self.company_id.asset_custody_location_id
        if not loc:
            raise UserError(_(
                "No Custody (In-Use) location is configured. Set it under "
                "Settings > ARCS Asset Register before moving assets."))
        return loc

    def _store_location(self):
        self.ensure_one()
        loc = self.company_id.asset_store_location_id
        if not loc:
            raise UserError(_(
                "No Store location is configured. Set it under "
                "Settings > ARCS Asset Register before using 'Move to Store'."))
        return loc

    def _disposal_location(self):
        self.ensure_one()
        loc = self.company_id.asset_disposal_location_id
        if not loc:
            raise UserError(_(
                "No Disposal / Loss location is configured. Set it under "
                "Settings > ARCS Asset Register before disposing assets."))
        return loc

    def _internal_picking_type(self):
        self.ensure_one()
        wh = self.company_id.asset_warehouse_id
        pt = wh.int_type_id if wh else False
        if not pt:
            pt = self.env["stock.picking.type"].search([
                ("code", "=", "internal"),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
        if not pt:
            raise UserError(_(
                "No internal-transfer operation type is available. Configure an "
                "Asset Warehouse under Settings > ARCS Asset Register."))
        return pt

    def _ensure_inventory_item(self):
        """Create the product + serial lot and put 1 unit on hand in custody."""
        self.ensure_one()
        self._check_not_terminal()
        if not self.product_id:
            categ = (self.company_id.asset_product_category_id
                     or self.env.ref("product.product_category_all", raise_if_not_found=False))
            product = self.env["product.product"].create({
                "name": "%s [%s]" % (self.name, self.code),
                "type": "product",
                "tracking": "serial",
                "default_code": self.code,
                "categ_id": categ.id if categ else False,
                "list_price": 0.0,
                "standard_price": self.acquisition_cost or 0.0,
                "purchase_ok": False,
                "sale_ok": False,
            })
            self.product_id = product.id
        if not self.lot_id:
            lot = self.env["stock.lot"].create({
                "name": self.serial_number or self.code,
                "product_id": self.product_id.id,
                "company_id": self.company_id.id,
            })
            self.lot_id = lot.id
        if self.on_hand_qty <= 0:
            loc = self._custody_location()
            quant = self.env["stock.quant"].with_context(
                inventory_mode=True).create({
                    "product_id": self.product_id.id,
                    "location_id": loc.id,
                    "lot_id": self.lot_id.id,
                    "inventory_quantity": 1.0,
                })
            quant.action_apply_inventory()
            self.current_location_id = loc.id
        elif not self.current_location_id:
            quant = self.env["stock.quant"].sudo().search([
                ("product_id", "=", self.product_id.id),
                ("lot_id", "=", self.lot_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ], limit=1)
            self.current_location_id = quant.location_id.id
        return True

    def _make_internal_move(self, dest_location, owner=False, label=False):
        """Create and immediately validate an internal transfer of this unit."""
        self.ensure_one()
        self._ensure_inventory_item()
        src = self.current_location_id
        if not src:
            raise UserError(_("Cannot determine the current Inventory location."))
        if src.id == dest_location.id:
            raise UserError(_(
                "Asset '%s' is already in %s.") % (self.display_name, dest_location.display_name))
        pt = self._internal_picking_type()
        picking = self.env["stock.picking"].create({
            "picking_type_id": pt.id,
            "location_id": src.id,
            "location_dest_id": dest_location.id,
            "origin": label and "%s / %s" % (self.code, label) or self.code,
            "company_id": self.company_id.id,
            "move_ids": [(0, 0, {
                "name": label or self.name,
                "product_id": self.product_id.id,
                "product_uom_qty": 1.0,
                "product_uom": self.product_id.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest_location.id,
                "company_id": self.company_id.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        move = picking.move_ids[:1]
        if move.move_line_ids:
            ml = move.move_line_ids[:1]
            ml.lot_id = self.lot_id.id
            ml.quantity = 1.0
            if owner:
                ml.owner_id = owner.id
        else:
            self.env["stock.move.line"].create({
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": self.product_id.id,
                "product_uom_id": self.product_id.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest_location.id,
                "lot_id": self.lot_id.id,
                "quantity": 1.0,
                "owner_id": owner.id if owner else False,
                "company_id": self.company_id.id,
            })
        picking.with_context(skip_backorder=True, skip_sms=True)._action_done()
        self.current_location_id = dest_location.id
        return picking

    # ============================================================ LIFECYCLE
    def action_set_in_store(self):
        """Move to Store: real internal transfer into the Store location."""
        for a in self:
            a._check_not_terminal()
            a._check_can_move()
            dest = a._store_location()
            a._make_internal_move(dest, owner=a.locked_to_id or a.custodian_id,
                                   label=_("Move to Store"))
            a._transition("in_store", "move-to-store",
                          comment=_("Moved to store location %s.") % dest.display_name)
        return True

    def action_set_in_use(self):
        """Return to Use: real internal transfer back to the Custody location."""
        for a in self:
            a._check_not_terminal()
            a._check_can_move()
            dest = a._custody_location()
            a._make_internal_move(dest, owner=a.locked_to_id or a.custodian_id,
                                   label=_("Return to Use"))
            a._transition("in_use", "return-to-use",
                          comment=_("Returned to custody location %s.") % dest.display_name)
        return True

    def action_transfer(self):
        """Open the Transfer wizard (collects destination + custodian)."""
        self.ensure_one()
        self._check_not_terminal()
        self._check_can_move()
        return self._open_wizard("arcs.asset.transfer.wizard",
                                 _("Transfer Asset"))

    def action_dispose(self):
        self.ensure_one()
        self._check_not_terminal()
        return self._open_wizard("arcs.asset.dispose.wizard",
                                 _("Dispose Asset"))

    def action_mark_lost(self):
        self.ensure_one()
        self._check_not_terminal()
        return self._open_wizard("arcs.asset.lost.wizard",
                                 _("Mark Asset Lost"))

    def _open_wizard(self, model, title):
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": model,
            "view_mode": "form",
            "target": "new",
            "context": {"default_asset_id": self.id, "active_id": self.id},
        }

    # ----- worker methods called by the wizards --------------------------
    def _do_transfer(self, vals):
        self.ensure_one()
        self._check_not_terminal()
        self._check_can_move()
        dest = vals["dest_location_id"]
        custodian = vals["custodian_id"]
        self._make_internal_move(dest, owner=custodian, label=_("Transfer"))
        self.write({
            "custodian_id": custodian.id,
            "locked_to_id": custodian.id,
            "transfer_partner_id": custodian.id,
            "transfer_to": custodian.display_name,
            "transfer_location_id": dest.id,
            "transfer_date": vals.get("transfer_date") or fields.Date.context_today(self),
            "transfer_reference": vals.get("reference"),
        })
        self._transition("transferred", "transfer", comment=_(
            "Transferred to %s at %s. Locked to %s.")
            % (custodian.display_name, dest.display_name, custodian.display_name))
        return True

    def _do_dispose(self, vals):
        self.ensure_one()
        self._check_not_terminal()
        if self.in_inventory:
            dest = self._disposal_location()
            self._make_internal_move(dest, label=_("Disposal"))
        self.write({
            "disposal_date": vals.get("disposal_date") or fields.Date.context_today(self),
            "disposal_method": vals["disposal_method"],
            "disposal_value": vals.get("disposal_value") or 0.0,
            "disposal_reference": vals.get("reference"),
        })
        if self.company_id.asset_book_disposal:
            self._book_disposal_entry()
        method = dict(self._fields["disposal_method"].selection).get(self.disposal_method)
        self._transition("disposed", "dispose", comment=_(
            "Disposed (%s), value %s.") % (method, self.disposal_value))
        return True

    def _do_lost(self, vals):
        self.ensure_one()
        self._check_not_terminal()
        if self.in_inventory:
            dest = self._disposal_location()
            self._make_internal_move(dest, label=_("Loss"))
        self.write({
            "lost_date": vals.get("lost_date") or fields.Date.context_today(self),
            "lost_reason": vals.get("reason"),
        })
        self._transition("lost", "lost", comment=_(
            "Marked lost: %s") % (self.lost_reason or _("no reason given")))
        return True

    def _book_disposal_entry(self):
        self.ensure_one()
        company = self.company_id
        journal = company.asset_disposal_journal_id
        income = company.asset_disposal_income_account_id
        loss = company.asset_disposal_loss_account_id
        if not (journal and income and loss):
            raise UserError(_(
                "Disposal booking is enabled but the Disposal Journal and the "
                "proceeds/write-off accounts are not all configured."))
        amount = self.disposal_value or 0.0
        analytic = {}
        aa = getattr(self.grant_id, "analytic_account_id", False)
        if aa:
            analytic = {aa.id: 100.0}
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.disposal_date or fields.Date.context_today(self),
            "ref": _("Asset disposal %s") % self.code,
            "line_ids": [
                (0, 0, {
                    "name": _("Disposal proceeds %s") % self.code,
                    "account_id": loss.id,
                    "debit": amount,
                    "credit": 0.0,
                    "analytic_distribution": analytic or False,
                }),
                (0, 0, {
                    "name": _("Disposal income %s") % self.code,
                    "account_id": income.id,
                    "debit": 0.0,
                    "credit": amount,
                    "analytic_distribution": analytic or False,
                }),
            ],
        })
        if amount:
            move.action_post()
        self.disposal_move_id = move.id
        return move

    # ----- smart buttons -------------------------------------------------
    def action_view_stock_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Inventory Moves"),
            "res_model": "stock.move.line",
            "view_mode": "tree,form",
            "domain": [("lot_id", "=", self.lot_id.id), ("state", "=", "done")],
            "context": {"search_default_done": 1},
        }

    def action_view_disposal_move(self):
        self.ensure_one()
        if not self.disposal_move_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Disposal Entry"),
            "res_model": "account.move",
            "res_id": self.disposal_move_id.id,
            "view_mode": "form",
        }

    # ---------------- voucher printing ----------------
    def _voucher_title(self):
        if self.env.context.get("print_disposal_voucher"):
            return _("Asset Disposal Voucher")
        return _("Asset Registration Voucher")

    def _voucher_subtitle(self):
        if self.env.context.get("print_disposal_voucher"):
            method = dict(self._fields["disposal_method"].selection).get(self.disposal_method)
            return " | ".join(p for p in (_("Asset Tag: %s") % (self.code or ""), method) if p)
        return "Asset Tag: %s" % (self.code or "")

    def _voucher_number(self):
        if self.env.context.get("print_disposal_voucher"):
            return self.disposal_reference or self.code
        return self.code

    def _voucher_date(self):
        if self.env.context.get("print_disposal_voucher"):
            return self.disposal_date
        return self.acquisition_date

    def _voucher_context_line(self):
        if self.env.context.get("print_disposal_voucher"):
            parts = [p for p in (self.grant_id.name, self.project_id.name) if p]
            return " | ".join(parts) if parts else False
        parts = [p for p in (self.grant_id.name, self.project_id.name,
                             dict(self._fields["category"].selection).get(self.category)) if p]
        return " | ".join(parts) if parts else False

    def _voucher_is_posted(self):
        if self.env.context.get("print_disposal_voucher"):
            return bool(self.disposal_move_id and self.disposal_move_id.state == "posted")
        return False

    def _voucher_lines(self):
        self.ensure_one()
        if self.env.context.get("print_disposal_voucher"):
            return self._disposal_voucher_lines()
        source = self.expense_id.name if self.expense_id else self.grant_id.name
        return [
            {"account": _("Fixed Assets - %s") % (dict(self._fields["category"].selection).get(self.category) or ""),
             "description": self.name, "debit": self.acquisition_cost, "credit": 0.0},
            {"account": _("Funded via %s") % (source or _("Grant")),
             "description": _("Acquisition cost"), "debit": 0.0, "credit": self.acquisition_cost},
        ]

    def _disposal_voucher_lines(self):
        """Reflect the actual posted disposal move when one exists (booking
        enabled); otherwise fall back to a synthetic, indicative pair of
        lines mirroring what _book_disposal_entry() would post."""
        self.ensure_one()
        if self.disposal_move_id:
            return [{
                "account": line.account_id.display_name,
                "description": line.name or "",
                "debit": line.debit,
                "credit": line.credit,
            } for line in self.disposal_move_id.line_ids]
        amount = self.disposal_value or 0.0
        method = dict(self._fields["disposal_method"].selection).get(self.disposal_method) or ""
        return [
            {"account": _("Disposal Loss / Write-off"),
             "description": _("Disposal of %(asset)s (%(method)s)") % {
                 "asset": self.name, "method": method},
             "debit": amount, "credit": 0.0},
            {"account": _("Disposal Proceeds"),
             "description": _("Proceeds / write-off value"),
             "debit": 0.0, "credit": amount},
        ]

    def action_print_voucher(self):
        self.ensure_one()
        return self.env.ref("arcs_asset.action_report_asset_voucher").report_action(self)

    def action_print_disposal_voucher(self):
        self.ensure_one()
        if self.state != "disposed":
            raise UserError(_("Only disposed assets can print a Disposal Voucher."))
        return self.env.ref(
            "arcs_asset.action_report_asset_disposal_voucher"
        ).with_context(print_disposal_voucher=True).report_action(self)
