import re
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_]{1,11}$")



class McitDonor(models.Model):
    _name = "mcit.donor"
    _description = "Donor"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(string="Donor Name", required=True, tracking=True,
                       help="Enter donor organization name")
    code = fields.Char(string="Donor Code", required=True, copy=False, index=True,
                       help="Unique short code identifying this donor.")
    active = fields.Boolean(default=True)
    donor_type = fields.Selection(
        [("bilateral", "Bilateral"), ("multilateral", "Multilateral"),
         ("foundation", "Foundation"), ("government", "Government"),
         ("ingo", "INGO"), ("corporate", "Corporate"), ("individual", "Individual")],
        string="Donor Type", required=True, default="multilateral")
    partner_id = fields.Many2one("res.partner", string="Contact",
                                 help="Linked contact / organization record.")
    country_id = fields.Many2one("res.country", string="Country")
    currency_id = fields.Many2one(
        "res.currency", string="Currency",
        default=lambda self: self.env.company.currency_id)
    email = fields.Char(string="Email")
    website = fields.Char(string="Website")
    reporting_frequency = fields.Selection(
        [("monthly", "Monthly"), ("quarterly", "Quarterly"),
         ("semiannual", "Semi-annual"), ("annual", "Annual"), ("final", "Final only")],
        string="Reporting Frequency", default="quarterly",
        help="Default cadence at which this donor requires reports.")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "The Donor Code must be unique."),
    ]

    @api.constrains("email")
    def _check_email(self):
        for d in self.filtered("email"):
            if not EMAIL_RE.match(d.email.strip()):
                raise ValidationError(_("Please enter a valid email address for donor '%s'.", d.name))

    @api.constrains("active")
    def _check_active_use(self):
        # Active status required to be used by grants is enforced at grant level.
        return True

    @api.onchange("code")
    def _onchange_code_normalize(self):
        """UX: tidy the code as the user types (upper-case, no surrounding spaces)."""
        if self.code:
            self.code = self.code.strip().upper()

    @api.onchange("website")
    def _onchange_website_scheme(self):
        """UX: assume https:// when the user omits the scheme."""
        if self.website and not re.match(r"^https?://", self.website.strip(), re.I):
            self.website = "https://" + self.website.strip()

    @api.constrains("code")
    def _check_code_format(self):
        for d in self.filtered("code"):
            if not CODE_RE.match(d.code.strip()):
                raise ValidationError(_(
                    "Invalid donor code \u201c%(code)s\u201d.\n\n"
                    "Use 2\u201312 characters \u2014 letters, digits, dash or underscore \u2014 "
                    "starting with a letter or digit.\n"
                    "Examples: UNDP, ECHO, WB-2024.",
                    code=d.code))

    @api.constrains("website")
    def _check_website(self):
        for d in self.filtered("website"):
            if not re.match(r"^https?://[^\s.]+\.[^\s]{2,}$", d.website.strip(), re.I):
                raise ValidationError(_(
                    "\u201c%(url)s\u201d doesn't look like a valid website for donor "
                    "\u2018%(name)s\u2019.\n\nEnter a full address, e.g. https://www.donor.org",
                    url=d.website, name=d.name))