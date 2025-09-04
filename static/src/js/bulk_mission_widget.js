/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { Component, onMounted, onWillUnmount, useRef, useState } = owl;

export class BulkMissionWidget extends Component {
    static template = "transport_management.BulkMissionWidget";

    setup() {
        this.mapContainer = useRef("mapContainer");
        this.notification = useService("notification");
        this.orm = useService("orm");

        this.map = null;
        this.sourceMarkers = [];
        this.destinationMarkers = [];

        this.state = useState({
            sources: [],
            destinations: [],
            drivers: [],
            vehicles: [],
        });

        onMounted(async () => {
            window.bulkMissionWidget = this;
            this.initializeMap();
            await this.loadDriversAndVehicles();
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

            // Click to add sources
            this.map.on("click", (e) => this.addSource(e.latlng.lat, e.latlng.lng));

            // Right-click to add destinations
            this.map.on("contextmenu", (e) => {
                e.originalEvent.preventDefault();
                this.addDestination(e.latlng.lat, e.latlng.lng);
            });

            // Handle popup events for removal
            this.map.on('popupopen', (e) => {
                const deleteButton = e.popup._container.querySelector('.tm-delete-marker');
                if (deleteButton) {
                    deleteButton.addEventListener('click', () => {
                        const type = deleteButton.dataset.type;
                        const index = parseInt(deleteButton.dataset.index);
                        if (type === 'source') {
                            this.removeSource(index);
                        } else {
                            this.removeDestination(index);
                        }
                        this.map.closePopup();
                    });
                }
            });

            console.log("Bulk location selector map initialized successfully");
        } catch (error) {
            console.error("Error initializing map:", error);
            this.notification.add("Failed to initialize map. Please refresh the page.", { type: "danger" });
        }
    }

    syncStateFromRecord() {
        try {
            const data = JSON.parse(this.props.record.data.mission_templates || '{"sources": [], "destinations": []}');
            this.state.sources = data.sources || [];
            this.state.destinations = data.destinations || [];
            this.updateMapDisplay();
        } catch {
            this.state.sources = [];
            this.state.destinations = [];
        }
    }

    async saveData() {
        const data = {
            sources: this.state.sources,
            destinations: this.state.destinations
        };
        await this.props.record.update({ mission_templates: JSON.stringify(data) });
    }

    async loadDriversAndVehicles() {
        try {
            console.log("Loading drivers and vehicles...");

            // Try to load drivers from different possible models
            let drivers = [];
            try {
                drivers = await this.orm.searchRead("res.partner", [["is_company", "=", false]], ["id", "name"]);
                console.log("Found drivers in res.partner:", drivers.length);
            } catch (e) {
                console.warn("Could not load from res.partner:", e);
                try {
                    drivers = await this.orm.searchRead("hr.employee", [], ["id", "name"]);
                    console.log("Found drivers in hr.employee:", drivers.length);
                } catch (e2) {
                    console.warn("Could not load from hr.employee:", e2);
                }
            }

            // Try to load vehicles from different possible models
            let vehicles = [];
            try {
                vehicles = await this.orm.searchRead("truck.vehicle", [], ["id", "name", "max_weight", "max_volume", "license_plate"]);
                console.log("Found vehicles in truck.vehicle:", vehicles.length);
            } catch (e) {
                console.warn("Could not load from truck.vehicle:", e);
                try {
                    vehicles = await this.orm.searchRead("fleet.vehicle", [], ["id", "name", "model_id"]);
                    console.log("Found vehicles in fleet.vehicle:", vehicles.length);
                } catch (e2) {
                    console.warn("Could not load from fleet.vehicle:", e2);
                }
            }

            console.log("Loaded drivers:", drivers.length, drivers);
            console.log("Loaded vehicles:", vehicles.length, vehicles);

            this.state.drivers = drivers;
            this.state.vehicles = vehicles;

            // Force a re-render to update the metrics
            this.render();

            // Also check what models are available
            await this.debugAvailableModels();
        } catch (error) {
            console.error("Error loading drivers and vehicles:", error);
        }
    }

    // Source Management
    async addSource(lat, lng) {
        try {
            const address = await this.reverseGeocode(lat, lng);

            const newSource = {
                id: Date.now(),
                name: `Source ${this.state.sources.length + 1}`,
                location: address,
                latitude: lat,
                longitude: lng,
                source_type: 'warehouse'
            };

            this.state.sources.push(newSource);
            await this.saveData();
            this.updateMapDisplay();
            this.notification.add(`Source added: ${address.substring(0, 50)}...`, { type: "success" });
        } catch (error) {
            console.error('Error adding source:', error);
            this.notification.add("Failed to add source", { type: "danger" });
        }
    }

    async removeSource(index) {
        this.state.sources.splice(index, 1);
        await this.saveData();
        this.updateMapDisplay();
        this.notification.add("Source removed", { type: "success" });
    }

    async updateSourceField(index, field, value) {
        if (this.state.sources[index]) {
            this.state.sources[index][field] = value;
            await this.saveData();
        }
    }

    // Destination Management
    async addDestination(lat, lng) {
        try {
            const address = await this.reverseGeocode(lat, lng);

            const newDestination = {
                id: Date.now(),
                name: `Destination ${this.state.destinations.length + 1}`,
                location: address,
                latitude: lat,
                longitude: lng,
                mission_type: 'delivery',
                package_type: 'individual',
                total_weight: 0,
                total_volume: 0,
                service_duration: 0,
                requires_signature: false,
                expected_arrival_time: null
            };

            this.state.destinations.push(newDestination);
            await this.saveData();
            this.updateMapDisplay();
            this.notification.add(`Destination added: ${address.substring(0, 50)}...`, { type: "success" });
        } catch (error) {
            console.error('Error adding destination:', error);
            this.notification.add("Failed to add destination", { type: "danger" });
        }
    }

    async removeDestination(index) {
        this.state.destinations.splice(index, 1);
        await this.saveData();
        this.updateMapDisplay();
        this.notification.add("Destination removed", { type: "success" });
    }

    async updateDestinationField(index, field, value) {
        if (this.state.destinations[index]) {
            this.state.destinations[index][field] = value;
            await this.saveData();

            // Update map display if mission type changed
            if (field === 'mission_type') {
                this.updateMapDisplay();
            }
        }
    }

    // Map Display
    updateMapDisplay() {
        if (!this.map) return;

        // Clear existing markers
        this.sourceMarkers.forEach(marker => this.map.removeLayer(marker));
        this.destinationMarkers.forEach(marker => this.map.removeLayer(marker));
        this.sourceMarkers = [];
        this.destinationMarkers = [];

        // Add source markers
        this.state.sources.forEach((source, index) => {
            const marker = L.marker([source.latitude, source.longitude], {
                icon: this.createMarkerIcon('source'),
                draggable: true
            });

            marker.on("dragend", async (e) => {
                const newLatLng = e.target.getLatLng();
                await this.updateSourceLocation(index, newLatLng.lat, newLatLng.lng);
            });

            marker.bindPopup(`
                <div>
                    <strong>${source.name}</strong><br>
                    ${source.location}<br>
                    <small>Type: ${source.source_type}</small><br>
                    <small>Lat: ${source.latitude.toFixed(4)}, Lng: ${source.longitude.toFixed(4)}</small><br>
                    <button class="tm-delete-marker" 
                            data-type="source" 
                            data-index="${index}"
                            style="background: #dc3545; color: white; border: none; padding: 5px 10px; margin-top: 5px; border-radius: 3px; cursor: pointer;">
                        🗑️ Remove Source
                    </button>
                </div>
            `);

            this.sourceMarkers.push(marker);
            marker.addTo(this.map);
        });

        // Add destination markers
        this.state.destinations.forEach((dest, index) => {
            const marker = L.marker([dest.latitude, dest.longitude], {
                icon: this.createMarkerIcon(dest.mission_type),
                draggable: true
            });

            marker.on("dragend", async (e) => {
                const newLatLng = e.target.getLatLng();
                await this.updateDestinationLocation(index, newLatLng.lat, newLatLng.lng);
            });

            marker.bindPopup(`
                <div>
                    <strong>${dest.name}</strong><br>
                    ${dest.location}<br>
                    <small>Type: ${dest.mission_type}</small><br>
                    <small>Weight: ${dest.total_weight} kg</small><br>
                    <small>Lat: ${dest.latitude.toFixed(4)}, Lng: ${dest.longitude.toFixed(4)}</small><br>
                    <button class="tm-delete-marker" 
                            data-type="destination" 
                            data-index="${index}"
                            style="background: #dc3545; color: white; border: none; padding: 5px 10px; margin-top: 5px; border-radius: 3px; cursor: pointer;">
                        🗑️ Remove Destination
                    </button>
                </div>
            `);

            this.destinationMarkers.push(marker);
            marker.addTo(this.map);
        });

        this.fitMapToAllMarkers();
    }

    createMarkerIcon(type) {
        let html;

        if (type === 'source') {
            html = `
                <div class="tm-logistics-marker tm-source-marker">
                    <div class="tm-marker-circle">
                        <div class="tm-marker-icon"><i class="fa fa-truck"></i></div>
                    </div>
                </div>
            `;
        } else {
            const markerClass = type === 'pickup' ? 'tm-pickup-marker' : 'tm-delivery-marker';
            const markerIcon = type === 'pickup' ? '<i class="fa fa-upload"></i>' : '<i class="fa fa-download"></i>';

            html = `
                <div class="tm-logistics-marker ${markerClass}">
                    <div class="tm-marker-circle">
                        <div class="tm-marker-icon">${markerIcon}</div>
                    </div>
                </div>
            `;
        }

        return L.divIcon({
            className: 'tm-logistics-custom-marker',
            html: html,
            iconSize: [40, 40],
            iconAnchor: [20, 20]
        });
    }

    async updateSourceLocation(index, lat, lng) {
        if (this.state.sources[index]) {
            try {
                const address = await this.reverseGeocode(lat, lng);
                this.state.sources[index].location = address;
                this.state.sources[index].latitude = lat;
                this.state.sources[index].longitude = lng;
                await this.saveData();
                this.notification.add("Source location updated", { type: "success" });
            } catch (error) {
                console.error('Error updating source location:', error);
                this.notification.add("Failed to update source location", { type: "danger" });
            }
        }
    }

    async updateDestinationLocation(index, lat, lng) {
        if (this.state.destinations[index]) {
            try {
                const address = await this.reverseGeocode(lat, lng);
                this.state.destinations[index].location = address;
                this.state.destinations[index].latitude = lat;
                this.state.destinations[index].longitude = lng;
                await this.saveData();
                this.notification.add("Destination location updated", { type: "success" });
            } catch (error) {
                console.error('Error updating destination location:', error);
                this.notification.add("Failed to update destination location", { type: "danger" });
            }
        }
    }

    fitMapToAllMarkers() {
        if (!this.map) return;

        const allMarkers = [...this.sourceMarkers, ...this.destinationMarkers];
        if (allMarkers.length > 0) {
            const bounds = new L.FeatureGroup(allMarkers).getBounds();
            if (bounds.isValid()) {
                this.map.fitBounds(bounds, { padding: [50, 50] });
            }
        }
    }

    async clearAllMarkers() {
        if (confirm('Are you sure you want to clear all sources and destinations?')) {
            this.state.sources = [];
            this.state.destinations = [];

            await this.saveData();
            this.updateMapDisplay();
            this.notification.add("All locations cleared", { type: "success" });
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

    // Date/Time formatting
    formatDateTimeForInput(dateTimeString) {
        if (!dateTimeString) return '';
        return dateTimeString.slice(0, 16);
    }

    // Debug method to check available models
    async debugAvailableModels() {
        try {
            console.log("=== DEBUGGING AVAILABLE MODELS ===");

            // Check what models exist
            const models = ['res.partner', 'hr.employee', 'truck.vehicle', 'fleet.vehicle'];

            for (const model of models) {
                try {
                    const count = await this.orm.call(model, 'search_count', [[]]);
                    console.log(`${model}: ${count} records`);
                } catch (e) {
                    console.log(`${model}: NOT AVAILABLE (${e.message})`);
                }
            }

            console.log("=== END DEBUG ===");
        } catch (error) {
            console.error("Debug error:", error);
        }
    }

    // JSON Generation for console logging
    generateCompleteJSON() {
        const completeData = {
            bulk_location_data: {
                created_at: new Date().toISOString(),
                total_sources: this.state.sources.length,
                total_destinations: this.state.destinations.length,
                sources: this.state.sources.map(source => ({
                    ...source,
                    // Ensure all required fields are present
                    source_type: source.source_type || 'warehouse',
                    name: source.name || 'Unnamed Source'
                })),
                destinations: this.state.destinations.map(dest => ({
                    ...dest,
                    // Ensure all required fields are present
                    mission_type: dest.mission_type || 'delivery',
                    package_type: dest.package_type || 'individual',
                    total_weight: dest.total_weight || 0,
                    total_volume: dest.total_volume || 0,
                    service_duration: dest.service_duration || 0,
                    requires_signature: dest.requires_signature || false,
                    expected_arrival_time: dest.expected_arrival_time || null,
                    name: dest.name || 'Unnamed Destination'
                })),
                available_vehicles: this.state.vehicles.map(vehicle => ({
                    ...vehicle,
                    // Include all vehicle details
                    max_weight: vehicle.max_weight || 0,
                    max_volume: vehicle.max_volume || 0,
                    license_plate: vehicle.license_plate || 'N/A'
                })),
                available_drivers: this.state.drivers,
                summary: {
                    total_locations: this.state.sources.length + this.state.destinations.length,
                    pickup_destinations: this.state.destinations.filter(d => d.mission_type === 'pickup').length,
                    delivery_destinations: this.state.destinations.filter(d => d.mission_type === 'delivery').length,
                    total_weight: this.state.destinations.reduce((sum, d) => sum + (d.total_weight || 0), 0),
                    total_volume: this.state.destinations.reduce((sum, d) => sum + (d.total_volume || 0), 0)
                }
            }
        };

        console.log("=== COMPLETE BULK LOCATION JSON ===");
        console.log(JSON.stringify(completeData, null, 2));
        console.log("=== END JSON ===");

        // Also trigger notification
        this.notification.add(
            `JSON generated with ${this.state.sources.length} sources, ${this.state.destinations.length} destinations, and ${this.state.vehicles.length} vehicles. Check browser console.`,
            { type: "success" }
        );

        return completeData;
    }
}

// Register the widget
registry.category("fields").add("bulk_mission_widget", BulkMissionWidget);

// Also register as a standalone widget
registry.category("view_widgets").add("bulk_mission_widget", BulkMissionWidget);