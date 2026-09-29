{
    "name": "ARCS Donor Mgmt - Dashboards",
    "version": "17.0.1.2.3",
    "summary": "Community monitoring: OWL portfolio dashboard + pivot/graph views.",
    "category": "Accounting/ARCS Donor Management",
    "license": "LGPL-3", "author": "ARCS",
    "depends": ["arcs_budget", "arcs_expense", "arcs_fund", "arcs_report",
                "arcs_program", "arcs_zone", "arcs_advance"],
    "data": [
        "views/arcs_dashboard_views.xml",
        "views/menus.xml",
        "views/dashboard_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "arcs_dashboard/static/src/scss/dashboard.scss",
            "arcs_dashboard/static/src/js/dashboard.js",
            "arcs_dashboard/static/src/xml/dashboard.xml",
        ],
    },
    "installable": True,
}
