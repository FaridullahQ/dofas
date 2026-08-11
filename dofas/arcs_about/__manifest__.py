{
    "name": "ARCS Donor Mgmt - About & Help",
    "version": "17.0.1.2.0",
    "summary": "Help menu: User Guide, FAQs, and Support Contact. Optional, enabled from ARCS Settings.",
    "description": "Adds a 'Help' menu with three pages: User Guide (company details, the "
                   "end-to-end process flow and a glossary of terms), FAQs (answers to common "
                   "questions), and Support Contact (how to reach the organisation directly). "
                   "The menu is shown only when enabled from ARCS Settings.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3",
    "author": "ARCS",
    "depends": ["arcs_base"],
    "data": [
        "security/arcs_about_groups.xml",
        "security/ir.model.access.csv",
        "views/arcs_about_views.xml",
        "views/arcs_faq_views.xml",
        "views/arcs_support_contact_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
