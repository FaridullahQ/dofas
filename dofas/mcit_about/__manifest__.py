{
    "name": "MCIT Donor Mgmt - About & Help",
    "version": "17.0.1.0.1",
    "summary": "Optional About & Help menu: company info, overall flow and glossary.",
    "description": "Adds an 'About & Help' page (company details, the end-to-end process "
                   "flow and a glossary of terms). The menu is shown only when enabled "
                   "from MCIT Settings.",
    "category": "Accounting/MCIT Donor Management",
    "license": "LGPL-3",
    "author": "MCIT",
    "depends": ["mcit_base"],
    "data": [
        "security/mcit_about_groups.xml",
        "security/ir.model.access.csv",
        "views/mcit_about_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
