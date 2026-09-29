{
    "name": "ARCS Donor Mgmt - Asset Register",
    "version": "17.0.2.0.3",
    "summary": "Grant-funded asset register with real Inventory integration: "
               "store moves, custodian-locked transfers, audited disposal.",
    "description": """
Grant-Funded Asset Register (Inventory-integrated)
==================================================
Tracks fixed assets acquired with donor funds and mirrors each one into Odoo
Inventory as a serial-tracked product (one lot = one physical unit), so the
lifecycle actions perform REAL stock moves:

* Move to Store  -> internal transfer into the configured Store location.
* Return to Use  -> internal transfer back to the Custody location.
* Transfer       -> wizard: choose destination location + custodian; performs an
                    internal transfer and LOCKS the unit to that custodian
                    (stock owner) so only an Asset Manager can move it again.
* Dispose / Lost -> wizard: removes the unit from on-hand stock (to the
                    configured Disposal/Loss location) and, optionally, books a
                    disposal journal entry.

Every transition is written to the immutable audit log via the approval mixin.
Feeds the donor Asset report.
""",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_grant", "arcs_program", "arcs_expense", "account", "stock"],
    "data": [
        "security/arcs_asset_groups.xml",
        "security/ir.model.access.csv",
        "security/arcs_asset_rules.xml",
        "data/ir_sequence.xml",
        "report/asset_voucher_report.xml",
        "report/asset_disposal_voucher_report.xml",
        "wizards/asset_wizard_views.xml",
        "views/arcs_asset_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
