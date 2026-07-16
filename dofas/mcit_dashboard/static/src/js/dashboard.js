/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

const COLORS = ["#1F3A5F", "#C9A24B", "#1D9E75", "#378ADD", "#D85A30", "#7F77DD", "#6B7280", "#B0843B"];

export class McitDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
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
    }

    onFilterChange(key, ev) {
        this.state.filters[key] = ev.target.value;
        if (key === "program_id") { this.state.filters.project_id = ""; this.state.filters.activity_id = ""; }
        if (key === "project_id") { this.state.filters.activity_id = ""; }
        if (key === "grant_id") { this.state.filters.budget_line_id = ""; }
    }
    apply() { this.load(); }
    reset() {
        for (const k in this.state.filters) { this.state.filters[k] = ""; }
        this.load();
    }

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

    // ---- KPI cards ----
    get cards() {
        const t = this.state.data.totals || {};
        return [
            { key: "approved", label: "Approved budget", icon: "fa-bullseye", accent: "#1F3A5F", val: this.fmt(t.approved) },
            { key: "committed", label: "Committed", icon: "fa-lock", accent: "#C9A24B", val: this.fmt(t.committed) },
            { key: "actual", label: "Actual spent", icon: "fa-file-text-o", accent: "#1D9E75", val: this.fmt(t.actual) },
            { key: "available", label: "Available", icon: "fa-credit-card", accent: "#378ADD", val: this.fmt(t.available) },
            { key: "received", label: "Funds received", icon: "fa-download", accent: "#1D9E75", val: this.fmt(t.received) },
            { key: "advances", label: "Outstanding advances", icon: "fa-exchange", accent: "#C9A24B", val: this.fmt(t.outstanding_advances) },
            { key: "utilization", label: "Utilization", icon: "fa-tachometer", accent: this.toneColor(t.utilization), val: this.pct(t.utilization) },
            { key: "overdue", label: "Overdue reports", icon: "fa-bell", accent: "#D85A30", val: String(t.overdue || 0) },
        ];
    }

    // ---- formatting / helpers ----
    fmt(n) { return (this.state.data.currency || "") + Math.round(n || 0).toLocaleString(); }
    pct(n) { return (Math.round((n || 0) * 10) / 10) + "%"; }
    toneClass(u) { return u >= 90 ? "o_util_bad" : (u >= 80 ? "o_util_warn" : "o_util_ok"); }
    toneColor(u) { return u >= 90 ? "#D85A30" : (u >= 80 ? "#C9A24B" : "#1D9E75"); }
    color(i) { return COLORS[i % COLORS.length]; }

    get tsMax() { return Math.max(1, ...this.state.data.time_series.map((p) => p.value || 0)); }
    tsHeight(v) { return Math.max(2, Math.round((100 * (v || 0)) / this.tsMax)); }

    get progMax() {
        let m = 1;
        for (const p of this.state.data.programs) { m = Math.max(m, p.planned || 0, p.committed || 0, p.actual || 0); }
        return m;
    }
    progPct(v) { return Math.round((100 * (v || 0)) / this.progMax); }

    get zoneMax() { return Math.max(1, ...this.state.data.zones.map((z) => z.value || 0)); }
    zonePct(v) { return Math.round((100 * (v || 0)) / this.zoneMax); }

    get donutSegments() {
        const C = 2 * Math.PI * 54;
        const cats = this.state.data.categories || [];
        const total = cats.reduce((a, c) => a + c.value, 0) || 1;
        let offset = 0;
        return cats.map((c, i) => {
            const len = (c.value / total) * C;
            const seg = { color: this.color(i), dash: `${len} ${C - len}`, offset: -offset,
                          label: c.label, value: c.value, pct: Math.round((100 * c.value) / total) };
            offset += len;
            return seg;
        });
    }
}
McitDashboard.template = "mcit_dashboard.Dashboard";

registry.category("actions").add("mcit_dashboard.main", McitDashboard);
