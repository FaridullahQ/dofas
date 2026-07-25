/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

const COLORS = ["#1F3A5F", "#C9A24B", "#1D9E75", "#378ADD", "#D85A30", "#7F77DD", "#6B7280", "#B0843B"];

function fmtDate(d) {
    return d.toISOString().slice(0, 10);
}

export class McitDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            lastUpdated: null,
            activePreset: "",
            selectedGrantId: null,
            sort: { grants: { key: "approved", dir: "desc" }, top_lines: { key: "utilization", dir: "desc" } },
            options: { programs: [], projects: [], activities: [], grants: [], donors: [], lines: [], zones: [] },
            filters: {
                date_from: "", date_to: "", program_id: "", project_id: "", activity_id: "",
                grant_id: "", donor_id: "", budget_line_id: "", zone_id: "",
            },
            data: {
                totals: {}, grants: [], categories: [], programs: [], zones: [],
                time_series: [], top_lines: [], advances: [], alerts: [], currency: "",
            },
        });
        onWillStart(async () => {
            this.state.options = await this.orm.call("mcit.dashboard", "get_filter_options", []);
            await this.load();
        });
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("mcit.dashboard", "get_dashboard_data", [this.state.filters]);
        this.state.loading = false;
        this.state.lastUpdated = new Date();
    }

    onFilterChange(key, ev) {
        this.state.filters[key] = ev.target.value;
        if (key === "program_id") { this.state.filters.project_id = ""; this.state.filters.activity_id = ""; }
        if (key === "project_id") { this.state.filters.activity_id = ""; }
        if (key === "grant_id") { this.state.filters.budget_line_id = ""; }
        if (key === "date_from" || key === "date_to") { this.state.activePreset = ""; }
        // Auto-apply: no separate "Apply" click needed, feels immediate/dynamic.
        this.load();
    }

    applyPreset(preset) {
        const today = new Date();
        let from, to;
        if (preset === "month") {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
            to = today;
        } else if (preset === "quarter") {
            const q = Math.floor(today.getMonth() / 3);
            from = new Date(today.getFullYear(), q * 3, 1);
            to = today;
        } else if (preset === "year") {
            from = new Date(today.getFullYear(), 0, 1);
            to = today;
        } else {
            from = null; to = null;
        }
        this.state.filters.date_from = from ? fmtDate(from) : "";
        this.state.filters.date_to = to ? fmtDate(to) : "";
        this.state.activePreset = preset;
        this.load();
    }

    reset() {
        for (const k in this.state.filters) { this.state.filters[k] = ""; }
        this.state.activePreset = "";
        this.load();
    }

    refresh() { this.load(); }

    // ---- cascading option lists ----
    get projects() {
        const p = this.state.filters.program_id;
        return p ? this.state.options.projects.filter((x) => String(x.program_id) === String(p)) : this.state.options.projects;
    }
    get activities() {
        const p = this.state.filters.project_id;
        return p ? this.state.options.activities.filter((x) => String(x.project_id) === String(p)) : this.state.options.activities;
    }
    get lines() {
        const g = this.state.filters.grant_id;
        return g ? this.state.options.lines.filter((x) => String(x.grant_id) === String(g)) : this.state.options.lines;
    }
    sel(key, id) { return String(this.state.filters[key]) === String(id); }

    get activeFilterCount() {
        return Object.values(this.state.filters).filter((v) => v).length;
    }

    // ---- KPI cards (each carries a drill-down action) ----
    get cards() {
        const t = this.state.data.totals || {};
        const n = (v) => Math.round(v || 0).toLocaleString();
        const plural = (v, w) => `${n(v)} ${w}${(v || 0) === 1 ? "" : "s"}`;
        return [
            { key: "approved", label: "Approved budget", icon: "fa-bullseye", accent: "#1F3A5F", val: this.fmt(t.approved), sub: plural(t.grants, "grant"), onClick: () => this.openGrants() },
            { key: "committed", label: "Committed", icon: "fa-lock", accent: "#C9A24B", val: this.fmt(t.committed), sub: plural(t.pending_requests, "pending request"), onClick: () => this.openCommitments() },
            { key: "actual", label: "Actual spent", icon: "fa-file-text-o", accent: "#1D9E75", val: this.fmt(t.actual), sub: plural(t.expenses, "posted expense"), onClick: () => this.openExpenses() },
            { key: "available", label: "Available", icon: "fa-credit-card", accent: "#378ADD", val: this.fmt(t.available), sub: "remaining balance" },
            { key: "received", label: "Funds received", icon: "fa-download", accent: "#1D9E75", val: this.fmt(t.received), sub: "from donors", onClick: () => this.openFundReceipts() },
            { key: "advances", label: "Outstanding advances", icon: "fa-exchange", accent: "#C9A24B", val: this.fmt(t.outstanding_advances), sub: "awaiting liquidation", onClick: () => this.openAdvances() },
            { key: "utilization", label: "Utilization", icon: "fa-tachometer", accent: this.toneColor(t.utilization), val: this.pct(t.utilization), sub: (t.utilization || 0) >= 90 ? "High \u2014 review" : (t.utilization || 0) >= 80 ? "Watch closely" : "On track" },
            { key: "overdue", label: "Overdue reports", icon: "fa-bell", accent: "#D85A30", val: String(t.overdue || 0), sub: t.overdue ? "need submission" : "all clear", onClick: t.overdue ? () => this.openOverdueReports() : null },
        ];
    }

    // ---- formatting / helpers ----
    fmt(n) { return (this.state.data.currency || "") + Math.round(n || 0).toLocaleString(); }
    pct(n) { return (Math.round((n || 0) * 10) / 10) + "%"; }
    toneClass(u) { return u >= 90 ? "o_util_bad" : (u >= 80 ? "o_util_warn" : "o_util_ok"); }
    toneColor(u) { return u >= 90 ? "#D85A30" : (u >= 80 ? "#C9A24B" : "#1D9E75"); }
    color(i) { return COLORS[i % COLORS.length]; }

    get lastUpdatedLabel() {
        if (!this.state.lastUpdated) { return ""; }
        return this.state.lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    get tsMax() { return Math.max(1, ...this.state.data.time_series.map((p) => p.value || 0)); }
    _niceMax(max) {
        if (max <= 0) { return 1; }
        const exp = Math.floor(Math.log10(max));
        const base = Math.pow(10, exp);
        const f = max / base;
        const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
        return nice * base;
    }
    get tsNiceMax() { return this._niceMax(this.tsMax); }
    get tsTicks() {
        const max = this.tsNiceMax, steps = 4, out = [];
        for (let i = steps; i >= 0; i--) { out.push(Math.round((max * i) / steps)); }
        return out;
    }
    tsHeight(v) { return Math.max(1, Math.round((100 * (v || 0)) / this.tsNiceMax)); }

    // ---- donut chart builder (CSS conic-gradient, no external chart lib) ----
    _buildDonut(items) {
        const rows = (items || []).filter((r) => r.value);
        const total = rows.reduce((a, r) => a + (r.value || 0), 0) || 1;
        let acc = 0;
        const stops = [];
        const withPct = rows.map((r, i) => {
            const color = r.color || this.color(i);
            const pct = (100 * r.value) / total;
            const start = acc;
            acc += pct;
            stops.push(`${color} ${start.toFixed(2)}% ${acc.toFixed(2)}%`);
            return { label: r.label, value: r.value, isCount: r.isCount, color, pct: Math.round(pct) };
        });
        return {
            rows: withPct,
            total,
            gradient: stops.length ? `conic-gradient(${stops.join(", ")})` : "conic-gradient(#E9ECF2 0% 100%)",
        };
    }
    get categoryDonut() { return this._buildDonut(this.state.data.categories || []); }
    get statusDonut() {
        const counts = {};
        for (const g of this.state.data.grants || []) {
            const k = g.status || "Unspecified";
            counts[k] = (counts[k] || 0) + 1;
        }
        const rows = Object.keys(counts)
            .map((k, i) => ({ label: k, value: counts[k], isCount: true, color: this.color(i) }))
            .sort((a, b) => b.value - a.value);
        return this._buildDonut(rows);
    }

    // ---- top grants by value (horizontal bar list) ----
    get topGrantsByValue() {
        const rows = [...(this.state.data.grants || [])]
            .sort((a, b) => (b.approved || 0) - (a.approved || 0))
            .slice(0, 5);
        const max = Math.max(1, ...rows.map((g) => g.approved || 0));
        return rows.map((g) => ({ ...g, barPct: Math.max(2, Math.round((100 * (g.approved || 0)) / max)) }));
    }

    // ---- recent grants (quick list, mirrors the full table order) ----
    get recentGrants() { return (this.state.data.grants || []).slice(0, 6); }

    statusBadgeClass(status) {
        const s = (status || "").toLowerCase();
        if (s.includes("draft")) { return "o_pill_grey"; }
        if (s.includes("clos") || s.includes("cancel") || s.includes("reject")) { return "o_pill_grey"; }
        if (s.includes("pend") || s.includes("review") || s.includes("submit")) { return "o_pill_amber"; }
        return "o_pill_teal";
    }

    // ---- grant deep-dive (client-side detail, no extra round-trip) ----
    onSelectGrant(ev) {
        const v = ev.target.value;
        this.state.selectedGrantId = v ? parseInt(v, 10) : null;
    }
    get selectedGrant() {
        if (!this.state.selectedGrantId) { return null; }
        return (this.state.data.grants || []).find((g) => g.id === this.state.selectedGrantId) || null;
    }

    get progMax() {
        let m = 1;
        for (const p of this.state.data.programs) { m = Math.max(m, p.planned || 0, p.committed || 0, p.actual || 0); }
        return m;
    }
    progPct(v) { return Math.round((100 * (v || 0)) / this.progMax); }

    get zoneMax() { return Math.max(1, ...this.state.data.zones.map((z) => z.value || 0)); }
    zonePct(v) { return Math.round((100 * (v || 0)) / this.zoneMax); }

    get categoryRows() {
        const cats = this.state.data.categories || [];
        const total = cats.reduce((a, c) => a + c.value, 0) || 1;
        const max = Math.max(1, ...cats.map((c) => c.value || 0));
        return [...cats]
            .sort((a, b) => (b.value || 0) - (a.value || 0))
            .map((c, i) => ({
                color: this.color(i), label: c.label, value: c.value,
                pct: Math.round((100 * c.value) / total),
                barPct: Math.round((100 * c.value) / max),
            }));
    }

    // ---- sortable tables ----
    sortBy(table, key) {
        const s = this.state.sort[table];
        if (s.key === key) { s.dir = s.dir === "asc" ? "desc" : "asc"; } else { s.key = key; s.dir = "desc"; }
    }
    sortIcon(table, key) {
        const s = this.state.sort[table];
        if (s.key !== key) { return "fa-sort text-muted"; }
        return s.dir === "asc" ? "fa-sort-asc" : "fa-sort-desc";
    }
    get sortedGrants() {
        const { key, dir } = this.state.sort.grants;
        const rows = [...(this.state.data.grants || [])];
        rows.sort((a, b) => {
            const av = a[key], bv = b[key];
            const cmp = typeof av === "string" ? String(av).localeCompare(String(bv)) : (av || 0) - (bv || 0);
            return dir === "asc" ? cmp : -cmp;
        });
        return rows;
    }
    get sortedTopLines() {
        const { key, dir } = this.state.sort.top_lines;
        const rows = [...(this.state.data.top_lines || [])];
        rows.sort((a, b) => {
            const av = a[key], bv = b[key];
            const cmp = typeof av === "string" ? String(av).localeCompare(String(bv)) : (av || 0) - (bv || 0);
            return dir === "asc" ? cmp : -cmp;
        });
        return rows;
    }

    // ---- CSV export (client-side, no server round-trip) ----
    exportGrantsCsv() {
        const rows = [["Grant", "Donor", "Approved", "Committed", "Actual", "Available", "Utilization %", "Status"]];
        for (const g of this.sortedGrants) {
            rows.push([g.code, g.donor, g.approved, g.committed, g.actual, g.available,
                       Math.round(g.utilization || 0), g.status]);
        }
        const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "grants_in_scope.csv";
        a.click();
        URL.revokeObjectURL(url);
    }

    // ---- drill-down domain builder, mirrors the backend's own filter logic ----
    _baseDomain(extra) {
        const f = this.state.filters;
        const d = [...(extra || [])];
        if (f.grant_id) d.push(["grant_id", "=", parseInt(f.grant_id, 10)]);
        if (f.donor_id) d.push(["grant_id.donor_id", "=", parseInt(f.donor_id, 10)]);
        if (f.program_id) d.push(["project_id.program_id", "=", parseInt(f.program_id, 10)]);
        if (f.project_id) d.push(["project_id", "=", parseInt(f.project_id, 10)]);
        if (f.activity_id) d.push(["activity_id", "=", parseInt(f.activity_id, 10)]);
        if (f.budget_line_id) d.push(["budget_line_id", "=", parseInt(f.budget_line_id, 10)]);
        if (f.zone_id) d.push(["zone_id", "=", parseInt(f.zone_id, 10)]);
        return d;
    }

    _openList(name, resModel, domain, extraContext) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            views: [[false, "list"], [false, "form"]],
            view_mode: "list,form",
            domain,
            context: extraContext || {},
            target: "current",
        });
    }

    openExpenses() {
        const f = this.state.filters;
        const d = this._baseDomain([["state", "=", "posted"]]);
        if (f.date_from) { d.push(["date", ">=", f.date_from]); }
        if (f.date_to) { d.push(["date", "<=", f.date_to]); }
        this._openList("Expenses", "mcit.expense", d);
    }
    openCommitments() {
        const f = this.state.filters;
        const d = [["state", "=", "confirmed"]];
        if (f.grant_id) { d.push(["grant_id", "=", parseInt(f.grant_id, 10)]); }
        this._openList("Commitments", "mcit.commitment", d);
    }
    openFundReceipts() {
        const f = this.state.filters;
        const d = [["state", "=", "posted"]];
        if (f.grant_id) { d.push(["grant_id", "=", parseInt(f.grant_id, 10)]); }
        if (f.donor_id) { d.push(["grant_id.donor_id", "=", parseInt(f.donor_id, 10)]); }
        this._openList("Fund Receipts", "mcit.fund.receipt", d);
    }
    openAdvances() {
        const f = this.state.filters;
        const d = [["state", "=", "issued"]];
        if (f.zone_id) { d.push(["zone_id", "=", parseInt(f.zone_id, 10)]); }
        if (f.grant_id) { d.push(["grant_id", "=", parseInt(f.grant_id, 10)]); }
        this._openList("Advances", "mcit.advance", d);
    }
    openOverdueReports() {
        this._openList("Overdue Donor Reports", "mcit.donor.report", [["is_overdue", "=", true]]);
    }
    openPendingRequests() {
        const f = this.state.filters;
        const d = [["state", "in", ["submitted", "committed"]]];
        if (f.grant_id) { d.push(["grant_id", "=", parseInt(f.grant_id, 10)]); }
        if (f.zone_id) { d.push(["zone_id", "=", parseInt(f.zone_id, 10)]); }
        this._openList("Pending Acquisitions", "mcit.spend.request", d);
    }
    openGrants() {
        const f = this.state.filters;
        const d = [];
        if (f.grant_id) { d.push(["id", "=", parseInt(f.grant_id, 10)]); }
        if (f.donor_id) { d.push(["donor_id", "=", parseInt(f.donor_id, 10)]); }
        this._openList("Grants", "mcit.grant", d);
    }
    openGrant(id) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "mcit.grant", res_id: id,
            views: [[false, "form"]], target: "current",
        });
    }
}
McitDashboard.template = "mcit_dashboard.Dashboard";

registry.category("actions").add("mcit_dashboard.main", McitDashboard);
