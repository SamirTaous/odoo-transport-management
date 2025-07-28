/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

// Helper function to decode OSRM polyline
function decodePolyline(encoded) {
    let index = 0, len = encoded.length;
    let lat = 0, lng = 0;
    let array = [];
    while (index < len) {
        let b, shift = 0, result = 0;
        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);
        let dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lat += dlat;
        shift = 0;
        result = 0;
        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);
        let dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lng += dlng;
        array.push([lat * 1e-5, lng * 1e-5]);
    }
    return array;
}

export class MissionOverviewMap extends Component {
    static props = {
        action: { type: Object, optional: true },
        "*": true,
    };

    setup() {
        console.log("MissionOverviewMap setup called", this.props);
        
        this.mapContainer = useRef("mapContainer");
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.map = null;
        this.missionLayers = {};
        this.refreshInterval = null;
        
        this.state = useState({
            missions: [],
            loading: true,
            lastUpdate: null
        });

        onMounted(() => {
            console.log("MissionOverviewMap mounted");
            this.initializeMap();
            this.loadMissions();
            // Auto-refresh every 30 seconds
            this.refreshInterval = setInterval(() => {
                this.loadMissions();
            }, 30000);
        });

        onWillUnmount(() => {
            console.log("MissionOverviewMap unmounting");
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
            if (this.map) {
                this.map.remove();
            }
        });
    }

    async initializeMap() {
        console.log("initializeMap called");
        console.log("mapContainer.el:", this.mapContainer.el);
        console.log("Leaflet available:", typeof L !== "undefined");
        
        if (this.map) {
            console.log("Map already exists, skipping");
            return;
        }
        
        if (!this.mapContainer.el) {
            console.error("Map container element not found!");
            return;
        }

        if (typeof L === "undefined") {
            console.error("Leaflet library not found!");
            this.notification.add("Leaflet library not found. Please ensure Leaflet is loaded.", { type: "danger" });
            return;
        }

        try {
            console.log("Creating Leaflet map...");
            this.map = L.map(this.mapContainer.el).setView([46.603354, 1.888334], 6);
            console.log("Map created:", this.map);

            console.log("Adding tile layer...");
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(this.map);

            console.log("Overview map initialized successfully");
            
            // Force map to resize after a short delay
            setTimeout(() => {
                if (this.map) {
                    this.map.invalidateSize();
                    console.log("Map size invalidated");
                }
            }, 100);
            
        } catch (error) {
            console.error("Error initializing overview map:", error);
            this.notification.add("Failed to initialize map. Please refresh the page.", { type: "danger" });
        }
    }

    async loadMissions() {
        if (!this.map) return;

        try {
            this.state.loading = true;
            
            // Fetch missions with confirmed and in_progress states
            const missions = await this.orm.searchRead(
                "transport.mission",
                [["state", "in", ["confirmed", "in_progress"]]],
                [
                    "name", "state", "mission_type", "priority", "mission_date",
                    "source_location", "source_latitude", "source_longitude",
                    "driver_id", "vehicle_id", "total_distance_km", "destination_progress"
                ]
            );

            // Fetch destinations for each mission
            for (const mission of missions) {
                const destinations = await this.orm.searchRead(
                    "transport.destination",
                    [["mission_id", "=", mission.id]],
                    ["location", "latitude", "longitude", "sequence", "is_completed"],
                    { order: "sequence asc" }
                );
                mission.destinations = destinations;
            }

            this.state.missions = missions;
            this.state.lastUpdate = new Date();
            
            await this.updateMapDisplay();
            
        } catch (error) {
            console.error("Error loading missions:", error);
            this.notification.add("Failed to load missions", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async updateMapDisplay() {
        if (!this.map) return;

        // Clear existing layers
        Object.values(this.missionLayers).forEach(layer => {
            this.map.removeLayer(layer);
        });
        this.missionLayers = {};

        // Add missions to map
        for (const mission of this.state.missions) {
            await this.addMissionToMap(mission);
        }

        // Fit map to show all missions
        this.fitMapToMissions();
    }

    async addMissionToMap(mission) {
        if (!mission.source_latitude || !mission.source_longitude || !mission.destinations.length) {
            return;
        }

        const missionGroup = L.layerGroup();
        
        // Color scheme based on mission type and state
        const colors = this.getMissionColors(mission);
        
        // Add source marker
        const sourceIcon = this.createMissionIcon(mission, true);
        const sourceMarker = L.marker(
            [mission.source_latitude, mission.source_longitude],
            { icon: sourceIcon }
        );
        
        const sourcePopup = this.createMissionPopup(mission);
        sourceMarker.bindPopup(sourcePopup);
        missionGroup.addLayer(sourceMarker);

        // Add destination markers
        mission.destinations.forEach((dest, index) => {
            if (dest.latitude && dest.longitude) {
                const destIcon = this.createDestinationIcon(mission, dest, index + 1);
                const destMarker = L.marker([dest.latitude, dest.longitude], { icon: destIcon });
                
                const destPopup = `
                    <div class="tm-overview-popup">
                        <h6>${mission.name} - Stop ${dest.sequence}</h6>
                        <p><strong>Location:</strong> ${dest.location}</p>
                        <p><strong>Status:</strong> ${dest.is_completed ? '✅ Completed' : '⏳ Pending'}</p>
                    </div>
                `;
                destMarker.bindPopup(destPopup);
                missionGroup.addLayer(destMarker);
            }
        });

        // Draw route
        await this.drawMissionRoute(mission, missionGroup, colors);
        
        // Add to map
        missionGroup.addTo(this.map);
        this.missionLayers[mission.id] = missionGroup;
    }

    getMissionColors(mission) {
        const baseColors = {
            pickup: { primary: '#17a2b8', secondary: '#138496' },
            delivery: { primary: '#28a745', secondary: '#1e7e34' }
        };
        
        const typeColors = baseColors[mission.mission_type] || baseColors.delivery;
        
        // Adjust opacity based on state
        const opacity = mission.state === 'in_progress' ? 1.0 : 0.7;
        
        return {
            route: typeColors.primary,
            marker: typeColors.secondary,
            opacity: opacity
        };
    }

    createMissionIcon(mission, isSource = false) {
        const colors = this.getMissionColors(mission);
        const stateClass = mission.state === 'in_progress' ? 'tm-active' : 'tm-confirmed';
        const typeIcon = mission.mission_type === 'pickup' ? '🏭' : '📦';
        
        const html = `
            <div class="tm-overview-marker tm-source-marker ${stateClass}">
                <div class="tm-marker-content" style="background-color: ${colors.marker};">
                    <span class="tm-marker-icon">${typeIcon}</span>
                </div>
                <div class="tm-marker-label">${mission.name}</div>
            </div>
        `;

        return L.divIcon({
            className: 'tm-overview-icon',
            html: html,
            iconSize: [50, 60],
            iconAnchor: [25, 55]
        });
    }

    createDestinationIcon(mission, destination, sequence) {
        const colors = this.getMissionColors(mission);
        const completedClass = destination.is_completed ? 'tm-completed' : 'tm-pending';
        const typeIcon = mission.mission_type === 'pickup' ? '📤' : '📥';
        
        const html = `
            <div class="tm-overview-marker tm-dest-marker ${completedClass}">
                <div class="tm-marker-content" style="background-color: ${colors.marker};">
                    <span class="tm-marker-number">${sequence}</span>
                    <span class="tm-marker-icon">${typeIcon}</span>
                </div>
            </div>
        `;

        return L.divIcon({
            className: 'tm-overview-icon',
            html: html,
            iconSize: [35, 45],
            iconAnchor: [17.5, 40]
        });
    }

    createMissionPopup(mission) {
        const progressBar = mission.destination_progress || 0;
        const stateLabel = {
            'confirmed': '✅ Confirmed',
            'in_progress': '🚛 In Progress'
        }[mission.state] || mission.state;

        return `
            <div class="tm-overview-popup">
                <h5>${mission.name}</h5>
                <div class="tm-popup-info">
                    <p><strong>Type:</strong> ${mission.mission_type === 'pickup' ? '📤 Pickup' : '📥 Delivery'}</p>
                    <p><strong>Status:</strong> ${stateLabel}</p>
                    <p><strong>Date:</strong> ${mission.mission_date}</p>
                    <p><strong>Driver:</strong> ${mission.driver_id ? mission.driver_id[1] : 'Not assigned'}</p>
                    <p><strong>Vehicle:</strong> ${mission.vehicle_id ? mission.vehicle_id[1] : 'Not assigned'}</p>
                    <p><strong>Distance:</strong> ${(mission.total_distance_km || 0).toFixed(1)} km</p>
                    <div class="tm-progress-container">
                        <label>Progress:</label>
                        <div class="progress" style="height: 20px; margin-top: 5px;">
                            <div class="progress-bar" style="width: ${progressBar}%;">${progressBar.toFixed(0)}%</div>
                        </div>
                    </div>
                    <p><strong>Destinations:</strong> ${mission.destinations.length}</p>
                </div>
            </div>
        `;
    }

    async drawMissionRoute(mission, layerGroup, colors) {
        if (!mission.destinations.length) return;

        // Prepare points for OSRM
        const points = [[mission.source_longitude, mission.source_latitude]];
        mission.destinations
            .filter(dest => dest.latitude && dest.longitude)
            .sort((a, b) => a.sequence - b.sequence)
            .forEach(dest => {
                points.push([dest.longitude, dest.latitude]);
            });

        if (points.length < 2) return;

        try {
            const coordinates = points.map(p => p.join(',')).join(';');
            const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${coordinates}?overview=full&geometries=polyline`;

            const response = await fetch(osrmUrl);
            if (!response.ok) throw new Error('OSRM request failed');
            
            const data = await response.json();
            if (data.code !== "Ok" || !data.routes || data.routes.length === 0) {
                throw new Error("No route found");
            }

            const route = data.routes[0];
            const routeGeometry = decodePolyline(route.geometry);

            // Create route polyline with mission-specific styling
            const routeLine = L.polyline(routeGeometry, {
                color: colors.route,
                weight: mission.state === 'in_progress' ? 5 : 3,
                opacity: colors.opacity,
                dashArray: mission.state === 'confirmed' ? '10, 5' : null,
                className: `tm-route-${mission.mission_type} tm-state-${mission.state}`
            });

            layerGroup.addLayer(routeLine);

        } catch (error) {
            console.warn(`Failed to draw route for mission ${mission.name}:`, error);
            
            // Fallback to straight lines
            const latLngPoints = points.map(p => [p[1], p[0]]);
            const fallbackRoute = L.polyline(latLngPoints, {
                color: colors.route,
                weight: 2,
                opacity: 0.5,
                dashArray: '5, 10',
                className: `tm-route-fallback tm-route-${mission.mission_type}`
            });

            layerGroup.addLayer(fallbackRoute);
        }
    }

    fitMapToMissions() {
        if (!this.map || !this.state.missions.length) return;

        const bounds = L.latLngBounds();
        let hasValidBounds = false;

        this.state.missions.forEach(mission => {
            if (mission.source_latitude && mission.source_longitude) {
                bounds.extend([mission.source_latitude, mission.source_longitude]);
                hasValidBounds = true;
            }
            
            mission.destinations.forEach(dest => {
                if (dest.latitude && dest.longitude) {
                    bounds.extend([dest.latitude, dest.longitude]);
                    hasValidBounds = true;
                }
            });
        });

        if (hasValidBounds) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    async refreshMissions() {
        await this.loadMissions();
        this.notification.add("Missions refreshed", { type: "success" });
    }

    getStatusSummary() {
        const confirmed = this.state.missions.filter(m => m.state === 'confirmed').length;
        const inProgress = this.state.missions.filter(m => m.state === 'in_progress').length;
        return { confirmed, inProgress, total: this.state.missions.length };
    }
}

MissionOverviewMap.template = "transport_management.MissionOverviewMap";

// Register as a client action - proper Odoo 16 way
registry.category("actions").add("transport_mission_overview_map", MissionOverviewMap);