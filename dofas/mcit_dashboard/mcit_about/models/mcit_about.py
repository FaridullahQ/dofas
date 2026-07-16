from odoo import api, fields, models


class McitAbout(models.TransientModel):
    _name = "mcit.about"
    _description = "About & Help"

    company_name = fields.Char(readonly=True)
    company_logo = fields.Binary(readonly=True)
    company_email = fields.Char(readonly=True)
    company_phone = fields.Char(readonly=True)
    company_website = fields.Char(readonly=True)
    company_address = fields.Char(readonly=True)
    suite_version = fields.Char(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        c = self.env.company
        parts = [c.street, c.street2, c.city, c.zip, c.country_id.name]
        module = self.env["ir.module.module"].sudo().search(
            [("name", "=", "mcit_donor_management")], limit=1)
        res.update({
            "company_name": c.name,
            "company_logo": c.logo,
            "company_email": c.email or "",
            "company_phone": c.phone or "",
            "company_website": c.website or "",
            "company_address": ", ".join([p for p in parts if p]),
            "suite_version": (module.installed_version or "17.0") if module else "17.0",
        })
        return res
