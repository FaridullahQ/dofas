from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class ArcsProject(models.Model):
    _inherit = "arcs.project"

    def _grant_remaining_for_planning(self, grant):
        """How much of `grant`'s own Approved Amount is still unclaimed by
        OTHER projects already planned directly under it - mirrors
        _program_remaining_for_planning() one level up, same reasoning:
        several projects sharing one donor's grant can never together plan
        more than that grant was actually approved for. Only meaningful
        for grants on the One Donor, Multiple Projects model - for every
        other funding model, projects are a free-form planning tool with
        no ceiling of their own imposed by this module.

        All projects under one grant already share that grant's own
        currency (both derive from the same grant), so no conversion is
        needed here, unlike the Program-level check which must convert
        across projects that can belong to different grants/currencies.

        Excludes this project's OWN prior claim (via `self._origin`, safe
        to call from an onchange on an unsaved record too)."""
        self.ensure_one()
        if not grant or grant.funding_model != "donor_multi_project":
            return 0.0
        domain = [("grant_id", "=", grant.id)]
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        siblings = self.search(domain)
        siblings_planned = sum(siblings.mapped("planned_cost"))
        return grant.approved_amount - siblings_planned

    @api.constrains("planned_cost", "grant_id")
    def _check_planned_within_grant_for_donor_multi_project(self):
        for p in self.filtered(lambda x: x.grant_id.funding_model == "donor_multi_project"):
            remaining = p._grant_remaining_for_planning(p.grant_id)
            if float_compare(p.planned_cost, remaining,
                             precision_rounding=p.currency_id.rounding or 0.01) > 0:
                raise ValidationError(_(
                    "Planned cost exceeds what's still available under grant "
                    "'%(g)s' once other projects' own Planned Cost is taken into "
                    "account: %(remaining).2f %(cur)s remains for this project to "
                    "plan against. This grant uses the One Donor, Multiple "
                    "Projects model, so its projects' combined plans can never "
                    "exceed the grant's Approved Amount.",
                    g=p.grant_id.display_name, remaining=remaining,
                    cur=p.currency_id.name or ""))

    @api.onchange("grant_id")
    def _onchange_grant_id_donor_multi_project(self):
        if (self.grant_id and self.grant_id.funding_model == "donor_multi_project"
                and not self.planned_cost):
            self.planned_cost = max(self._grant_remaining_for_planning(self.grant_id), 0.0)
