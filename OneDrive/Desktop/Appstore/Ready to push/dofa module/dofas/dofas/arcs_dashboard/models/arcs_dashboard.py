from odoo import api, fields, models


class ArcsDashboard(models.AbstractModel):
    """Filter-aware KPI/aggregate provider for the OWL portfolio dashboard.

    Snapshot figures (planned/committed/available) come from arcs.budget.line.
    Date-accurate actuals and all dimensional/time breakdowns are aggregated
    from POSTED arcs.expense records (the vouchers), so the dashboard can be
    sliced by date and by program / project / activity / budget line / zone.
    All amounts are converted to the company currency using the configured
    rate policy (transaction = today, inception = grant start date).
    """

    _name = "arcs.dashboard"
    _description = "ARCS Grant Portfolio Dashboard (data provider)"

    # ------------------------------------------------------------------ options
    @api.model
    def get_filter_options(self):
        company = self.env.company

        def rows(model, fields_=None, domain=None, order="name"):
            if model not in self.env:
                return []
            return self.env[model].search_read(domain or [], fields_ or ["name"], order=order)

        programs = rows("arcs.program")
        projects = self.env["arcs.project"].search_read([], ["name", "program_id"]) \
            if "arcs.project" in self.env else []
        activities = self.env["arcs.activity"].search_read([], ["name", "project_id"]) \
            if "arcs.activity" in self.env else []
        grants = self.env["arcs.grant"].search_read(
            [("company_id", "=", company.id)], ["display_name", "donor_id"], order="date_start desc")
        donors = rows("arcs.donor")
        lines = self.env["arcs.budget.line"].search_read(
            [("grant_id.company_id", "=", company.id)], ["name", "grant_id"], order="name")
        zones = rows("arcs.zone") if "arcs.zone" in self.env else []
        return {
            "programs": [{"id": r["id"], "name": r["name"]} for r in programs],
            "projects": [{"id": r["id"], "name": r["name"],
                          "program_id": r["program_id"][0] if r.get("program_id") else 0} for r in projects],
            "activities": [{"id": r["id"], "name": r["name"],
                            "project_id": r["project_id"][0] if r.get("project_id") else 0} for r in activities],
            "grants": [{"id": r["id"], "name": r["display_name"]} for r in grants],
            "donors": [{"id": r["id"], "name": r["name"]} for r in donors],
            "lines": [{"id": r["id"], "name": r["name"],
                       "grant_id": r["grant_id"][0] if r.get("grant_id") else 0} for r in lines],
            "zones": [{"id": r["id"], "name": r["name"]} for r in zones],
        }

    # ------------------------------------------------------------------- helpers
    @api.model
    def _parse(self, f):
        f = f or {}

        def i(k):
            v = f.get(k)
            try:
                return int(v) if v not in (None, "", "ALL", "0", 0) else None
            except (TypeError, ValueError):
                return None
        return {
            "date_from": f.get("date_from") or None,
            "date_to": f.get("date_to") or None,
            "grant": i("grant_id"), "donor": i("donor_id"), "program": i("program_id"),
            "project": i("project_id"), "activity": i("activity_id"),
            "line": i("budget_line_id"), "zone": i("zone_id"),
        }

    # ---------------------------------------------------------------- main entry
    @api.model
    def get_dashboard_data(self, filters=None):
        company = self.env.company
        comp_ccy = company.currency_id
        policy = company.arcs_currency_rate_policy or "transaction"
        today = fields.Date.context_today(self)
        F = self._parse(filters)

        Grant = self.env["arcs.grant"]
        Line = self.env["arcs.budget.line"]
        Expense = self.env["arcs.expense"]
        sel_cat = dict(Line._fields["category"].selection)

        def conv(amount, grant):
            if not amount:
                return 0.0
            gc = grant.currency_id if grant else comp_ccy
            if not gc or gc == comp_ccy:
                return amount
            date = grant.date_start if (policy == "inception" and grant and grant.date_start) else today
            return gc._convert(amount, comp_ccy, company, date)

        # ---- domains -------------------------------------------------------
        bdom = [("grant_id.company_id", "=", company.id)]
        edom = [("state", "=", "posted"), ("grant_id.company_id", "=", company.id)]
        if F["grant"]:
            bdom += [("grant_id", "=", F["grant"])]; edom += [("grant_id", "=", F["grant"])]
        if F["donor"]:
            bdom += [("grant_id.donor_id", "=", F["donor"])]; edom += [("grant_id.donor_id", "=", F["donor"])]
        if F["program"]:
            bdom += [("project_id.program_id", "=", F["program"])]; edom += [("project_id.program_id", "=", F["program"])]
        if F["project"]:
            bdom += [("project_id", "=", F["project"])]; edom += [("project_id", "=", F["project"])]
        if F["line"]:
            bdom += [("id", "=", F["line"])]; edom += [("budget_line_id", "=", F["line"])]
        if F["activity"]:
            edom += [("activity_id", "=", F["activity"])]
        if F["zone"] and "zone_id" in Expense._fields:
            edom += [("zone_id", "=", F["zone"])]
        if F["date_from"]:
            edom += [("date", ">=", F["date_from"])]
        if F["date_to"]:
            edom += [("date", "<=", F["date_to"])]

        # ---- grants in scope ----------------------------------------------
        if F["program"] or F["project"] or F["line"]:
            scope_grants = Line.search(bdom).mapped("grant_id")
        else:
            gdom = [("company_id", "=", company.id)]
            if F["grant"]:
                gdom += [("id", "=", F["grant"])]
            if F["donor"]:
                gdom += [("donor_id", "=", F["donor"])]
            scope_grants = Grant.search(gdom, order="approved_amount desc")
        gmap = {g.id: g for g in scope_grants}

        # ---- per-grant snapshot (planned/committed) -----------------------
        snap = {}
        if scope_grants:
            for row in Line.read_group(bdom + [("grant_id", "in", scope_grants.ids)],
                                       ["planned_amount:sum", "committed_amount:sum"], ["grant_id"]):
                snap[row["grant_id"][0]] = (row.get("planned_amount") or 0.0,
                                            row.get("committed_amount") or 0.0)
        # actual per grant from posted expenses (date-accurate)
        actual_g = {}
        for row in Expense.read_group(edom, ["amount:sum"], ["grant_id"]):
            if row.get("grant_id"):
                actual_g[row["grant_id"][0]] = row.get("amount") or 0.0
        # received per grant
        received_g = {}
        if "arcs.fund.receipt" in self.env and scope_grants:
            for row in self.env["arcs.fund.receipt"].read_group(
                    [("grant_id", "in", scope_grants.ids), ("state", "=", "posted")],
                    ["amount:sum"], ["grant_id"]):
                received_g[row["grant_id"][0]] = row.get("amount") or 0.0

        totals = dict(approved=0.0, planned=0.0, committed=0.0, actual=0.0,
                      received=0.0, available=0.0, cash=0.0)
        grant_rows, alerts = [], []
        for g in scope_grants:
            planned_gc, committed_gc = snap.get(g.id, (0.0, 0.0))
            approved = conv(g.approved_amount or 0.0, g)
            planned = conv(planned_gc, g)
            committed = conv(committed_gc, g)
            actual = conv(actual_g.get(g.id, 0.0), g)
            recd = conv(received_g.get(g.id, 0.0), g)
            base = approved or planned
            available = base - committed - actual
            util = (100.0 * (committed + actual) / base) if base else 0.0
            exp_days = (g.date_end - today).days if g.date_end else None
            grant_rows.append({
                "id": g.id, "code": g.display_name, "donor": g.donor_id.display_name or "",
                "approved": approved, "committed": committed, "actual": actual,
                "available": available, "received": recd, "utilization": util,
                "status": dict(g._fields["state"].selection).get(g.state, g.state or ""),
                "exp_days": exp_days,
            })
            totals["approved"] += approved
            totals["planned"] += planned
            totals["committed"] += committed
            totals["actual"] += actual
            totals["received"] += recd
            if util >= 90:
                alerts.append({"level": "danger", "icon": "fa-fire",
                               "text": "%s at %.0f%% utilization \u2014 review before next commitment" % (g.display_name, util)})
            if recd - actual < 0:
                alerts.append({"level": "warning", "icon": "fa-exclamation-triangle",
                               "text": "%s cash on hand below spend \u2014 awaiting draw-down" % g.display_name})
            if exp_days is not None and 0 <= exp_days <= 30:
                alerts.append({"level": "warning", "icon": "fa-calendar-times-o",
                               "text": "%s grant period ends in %d days" % (g.display_name, exp_days)})
        base_total = totals["approved"] or totals["planned"]
        totals["available"] = base_total - totals["committed"] - totals["actual"]
        totals["cash"] = totals["received"] - totals["actual"]
        totals["utilization"] = (100.0 * (totals["committed"] + totals["actual"]) / base_total) if base_total else 0.0

        # ---- time series (monthly actual) ---------------------------------
        months = {}
        for row in Expense.read_group(edom, ["amount:sum"], ["date:month"], lazy=False):
            label = row.get("date:month") or "\u2014"
            rng = (row.get("__range") or {}).get("date:month") or {}
            start = rng.get("from") or label
            g = gmap.get(row.get("grant_id") and row["grant_id"][0])
            months.setdefault(label, {"value": 0.0, "sort": start})
            months[label]["value"] += conv(row.get("amount") or 0.0, g)
        time_series = [{"label": k, "value": v["value"]} for k, v in
                       sorted(months.items(), key=lambda kv: kv[1]["sort"])]

        # ---- by program (planned/committed/actual) ------------------------
        projmap = {}
        if "arcs.project" in self.env:
            for p in self.env["arcs.project"].search_read([], ["program_id"]):
                projmap[p["id"]] = p["program_id"][1] if p.get("program_id") else "Unassigned"
        prog = {}
        for row in Line.read_group(bdom, ["planned_amount:sum", "committed_amount:sum"],
                                   ["project_id", "grant_id"], lazy=False):
            g = gmap.get(row.get("grant_id") and row["grant_id"][0]) or (
                Grant.browse(row["grant_id"][0]) if row.get("grant_id") else None)
            name = projmap.get(row["project_id"][0], "Unassigned") if row.get("project_id") else "Unassigned"
            d = prog.setdefault(name, {"planned": 0.0, "committed": 0.0, "actual": 0.0})
            d["planned"] += conv(row.get("planned_amount") or 0.0, g)
            d["committed"] += conv(row.get("committed_amount") or 0.0, g)
        for row in Expense.read_group(edom, ["amount:sum"], ["project_id", "grant_id"], lazy=False):
            g = gmap.get(row.get("grant_id") and row["grant_id"][0]) or (
                Grant.browse(row["grant_id"][0]) if row.get("grant_id") else None)
            name = projmap.get(row["project_id"][0], "Unassigned") if row.get("project_id") else "Unassigned"
            d = prog.setdefault(name, {"planned": 0.0, "committed": 0.0, "actual": 0.0})
            d["actual"] += conv(row.get("amount") or 0.0, g)
        programs = [{"label": k, "planned": v["planned"], "committed": v["committed"],
                     "actual": v["actual"]} for k, v in prog.items()]
        programs.sort(key=lambda x: x["planned"] or x["actual"], reverse=True)

        # ---- by category (donut) ------------------------------------------
        linecat = {}
        for l in Line.search_read(bdom, ["category"]):
            linecat[l["id"]] = sel_cat.get(l["category"], "Uncategorised")
        cat = {}
        for row in Expense.read_group(edom, ["amount:sum"], ["budget_line_id", "grant_id"], lazy=False):
            g = gmap.get(row.get("grant_id") and row["grant_id"][0]) or (
                Grant.browse(row["grant_id"][0]) if row.get("grant_id") else None)
            label = linecat.get(row["budget_line_id"][0], "Uncategorised") if row.get("budget_line_id") else "Uncategorised"
            cat[label] = cat.get(label, 0.0) + conv(row.get("amount") or 0.0, g)
        categories = [{"label": k, "value": v} for k, v in cat.items() if v]
        categories.sort(key=lambda c: c["value"], reverse=True)

        # ---- by zone ------------------------------------------------------
        zones = []
        if "zone_id" in Expense._fields:
            zmap = {z["id"]: z["name"] for z in self.env["arcs.zone"].search_read([], ["name"])} \
                if "arcs.zone" in self.env else {}
            zc = {}
            for row in Expense.read_group(edom, ["amount:sum"], ["zone_id", "grant_id"], lazy=False):
                g = gmap.get(row.get("grant_id") and row["grant_id"][0]) or (
                    Grant.browse(row["grant_id"][0]) if row.get("grant_id") else None)
                label = zmap.get(row["zone_id"][0], "Unassigned") if row.get("zone_id") else "Unassigned"
                zc[label] = zc.get(label, 0.0) + conv(row.get("amount") or 0.0, g)
            zones = [{"label": k, "value": v} for k, v in zc.items() if v]
            zones.sort(key=lambda z: z["value"], reverse=True)

        # ---- top budget lines by utilization ------------------------------
        top_lines = []
        for l in Line.search(bdom):
            planned = conv(l.planned_amount or 0.0, l.grant_id)
            actual = conv(l.actual_amount or 0.0, l.grant_id)
            committed = conv(l.committed_amount or 0.0, l.grant_id)
            util = (100.0 * (committed + actual) / planned) if planned else 0.0
            top_lines.append({"name": l.name, "grant": l.grant_id.display_name or "",
                              "planned": planned, "actual": actual, "utilization": util})
        top_lines.sort(key=lambda x: x["utilization"], reverse=True)
        top_lines = top_lines[:8]

        # ---- advances -----------------------------------------------------
        advances, outstanding_total = [], 0.0
        if "arcs.advance" in self.env:
            Adv = self.env["arcs.advance"]
            advdom = [("company_id", "=", company.id), ("state", "=", "issued")]
            if F["zone"]:
                advdom += [("zone_id", "=", F["zone"])]
            if F["grant"]:
                advdom += [("grant_id", "=", F["grant"])]
            for row in Adv.read_group(advdom, ["amount:sum", "reported_amount:sum",
                                               "outstanding_amount:sum"], ["zone_id"], lazy=False):
                label = row["zone_id"][1] if row.get("zone_id") else "Employee / HQ"
                advances.append({"label": label, "sent": row.get("amount") or 0.0,
                                 "reported": row.get("reported_amount") or 0.0,
                                 "outstanding": row.get("outstanding_amount") or 0.0})
                outstanding_total += row.get("outstanding_amount") or 0.0
            advances.sort(key=lambda a: a["outstanding"], reverse=True)
        totals["outstanding_advances"] = outstanding_total

        # ---- counts & overdue ---------------------------------------------
        totals["grants"] = len(scope_grants)
        totals["expenses"] = Expense.search_count(edom)
        totals["pending_requests"] = 0
        if "arcs.spend.request" in self.env:
            rdom = [("state", "in", ("submitted", "committed"))]
            if F["grant"]:
                rdom += [("grant_id", "=", F["grant"])]
            if F["zone"]:
                rdom += [("zone_id", "=", F["zone"])]
            totals["pending_requests"] = self.env["arcs.spend.request"].search_count(rdom)
        overdue = 0
        if "arcs.donor.report" in self.env:
            odom = [("is_overdue", "=", True)]
            if "company_id" in self.env["arcs.donor.report"]._fields:
                odom += [("company_id", "=", company.id)]
            overdue = self.env["arcs.donor.report"].search_count(odom)
        totals["overdue"] = overdue
        if overdue:
            alerts.append({"level": "danger", "icon": "fa-file-text-o",
                           "text": "%d donor report(s) overdue" % overdue})

        multi_ccy = any(g.currency_id and g.currency_id != comp_ccy for g in scope_grants)
        return {
            "totals": totals, "grants": grant_rows, "categories": categories,
            "programs": programs, "zones": zones, "time_series": time_series,
            "top_lines": top_lines, "advances": advances, "alerts": alerts,
            "currency": comp_ccy.symbol or "", "currency_name": comp_ccy.name or "",
            "rate_policy": policy, "multi_currency": multi_ccy, "filters": F,
        }
