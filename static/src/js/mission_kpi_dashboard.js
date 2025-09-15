/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

export class MissionKpiDashboard extends Component {
    static props = { action: { type: Object, optional: true }, "*": true };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.ui = useService("ui");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            kpi: null,
            series_missions: [],
            series_distance: [],
            series_cost: [],
            series_cost_per_km: [],
            series_on_time: [],
            date_from: null,
            date_to: null,
            group_by: "month",
        });

        this.missionsChart = useRef("missionsChart");
        this.distanceChart = useRef("distanceChart");
        this.costChart = useRef("costChart");
        this.onTimeChart = useRef("onTimeChart");
        this.costPerKmChart = useRef("costPerKmChart"); // Added this ref as it was used in renderCharts but not defined

        onMounted(async () => {
            await this.refreshData();
        });
    }

    get dateRangeArgs() {
        return [this.state.date_from, this.state.date_to, this.env.company && this.env.company.id];
    }

    async refreshData() {
        try {
            this.state.loading = true;
            const [summary, tsMissions, tsDistance, tsCost, tsOnTime, tsCostPerKm] = await Promise.all([
                this.orm.call("transport.mission", "get_kpi_summary", this.dateRangeArgs),
                this.orm.call("transport.mission", "get_kpi_timeseries", [], { group_by: this.state.group_by, metric: "missions", date_from: this.state.date_from, date_to: this.state.date_to }),
                this.orm.call("transport.mission", "get_kpi_timeseries", [], { group_by: this.state.group_by, metric: "distance", date_from: this.state.date_from, date_to: this.state.date_to }),
                this.orm.call("transport.mission", "get_kpi_timeseries", [], { group_by: this.state.group_by, metric: "cost", date_from: this.state.date_from, date_to: this.state.date_to }),
                this.orm.call("transport.mission", "get_kpi_timeseries", [], { group_by: this.state.group_by, metric: "on_time_rate", date_from: this.state.date_from, date_to: this.state.date_to }),
                this.orm.call("transport.mission", "get_kpi_timeseries", [], { group_by: this.state.group_by, metric: "cost_per_km", date_from: this.state.date_from, date_to: this.state.date_to }),
            ]);

            this.state.kpi = summary;
            this.state.series_missions = tsMissions;
            this.state.series_distance = tsDistance;
            this.state.series_cost = tsCost;
            this.state.series_on_time = tsOnTime;
            this.state.series_cost_per_km = tsCostPerKm;

            this.renderCharts();
        } catch (e) {
            console.error(e);
            this.notification.add("Failed to load KPI data", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    renderCharts() {
        const makeBar = (el, series, label) => {
            if (!el) return;
            // Simple rendering without external libs: create bars via CSS width
            el.innerHTML = "";
            const max = Math.max(1, ...series.map(s => s.value));
            series.forEach(s => {
                const row = document.createElement("div");
                row.className = "tm-chart-row";
                const name = document.createElement("div");
                name.className = "tm-chart-label";
                name.textContent = s.label;
                const barWrap = document.createElement("div");
                barWrap.className = "tm-chart-bar-wrap";
                const bar = document.createElement("div");
                bar.className = "tm-chart-bar";
                bar.style.width = `${(s.value / max) * 100}%`;
                bar.title = `${label}: ${s.value}`;
                barWrap.appendChild(bar);
                row.appendChild(name);
                row.appendChild(barWrap);
                el.appendChild(row);
            });
        };

        makeBar(this.missionsChart.el, this.state.series_missions, "Missions");
        makeBar(this.distanceChart.el, this.state.series_distance, "Km");
        makeBar(this.costChart.el, this.state.series_cost, "Cost");
        makeBar(this.onTimeChart.el, this.state.series_on_time, "% On-Time");
        if (this.costPerKmChart && this.costPerKmChart.el) {
            makeBar(this.costPerKmChart.el, this.state.series_cost_per_km, "Cost/Km");
        }
    }

    async openOverviewMap() {
        await this.action.doAction({ type: "ir.actions.client", tag: "transport_mission_mission_overview_simple", name: "Mission Overview Map" });
    }
}

MissionKpiDashboard.template = "transport_management.MissionKpiDashboard";
registry.category("actions").add("transport_mission_kpi_dashboard", MissionKpiDashboard);