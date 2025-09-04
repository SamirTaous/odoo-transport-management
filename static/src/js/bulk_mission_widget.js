/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { Component, onMounted, onWillUnmount, useRef, useState } = owl;

// Decode polyline function (same as in mission_map_planner_widget.js)
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

export class BulkMissionWidget extends Component {
    static template = "transport_management.BulkMissionWidget";

    setup() {
        this.mapContainer = useRef("mapContainer");
        this.notification = useService("notification");
        this.orm = useService("orm");

        this.map = null;
        this.missionLayers = {};
        this.currentMissionIndex = 0;

        this.state = useState({
            missions: [],
            currentMission: null,
            drivers: [],
            vehicles: [],
            showDriverDropdown: false,
            showVehicleDropdown: false,
            driverSearch: '',
            vehicleSearch: '',
            filteredDrivers: [],
            filteredVehicles: [],
        });

        onMounted(() => {
            window.bulkMissionWidget = this;
            this.initializeMap();
            this.loadDriversAndVehicles();
            this.syncStateFromRecord();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    async initializeMap() {
        if (this.map || !this.mapContainer.el) return;

        if (typeof L === "undefined") {
            this.notification.add("Leaflet library not found. Please ensure Leaflet is loaded.", { type: "danger" });
            return;
        }

        try {
            this.map = L.map(this.mapContainer.el).setView([31.7917, -7.0926], 6); // Morocco center

            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(this.map);

            // Add click handlers for creating new missions
            this.map.on("click", (e) => this.handleMapClick(e));
            this.map.on("contextmenu", (e) => {
                e.originalEvent.preventDefault();
                this.addDestinationToCurrentMission(e.latlng.lat, e.latlng.lng);
            });

            console.log("Bulk mission map initialized successfully");
        } catch (error) {
            console.error("Error initializing map:", error);
            this.notification.add("Failed to initialize map. Please refresh the page.", { type: "danger" });
        }
    }

    syncStateFromRecord() {
        const templates = this.getMissionTemplates();
        this.state.missions = templates;
        if (templates.length > 0 && !this.state.currentMission) {
            this.selectMission(0);
        }
        this.updateMapDisplay();
    }

    getMissionTemplates() {
        try {
            return JSON.parse(this.props.record.data.mission_templates || '[]');
        } catch {
            return [];
        }
    }

    async saveMissionTemplates() {
        const templates = JSON.stringify(this.state.missions);
        await this.props.record.update({ mission_templates: templates });
    }

    async loadDriversAndVehicles() {
        try {
            const [drivers, vehicles] = await Promise.all([
                this.orm.searchRead("res.partner", [["is_company", "=", false]], ["id", "name"]),
                this.orm.searchRead("truck.vehicle", [], ["id", "name"])
            ]);

            this.state.drivers = drivers;
            this.state.vehicles = vehicles;
            this.state.filteredDrivers = drivers;
            this.state.filteredVehicles = vehicles;
        } catch (error) {
            console.error("Error loading drivers and vehicles:", error);
        }
    }

    // Mission Management
    addNewMission() {
        const newMission = {
            id: Date.now(), // Temporary ID
            name: `Mission ${this.state.missions.length + 1}`,
            source_location: null,
            source_latitude: null,
            source_longitude: null,
            destinations: [],
            driver_id: null,
            driver_name: null,
            vehicle_id: null,
            vehicle_name: null,
            priority: '1',
            notes: '',
        };

        this.state.missions.push(newMission);
        this.selectMission(this.state.missions.length - 1);
        this.saveMissionTemplates();
        this.notification.add("New mission template added", { type: "success" });
    }

    selectMission(index) {
        this.currentMissionIndex = index;
        this.state.currentMission = this.state.missions[index];
        this.updateMapDisplay();
    }

    async removeMission(index) {
        if (confirm('Are you sure you want to remove this mission template?')) {
            this.state.missions.splice(index, 1);

            if (this.currentMissionIndex >= this.state.missions.length) {
                this.currentMissionIndex = Math.max(0, this.state.missions.length - 1);
            }

            this.state.currentMission = this.state.missions[this.currentMissionIndex] || null;
            this.updateMapDisplay();
            await this.saveMissionTemplates();
            this.notification.add("Mission template removed", { type: "success" });
        }
    }

    async duplicateMission(index) {
        const original = this.state.missions[index];
        const duplicate = {
            ...JSON.parse(JSON.stringify(original)),
            id: Date.now(),
            name: `${original.name} (Copy)`,
        };

        this.state.missions.splice(index + 1, 0, duplicate);
        this.selectMission(index + 1);
        await this.saveMissionTemplates();
        this.notification.add("Mission template duplicated", { type: "success" });
    }

    // Map Interaction
    async handleMapClick(e) {
        if (!this.state.currentMission) {
            this.addNewMission();
        }

        await this.setSourceLocation(e.latlng.lat, e.latlng.lng);
    }

    async setSourceLocation(lat, lng) {
        if (!this.state.currentMission) return;

        try {
            const address = await this.reverseGeocode(lat, lng);

            this.state.currentMission.source_location = address;
            this.state.currentMission.source_latitude = lat;
            this.state.currentMission.source_longitude = lng;

            await this.saveMissionTemplates();
            this.updateMapDisplay();
            this.notification.add("Source location updated", { type: "success" });
        } catch (error) {
            console.error('Error setting source location:', error);
            this.notification.add("Failed to set source location", { type: "danger" });
        }
    }

    async addDestinationToCurrentMission(lat, lng) {
        if (!this.state.currentMission) {
            this.addNewMission();
        }

        try {
            const address = await this.reverseGeocode(lat, lng);
            const newSequence = this.state.currentMission.destinations.length + 1;

            const newDestination = {
                id: Date.now(),
                location: address,
                latitude: lat,
                longitude: lng,
                sequence: newSequence,
                mission_type: 'delivery',
                expected_arrival_time: null,
                service_duration: 0,
                package_type: 'individual',
                total_weight: 0,
                total_volume: 0,
                requires_signature: false,
            };

            this.state.currentMission.destinations.push(newDestination);
            await this.saveMissionTemplates();
            this.updateMapDisplay();
            this.notification.add(`Destination ${newSequence} added`, { type: "success" });
        } catch (error) {
            console.error('Error adding destination:', error);
            this.notification.add("Failed to add destination", { type: "danger" });
        }
    }

    async removeDestination(missionIndex, destIndex) {
        const mission = this.state.missions[missionIndex];
        mission.destinations.splice(destIndex, 1);

        // Resequence remaining destinations
        mission.destinations.forEach((dest, index) => {
            dest.sequence = index + 1;
        });

        await this.saveMissionTemplates();
        this.updateMapDisplay();
        this.notification.add("Destination removed", { type: "success" });
    }

    // Map Display
    updateMapDisplay() {
        if (!this.map) return;

        // Clear existing layers
        Object.values(this.missionLayers).forEach(layer => {
            this.map.removeLayer(layer);
        });
        this.missionLayers = {};

        // Display all missions
        this.state.missions.forEach((mission, index) => {
            this.displayMissionOnMap(mission, index);
        });

        this.fitMapToAllMissions();
    }

    displayMissionOnMap(mission, index) {
        const isCurrentMission = index === this.currentMissionIndex;
        const missionColor = isCurrentMission ? '#007bff' : '#6c757d';
        const opacity = isCurrentMission ? 1.0 : 0.6;

        // Create layer group for this mission
        const missionGroup = L.layerGroup().addTo(this.map);
        this.missionLayers[index] = missionGroup;

        // Add source marker
        if (mission.source_latitude && mission.source_longitude) {
            const sourceMarker = L.marker([mission.source_latitude, mission.source_longitude], {
                icon: this.createMissionMarkerIcon('source', missionColor, index + 1)
            });

            sourceMarker.bindPopup(`
                <div>
                    <strong>Mission ${index + 1} - Source</strong><br>
                    ${mission.source_location}<br>
                    <small>Lat: ${mission.source_latitude.toFixed(4)}, Lng: ${mission.source_longitude.toFixed(4)}</small>
                </div>
            `);

            missionGroup.addLayer(sourceMarker);
        }

        // Add destination markers
        mission.destinations.forEach((dest, destIndex) => {
            if (dest.latitude && dest.longitude) {
                const destMarker = L.marker([dest.latitude, dest.longitude], {
                    icon: this.createMissionMarkerIcon('destination', missionColor, dest.sequence)
                });

                destMarker.bindPopup(`
                    <div>
                        <strong>Mission ${index + 1} - Destination ${dest.sequence}</strong><br>
                        ${dest.location}<br>
                        <small>Type: ${dest.mission_type}</small><br>
                        <small>Weight: ${dest.total_weight} kg</small><br>
                        <button onclick="window.bulkMissionWidget.removeDestination(${index}, ${destIndex})" 
                                style="background: #dc3545; color: white; border: none; padding: 5px 10px; margin-top: 5px; border-radius: 3px; cursor: pointer;">
                            🗑️ Remove
                        </button>
                    </div>
                `);

                missionGroup.addLayer(destMarker);
            }
        });

        // Draw route if possible
        this.drawMissionRoute(mission, missionGroup, missionColor, opacity);
    }

    createMissionMarkerIcon(type, color, number) {
        const isSource = type === 'source';

        let html;
        if (isSource) {
            html = `
                <div class="bulk-mission-marker source-marker" style="background-color: ${color};">
                    <div class="marker-number">${number}</div>
                    <div class="marker-icon"><i class="fa fa-truck"></i></div>
                </div>
            `;
        } else {
            html = `
                <div class="bulk-mission-marker dest-marker" style="background-color: ${color};">
                    <div class="marker-number">${number}</div>
                    <div class="marker-icon"><i class="fa fa-map-marker"></i></div>
                </div>
            `;
        }

        return L.divIcon({
            className: 'bulk-mission-custom-marker',
            html: html,
            iconSize: [30, 30],
            iconAnchor: [15, 15]
        });
    }

    async drawMissionRoute(mission, layerGroup, color, opacity) {
        if (!mission.source_latitude || !mission.source_longitude || mission.destinations.length === 0) {
            return;
        }

        const waypoints = [[mission.source_longitude, mission.source_latitude]];
        mission.destinations.forEach(dest => {
            if (dest.latitude && dest.longitude) {
                waypoints.push([dest.longitude, dest.latitude]);
            }
        });

        if (waypoints.length < 2) return;

        try {
            const coordinates = waypoints.map(wp => `${wp[0]},${wp[1]}`).join(';');
            const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${coordinates}?overview=full&geometries=polyline`;

            const response = await fetch(osrmUrl);
            if (response.ok) {
                const data = await response.json();
                if (data.code === 'Ok' && data.routes && data.routes.length > 0) {
                    const geometry = decodePolyline(data.routes[0].geometry);
                    const routeLine = L.polyline(geometry, {
                        color: color,
                        weight: 4,
                        opacity: opacity
                    });
                    layerGroup.addLayer(routeLine);
                }
            }
        } catch (error) {
            console.warn('Failed to draw route:', error);
        }
    }

    fitMapToAllMissions() {
        if (!this.map) return;

        const allPoints = [];

        this.state.missions.forEach(mission => {
            if (mission.source_latitude && mission.source_longitude) {
                allPoints.push([mission.source_latitude, mission.source_longitude]);
            }
            mission.destinations.forEach(dest => {
                if (dest.latitude && dest.longitude) {
                    allPoints.push([dest.latitude, dest.longitude]);
                }
            });
        });

        if (allPoints.length > 0) {
            const bounds = L.latLngBounds(allPoints);
            this.map.fitBounds(bounds, { padding: [20, 20] });
        }
    }

    async reverseGeocode(lat, lng) {
        try {
            const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`);
            if (!response.ok) throw new Error('Geocoding failed');
            const data = await response.json();
            return data.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
        } catch (error) {
            console.warn('Reverse geocoding failed:', error);
            return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
        }
    }

    // Driver/Vehicle Selection
    toggleDriverDropdown() {
        this.state.showDriverDropdown = !this.state.showDriverDropdown;
        this.state.showVehicleDropdown = false;
    }

    toggleVehicleDropdown() {
        this.state.showVehicleDropdown = !this.state.showVehicleDropdown;
        this.state.showDriverDropdown = false;
    }

    filterDrivers(ev) {
        const search = ev.target.value.toLowerCase();
        this.state.driverSearch = search;
        this.state.filteredDrivers = this.state.drivers.filter(driver =>
            driver.name.toLowerCase().includes(search)
        );
    }

    filterVehicles(ev) {
        const search = ev.target.value.toLowerCase();
        this.state.vehicleSearch = search;
        this.state.filteredVehicles = this.state.vehicles.filter(vehicle =>
            vehicle.name.toLowerCase().includes(search)
        );
    }

    async selectDriver(driver) {
        if (this.state.currentMission) {
            this.state.currentMission.driver_id = driver.id;
            this.state.currentMission.driver_name = driver.name;
            await this.saveMissionTemplates();
        }
        this.state.showDriverDropdown = false;
    }

    async selectVehicle(vehicle) {
        if (this.state.currentMission) {
            this.state.currentMission.vehicle_id = vehicle.id;
            this.state.currentMission.vehicle_name = vehicle.name;
            await this.saveMissionTemplates();
        }
        this.state.showVehicleDropdown = false;
    }

    // Form Updates
    async updateMissionField(field, value) {
        if (this.state.currentMission) {
            this.state.currentMission[field] = value;
            await this.saveMissionTemplates();
        }
    }

    async updateDestinationField(destIndex, field, value) {
        if (this.state.currentMission && this.state.currentMission.destinations[destIndex]) {
            this.state.currentMission.destinations[destIndex][field] = value;
            await this.saveMissionTemplates();
        }
    }
}

// Register the widget
registry.category("fields").add("bulk_mission_widget", BulkMissionWidget);