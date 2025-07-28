/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

// Helper function to decode OSRM polyline (reused from existing widget)
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

export class MissionOverviewSimple extends Component {
    static props = {
        action: { type: Object, optional: true },
        "*": true,
    };

    setup() {
        this.mapContainer = useRef("mapContainer");
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.map = null;
        this.missionLayers = [];
        this.refreshInterval = null;
        
        this.state = useState({
            missions: [],
            loading: true,
            lastUpdate: null,
            selectedMission: null,
            panelCollapsed: false
        });

        onMounted(() => {
            this.initializeMap();
            this.loadMissions();
            // Auto-refresh every 30 seconds
            this.refreshInterval = setInterval(() => {
                this.loadMissions();
            }, 30000);
        });

        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
            if (this.map) {
                this.map.remove();
            }
        });
    }

    initializeMap() {
        if (this.map || !this.mapContainer.el) return;

        if (typeof L === "undefined") {
            this.notification.add("Leaflet library not found", { type: "danger" });
            return;
        }

        try {
            this.map = L.map(this.mapContainer.el).setView([46.603354, 1.888334], 6);

            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(this.map);

            console.log("Overview map initialized");
        } catch (error) {
            console.error("Error initializing map:", error);
            this.notification.add("Failed to initialize map", { type: "danger" });
        }
    }

    async loadMissions() {
        if (!this.map) return;

        try {
            this.state.loading = true;
            
            // Fetch active missions
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
            
            this.updateMapDisplay();
            
        } catch (error) {
            console.error("Error loading missions:", error);
            this.notification.add("Failed to load missions", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    updateMapDisplay() {
        // Clear existing layers
        this.missionLayers.forEach(layer => {
            this.map.removeLayer(layer);
        });
        this.missionLayers = [];

        // Add each mission to the map
        this.state.missions.forEach(mission => {
            this.addMissionToMap(mission);
        });

        // Fit map to show all missions
        this.fitMapToMissions();
    }

    addMissionToMap(mission) {
        if (!mission.source_latitude || !mission.source_longitude || !mission.destinations.length) {
            return;
        }

        const missionGroup = L.layerGroup();
        
        // Colors based on mission type and state
        const colors = this.getMissionColors(mission);
        
        // Add source marker
        const sourceIcon = this.createSourceIcon(mission);
        const sourceMarker = L.marker(
            [mission.source_latitude, mission.source_longitude],
            { icon: sourceIcon }
        );
        
        sourceMarker.bindPopup(this.createMissionPopup(mission));
        missionGroup.addLayer(sourceMarker);

        // Add destination markers
        mission.destinations.forEach((dest, index) => {
            if (dest.latitude && dest.longitude) {
                const destIcon = this.createDestinationIcon(mission, dest, index + 1);
                const destMarker = L.marker([dest.latitude, dest.longitude], { icon: destIcon });
                
                const destPopup = `
                    <div style="min-width: 150px;">
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
        this.drawMissionRoute(mission, missionGroup, colors);
        
        // Add to map and track
        missionGroup.addTo(this.map);
        this.missionLayers.push(missionGroup);
    }

    getMissionColors(mission) {
        const baseColors = {
            pickup: { primary: '#17a2b8', secondary: '#138496' },
            delivery: { primary: '#28a745', secondary: '#1e7e34' }
        };
        
        const typeColors = baseColors[mission.mission_type] || baseColors.delivery;
        const opacity = mission.state === 'in_progress' ? 1.0 : 0.7;
        
        return {
            route: typeColors.primary,
            marker: typeColors.secondary,
            opacity: opacity
        };
    }

    createSourceIcon(mission) {
        const colors = this.getMissionColors(mission);
        const typeIcon = mission.mission_type === 'pickup' ? '🏭' : '📦';
        const stateClass = mission.state === 'in_progress' ? 'active' : 'confirmed';
        
        const html = `
            <div style="
                position: relative;
                width: 40px;
                height: 50px;
                display: flex;
                flex-direction: column;
                align-items: center;
                cursor: pointer;
            ">
                <div style="
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    background: ${colors.marker};
                    border: 3px solid white;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 1rem;
                ">
                    ${typeIcon}
                </div>
                <div style="
                    background: rgba(0, 0, 0, 0.8);
                    color: white;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 0.7rem;
                    font-weight: 500;
                    margin-top: 4px;
                    white-space: nowrap;
                ">
                    ${mission.name}
                </div>
            </div>
        `;

        return L.divIcon({
            className: 'custom-marker',
            html: html,
            iconSize: [40, 50],
            iconAnchor: [20, 45]
        });
    }

    createDestinationIcon(mission, destination, sequence) {
        const colors = this.getMissionColors(mission);
        const typeIcon = mission.mission_type === 'pickup' ? '📤' : '📥';
        const completedStyle = destination.is_completed ? 'opacity: 0.7;' : '';
        
        const html = `
            <div style="
                position: relative;
                width: 30px;
                height: 30px;
                ${completedStyle}
            ">
                <div style="
                    width: 30px;
                    height: 30px;
                    border-radius: 50%;
                    background: ${colors.marker};
                    border: 2px solid white;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 0.8rem;
                ">
                    ${typeIcon}
                </div>
                <div style="
                    position: absolute;
                    top: -8px;
                    right: -8px;
                    width: 16px;
                    height: 16px;
                    border-radius: 50%;
                    background: white;
                    color: #333;
                    font-weight: 800;
                    font-size: 0.6rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border: 1px solid #ccc;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
                ">
                    ${sequence}
                </div>
                ${destination.is_completed ? `
                <div style="
                    position: absolute;
                    bottom: -6px;
                    right: -6px;
                    width: 14px;
                    height: 14px;
                    border-radius: 50%;
                    background: #28a745;
                    color: white;
                    font-size: 0.6rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border: 2px solid white;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
                ">
                    ✓
                </div>
                ` : ''}
            </div>
        `;

        return L.divIcon({
            className: 'custom-marker',
            html: html,
            iconSize: [30, 30],
            iconAnchor: [15, 25]
        });
    }

    createMissionPopup(mission) {
        const progressBar = mission.destination_progress || 0;
        const stateLabel = {
            'confirmed': '✅ Confirmed',
            'in_progress': '🚛 In Progress'
        }[mission.state] || mission.state;

        return `
            <div style="min-width: 200px;">
                <h5>${mission.name}</h5>
                <p><strong>Type:</strong> ${mission.mission_type === 'pickup' ? '📤 Pickup' : '📥 Delivery'}</p>
                <p><strong>Status:</strong> ${stateLabel}</p>
                <p><strong>Date:</strong> ${mission.mission_date}</p>
                <p><strong>Driver:</strong> ${mission.driver_id ? mission.driver_id[1] : 'Not assigned'}</p>
                <p><strong>Vehicle:</strong> ${mission.vehicle_id ? mission.vehicle_id[1] : 'Not assigned'}</p>
                <p><strong>Distance:</strong> ${(mission.total_distance_km || 0).toFixed(1)} km</p>
                <div style="margin: 8px 0;">
                    <label style="font-size: 0.8rem; color: #666;">Progress:</label>
                    <div style="background: #f0f0f0; height: 20px; border-radius: 4px; margin-top: 5px; overflow: hidden;">
                        <div style="background: #007bff; height: 100%; width: ${progressBar}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 0.75rem; font-weight: 500;">
                            ${progressBar.toFixed(0)}%
                        </div>
                    </div>
                </div>
                <p><strong>Destinations:</strong> ${mission.destinations.length}</p>
            </div>
        `;
    }

    async drawMissionRoute(mission, layerGroup, colors) {
        if (!mission.destinations.length) return;

        try {
            // Get cached route data from backend
            const routeData = await this.orm.call(
                "transport.mission",
                "get_cached_route_data",
                [mission.id]
            );

            if (!routeData) {
                console.warn(`No route data available for mission ${mission.name}`);
                return;
            }

            let routeGeometry;
            
            if (routeData.is_fallback) {
                // Handle fallback route (stored as JSON points)
                try {
                    const points = JSON.parse(routeData.geometry);
                    routeGeometry = points;
                } catch (e) {
                    console.warn(`Failed to parse fallback route geometry for mission ${mission.name}`);
                    return;
                }
            } else {
                // Handle OSRM polyline geometry
                routeGeometry = decodePolyline(routeData.geometry);
            }

            // Create route polyline with appropriate styling
            const routeOptions = {
                color: colors.route,
                weight: mission.state === 'in_progress' ? 5 : 3,
                opacity: colors.opacity,
                dashArray: mission.state === 'confirmed' ? '10, 5' : null
            };

            // Add visual indicator for fallback routes
            if (routeData.is_fallback) {
                routeOptions.dashArray = '5, 10';
                routeOptions.opacity = 0.6;
                routeOptions.weight = 2;
            }

            const routeLine = L.polyline(routeGeometry, routeOptions);
            layerGroup.addLayer(routeLine);

            // Add cache indicator to popup if route was cached
            if (routeData.cached) {
                console.log(`Using cached route for mission ${mission.name} (${routeData.is_fallback ? 'fallback' : 'OSRM'})`);
            }

        } catch (error) {
            console.warn(`Failed to draw route for mission ${mission.name}:`, error);
            
            // Ultimate fallback - draw straight lines between points
            const points = [[mission.source_longitude, mission.source_latitude]];
            mission.destinations
                .filter(dest => dest.latitude && dest.longitude)
                .sort((a, b) => a.sequence - b.sequence)
                .forEach(dest => {
                    points.push([dest.longitude, dest.latitude]);
                });

            if (points.length >= 2) {
                const latLngPoints = points.map(p => [p[1], p[0]]);
                const fallbackRoute = L.polyline(latLngPoints, {
                    color: colors.route,
                    weight: 2,
                    opacity: 0.4,
                    dashArray: '2, 8'
                });

                layerGroup.addLayer(fallbackRoute);
            }
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

    selectMission(mission) {
        this.state.selectedMission = mission;
        
        // Fit map to selected mission
        if (this.map && mission) {
            const bounds = L.latLngBounds();
            
            // Add source to bounds
            if (mission.source_latitude && mission.source_longitude) {
                bounds.extend([mission.source_latitude, mission.source_longitude]);
            }
            
            // Add destinations to bounds
            mission.destinations.forEach(dest => {
                if (dest.latitude && dest.longitude) {
                    bounds.extend([dest.latitude, dest.longitude]);
                }
            });
            
            if (bounds.isValid()) {
                this.map.fitBounds(bounds, { padding: [50, 50] });
            }
        }
    }

    deselectMission() {
        this.state.selectedMission = null;
        // Fit map to show all missions
        this.fitMapToMissions();
    }

    togglePanel() {
        this.state.panelCollapsed = !this.state.panelCollapsed;
    }
}

MissionOverviewSimple.template = "transport_management.MissionOverviewSimple";

registry.category("actions").add("transport_mission_overview_simple", MissionOverviewSimple);