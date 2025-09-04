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

            // Load all truck information from truck.vehicle model
            let vehicles = [];
            try {
                vehicles = await this.orm.searchRead("truck.vehicle", [], [
                    "id", "name", "license_plate", "vin_number", "year", "brand", "model_name",
                    "ownership_type", "driver_id", "truck_type", "max_payload", "cargo_volume",
                    "cargo_length", "cargo_width", "cargo_height", "overall_length", "overall_width",
                    "overall_height", "gross_vehicle_weight", "engine_power", "fuel_type",
                    "fuel_capacity", "fuel_consumption", "has_crane", "has_tailgate",
                    "has_refrigeration", "has_gps", "special_equipment", "registration_expiry",
                    "insurance_expiry", "inspection_due", "maintenance_status", "odometer",
                    "last_service_odometer", "service_interval_km", "purchase_price",
                    "current_value", "is_available", "rental_status", "km_until_service",
                    "rental_start_date", "rental_end_date", "rental_cost_per_day", "subcontractor_id"
                ]);
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

            console.log("Final state - Drivers:", this.state.drivers.length, "Vehicles:", this.state.vehicles.length);
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
                expected_arrival_time: null,
                priority_delivery: false,
                contact_name: '',
                contact_phone: '',
                special_instructions: ''
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

    // Destination Popup Management
    openDestinationPopup(destIndex) {
        const destination = this.state.destinations[destIndex];
        if (!destination) return;

        // Store current editing destination
        this.currentEditingIndex = destIndex;
        this.currentEditingDestination = { ...destination }; // Clone to avoid direct mutation

        // Create and show modal
        this.showDestinationModal();
    }

    showDestinationModal() {
        const destination = this.currentEditingDestination;
        
        // Create modal HTML
        const modalHTML = `
            <div class="modal fade" id="destinationModal" tabindex="-1" role="dialog">
                <div class="modal-dialog modal-lg" role="document">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fa fa-flag-checkered me-2"></i>
                                Destination Details - ${destination.name || 'Unnamed Destination'}
                            </h5>
                            <button type="button" class="btn-close" onclick="window.bulkMissionWidget.closeDestinationModal()" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <form class="tm_destination_form">
                                <!-- Basic Information -->
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <label class="form-label">Destination Name</label>
                                        <input type="text" class="form-control" id="dest_name" 
                                               value="${destination.name || ''}"
                                               placeholder="Enter destination name"/>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label">Mission Type</label>
                                        <div class="tm_type_radio_group">
                                            <label class="tm_type_radio_option ${destination.mission_type === 'pickup' ? 'active' : ''}">
                                                <input type="radio" name="mission_type_popup" value="pickup" 
                                                       ${destination.mission_type === 'pickup' ? 'checked' : ''}/>
                                                <i class="fa fa-arrow-up"></i>
                                                <span>Pickup</span>
                                            </label>
                                            <label class="tm_type_radio_option ${destination.mission_type === 'delivery' || !destination.mission_type ? 'active' : ''}">
                                                <input type="radio" name="mission_type_popup" value="delivery" 
                                                       ${destination.mission_type === 'delivery' || !destination.mission_type ? 'checked' : ''}/>
                                                <i class="fa fa-arrow-down"></i>
                                                <span>Delivery</span>
                                            </label>
                                        </div>
                                    </div>
                                </div>

                                <!-- Location Information -->
                                <div class="row mb-3">
                                    <div class="col-12">
                                        <label class="form-label">Address</label>
                                        <textarea class="form-control" rows="2" readonly>${destination.location}</textarea>
                                    </div>
                                </div>

                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <label class="form-label">Latitude</label>
                                        <input type="number" class="form-control" readonly value="${destination.latitude}"/>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label">Longitude</label>
                                        <input type="number" class="form-control" readonly value="${destination.longitude}"/>
                                    </div>
                                </div>

                                <!-- Package Information -->
                                <h6 class="mb-3"><i class="fa fa-box me-2"></i>Package Information</h6>
                                <div class="row mb-3">
                                    <div class="col-md-4">
                                        <label class="form-label">Weight (kg)</label>
                                        <input type="number" class="form-control" id="dest_weight"
                                               value="${destination.total_weight || 0}" step="0.1" min="0"/>
                                    </div>
                                    <div class="col-md-4">
                                        <label class="form-label">Volume (m³)</label>
                                        <input type="number" class="form-control" id="dest_volume"
                                               value="${destination.total_volume || 0}" step="0.01" min="0"/>
                                    </div>
                                    <div class="col-md-4">
                                        <label class="form-label">Package Type</label>
                                        <select class="form-select" id="dest_package_type">
                                            <option value="individual" ${destination.package_type === 'individual' ? 'selected' : ''}>Individual</option>
                                            <option value="pallet" ${destination.package_type === 'pallet' ? 'selected' : ''}>Pallet</option>
                                        </select>
                                    </div>
                                </div>

                                <!-- Service Information -->
                                <h6 class="mb-3"><i class="fa fa-clock me-2"></i>Service Information</h6>
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <label class="form-label">Service Duration (minutes)</label>
                                        <input type="number" class="form-control" id="dest_service_duration"
                                               value="${destination.service_duration || 0}" min="0"/>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label">Expected Arrival</label>
                                        <input type="datetime-local" class="form-control" id="dest_expected_arrival"
                                               value="${this.formatDateTimeForInput(destination.expected_arrival_time)}"/>
                                    </div>
                                </div>

                                <!-- Additional Options -->
                                <h6 class="mb-3"><i class="fa fa-cog me-2"></i>Additional Options</h6>
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <div class="form-check">
                                            <input type="checkbox" class="form-check-input" id="dest_requires_signature"
                                                   ${destination.requires_signature ? 'checked' : ''}/>
                                            <label class="form-check-label">Requires Signature</label>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="form-check">
                                            <input type="checkbox" class="form-check-input" id="dest_priority_delivery"
                                                   ${destination.priority_delivery ? 'checked' : ''}/>
                                            <label class="form-check-label">Priority Delivery</label>
                                        </div>
                                    </div>
                                </div>

                                <!-- Contact Information -->
                                <h6 class="mb-3"><i class="fa fa-user me-2"></i>Contact Information</h6>
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <label class="form-label">Contact Name</label>
                                        <input type="text" class="form-control" id="dest_contact_name"
                                               value="${destination.contact_name || ''}" placeholder="Contact person name"/>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label">Contact Phone</label>
                                        <input type="tel" class="form-control" id="dest_contact_phone"
                                               value="${destination.contact_phone || ''}" placeholder="Phone number"/>
                                    </div>
                                </div>

                                <!-- Special Instructions -->
                                <div class="row mb-3">
                                    <div class="col-12">
                                        <label class="form-label">Special Instructions</label>
                                        <textarea class="form-control" rows="3" id="dest_special_instructions"
                                                  placeholder="Any special delivery instructions...">${destination.special_instructions || ''}</textarea>
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" onclick="window.bulkMissionWidget.closeDestinationModal()">Close</button>
                            <button type="button" class="btn btn-primary" onclick="window.bulkMissionWidget.saveDestinationModal()">Save Changes</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('destinationModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Show modal
        const modal = document.getElementById('destinationModal');
        modal.style.display = 'block';
        modal.classList.add('show');
        document.body.classList.add('modal-open');

        // Add backdrop
        const backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop fade show';
        backdrop.id = 'destinationModalBackdrop';
        document.body.appendChild(backdrop);

        // Handle radio button changes
        const radioButtons = modal.querySelectorAll('input[name="mission_type_popup"]');
        radioButtons.forEach(radio => {
            radio.addEventListener('change', (e) => {
                // Update active class
                modal.querySelectorAll('.tm_type_radio_option').forEach(option => {
                    option.classList.remove('active');
                });
                e.target.closest('.tm_type_radio_option').classList.add('active');
            });
        });
    }

    closeDestinationModal() {
        const modal = document.getElementById('destinationModal');
        const backdrop = document.getElementById('destinationModalBackdrop');
        
        if (modal) {
            modal.style.display = 'none';
            modal.classList.remove('show');
            modal.remove();
        }
        
        if (backdrop) {
            backdrop.remove();
        }
        
        document.body.classList.remove('modal-open');
    }

    saveDestinationModal() {
        const modal = document.getElementById('destinationModal');
        if (!modal) return;

        // Get all form values
        const updatedDestination = {
            ...this.currentEditingDestination,
            name: modal.querySelector('#dest_name').value,
            mission_type: modal.querySelector('input[name="mission_type_popup"]:checked').value,
            total_weight: parseFloat(modal.querySelector('#dest_weight').value) || 0,
            total_volume: parseFloat(modal.querySelector('#dest_volume').value) || 0,
            package_type: modal.querySelector('#dest_package_type').value,
            service_duration: parseInt(modal.querySelector('#dest_service_duration').value) || 0,
            expected_arrival_time: modal.querySelector('#dest_expected_arrival').value,
            requires_signature: modal.querySelector('#dest_requires_signature').checked,
            priority_delivery: modal.querySelector('#dest_priority_delivery').checked,
            contact_name: modal.querySelector('#dest_contact_name').value,
            contact_phone: modal.querySelector('#dest_contact_phone').value,
            special_instructions: modal.querySelector('#dest_special_instructions').value
        };

        // Update the destination
        this.updateDestinationFromPopup(this.currentEditingIndex, updatedDestination);
        
        // Close modal
        this.closeDestinationModal();
    }

    updateDestinationFromPopup(destIndex, updatedDestination) {
        if (this.state.destinations[destIndex]) {
            // Update the destination with all the new data
            Object.assign(this.state.destinations[destIndex], updatedDestination);
            this.saveData();
            this.updateMapDisplay();
            this.notification.add("Destination updated", { type: "success" });
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
                    // Include all truck details from truck maintenance module
                    max_payload: vehicle.max_payload || 0,
                    cargo_volume: vehicle.cargo_volume || 0,
                    license_plate: vehicle.license_plate || 'N/A',
                    brand: vehicle.brand || 'unknown',
                    model_name: vehicle.model_name || 'unknown',
                    truck_type: vehicle.truck_type || 'rigid',
                    fuel_type: vehicle.fuel_type || 'diesel',
                    ownership_type: vehicle.ownership_type || 'owned',
                    maintenance_status: vehicle.maintenance_status || 'good',
                    is_available: vehicle.is_available !== undefined ? vehicle.is_available : true,
                    rental_status: vehicle.rental_status || 'N/A',
                    // Capacity and dimensions
                    cargo_length: vehicle.cargo_length || 0,
                    cargo_width: vehicle.cargo_width || 0,
                    cargo_height: vehicle.cargo_height || 0,
                    overall_length: vehicle.overall_length || 0,
                    overall_width: vehicle.overall_width || 0,
                    overall_height: vehicle.overall_height || 0,
                    gross_vehicle_weight: vehicle.gross_vehicle_weight || 0,
                    // Engine and performance
                    engine_power: vehicle.engine_power || 0,
                    fuel_capacity: vehicle.fuel_capacity || 0,
                    fuel_consumption: vehicle.fuel_consumption || 0,
                    // Special equipment
                    has_crane: vehicle.has_crane || false,
                    has_tailgate: vehicle.has_tailgate || false,
                    has_refrigeration: vehicle.has_refrigeration || false,
                    has_gps: vehicle.has_gps || false,
                    special_equipment: vehicle.special_equipment || '',
                    // Maintenance and service
                    odometer: vehicle.odometer || 0,
                    last_service_odometer: vehicle.last_service_odometer || 0,
                    service_interval_km: vehicle.service_interval_km || 0,
                    km_until_service: vehicle.km_until_service || 0,
                    // Financial
                    purchase_price: vehicle.purchase_price || 0,
                    current_value: vehicle.current_value || 0,
                    rental_cost_per_day: vehicle.rental_cost_per_day || 0,
                    // Dates (convert to strings for JSON)
                    registration_expiry: vehicle.registration_expiry || null,
                    insurance_expiry: vehicle.insurance_expiry || null,
                    inspection_due: vehicle.inspection_due || null,
                    rental_start_date: vehicle.rental_start_date || null,
                    rental_end_date: vehicle.rental_end_date || null,
                    // Additional info
                    year: vehicle.year || 0,
                    vin_number: vehicle.vin_number || '',
                    driver_id: vehicle.driver_id || null,
                    subcontractor_id: vehicle.subcontractor_id || null
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

    // AI Optimization
    async optimizeWithAI() {
        if (this.state.sources.length === 0 && this.state.destinations.length === 0) {
            this.notification.add("Please add sources and destinations before optimizing", { type: "warning" });
            return;
        }

        try {
            // Save current data first
            await this.saveData();

            // Show loading notification
            this.notification.add("🤖 AI is optimizing your missions... This may take a moment.", { type: "info" });

            // Call the backend AI optimization
            const result = await this.orm.call(
                "bulk.mission.wizard",
                "action_optimize_with_ai",
                [this.props.record.resId]
            );

            // After optimization completes, get the AI results and log them
            if (result && result.params && result.params.type === 'success') {
                // Get the AI optimization results
                try {
                    const aiResult = await this.orm.call(
                        "bulk.mission.wizard",
                        "get_ai_optimization_result",
                        [this.props.record.resId]
                    );
                    
                    if (aiResult) {
                        this.handleAIOptimizationResult({
                            ai_response: aiResult,
                            summary: aiResult.optimization_summary || {},
                            title: result.params.title,
                            message: result.params.message
                        });
                    } else {
                        console.log("No AI results found");
                        this.notification.add(result.params.message, { type: "success" });
                    }
                } catch (error) {
                    console.error("Failed to get AI results:", error);
                    this.notification.add(result.params.message, { type: "success" });
                }
            } else {
                console.log("AI Optimization result:", result);
            }

        } catch (error) {
            console.error('AI optimization failed:', error);
            this.notification.add("AI optimization failed. Check console for details.", { type: "danger" });
        }
    }

    // Handle AI Optimization Results
    handleAIOptimizationResult(params) {
        const { ai_response, summary, title, message } = params;

        // Log comprehensive results to browser console
        console.log("🤖 ===== AI MISSION OPTIMIZATION RESULTS =====");
        console.log("📊 OPTIMIZATION SUMMARY:");
        console.log(`✅ Missions Created: ${summary.missions_created}`);
        console.log(`🚛 Vehicles Used: ${summary.vehicles_used}`);
        console.log(`📏 Total Distance: ${summary.total_distance} km`);
        console.log(`💰 Total Cost: ${summary.total_cost}`);
        console.log(`⭐ Optimization Score: ${summary.optimization_score}/100`);
        console.log(`💡 Cost Savings: ${summary.cost_savings}%`);
        
        console.log("\n🎯 COMPLETE AI RESPONSE:");
        console.log(JSON.stringify(ai_response, null, 2));
        
        // Log individual missions for easy analysis
        const missions = ai_response.created_missions || [];
        console.log(`\n📋 CREATED MISSIONS (${missions.length} total):`);
        
        missions.forEach((mission, index) => {
            console.log(`\n--- Mission ${index + 1}: ${mission.mission_name || 'Unnamed'} ---`);
            console.log(`🚛 Vehicle: ${mission.assigned_vehicle?.vehicle_name} (${mission.assigned_vehicle?.license_plate})`);
            console.log(`👤 Driver: ${mission.assigned_driver?.driver_name}`);
            console.log(`📍 Source: ${mission.source_location?.name} - ${mission.source_location?.location}`);
            console.log(`🎯 Destinations (${mission.destinations?.length || 0}):`);
            
            mission.destinations?.forEach((dest, destIndex) => {
                console.log(`  ${destIndex + 1}. ${dest.name} (${dest.mission_type})`);
                console.log(`     📍 ${dest.location}`);
                console.log(`     📦 Weight: ${dest.cargo_details?.total_weight}kg, Volume: ${dest.cargo_details?.total_volume}m³`);
            });
            
            console.log(`📊 Route Stats:`);
            console.log(`   Distance: ${mission.route_optimization?.total_distance_km}km`);
            console.log(`   Duration: ${mission.route_optimization?.estimated_duration_hours}h`);
            console.log(`   Cost: ${mission.route_optimization?.estimated_total_cost}`);
            console.log(`   Weight Utilization: ${mission.capacity_utilization?.weight_utilization_percentage}%`);
            console.log(`   Volume Utilization: ${mission.capacity_utilization?.volume_utilization_percentage}%`);
        });

        // Log insights and recommendations
        const insights = ai_response.optimization_insights || {};
        if (insights.key_decisions?.length > 0) {
            console.log("\n🎯 KEY OPTIMIZATION DECISIONS:");
            insights.key_decisions.forEach((decision, index) => {
                console.log(`${index + 1}. ${decision}`);
            });
        }

        if (insights.recommendations?.length > 0) {
            console.log("\n💡 AI RECOMMENDATIONS:");
            insights.recommendations.forEach((rec, index) => {
                console.log(`${index + 1}. ${rec}`);
            });
        }

        if (insights.alternative_scenarios?.length > 0) {
            console.log("\n🔄 ALTERNATIVE SCENARIOS CONSIDERED:");
            insights.alternative_scenarios.forEach((scenario, index) => {
                console.log(`${index + 1}. ${scenario.scenario_name}: ${scenario.description}`);
                console.log(`   Trade-offs: ${scenario.trade_offs}`);
            });
        }

        console.log("\n🤖 ===== END AI OPTIMIZATION RESULTS =====");

        // Show success notification
        this.notification.add(message, { type: "success" });

        // Also create a summary table in console for quick reference
        console.table(missions.map((mission, index) => ({
            'Mission': index + 1,
            'Name': mission.mission_name || 'Unnamed',
            'Vehicle': mission.assigned_vehicle?.vehicle_name || 'Unknown',
            'Driver': mission.assigned_driver?.driver_name || 'Unknown',
            'Destinations': mission.destinations?.length || 0,
            'Distance (km)': mission.route_optimization?.total_distance_km || 0,
            'Duration (h)': mission.route_optimization?.estimated_duration_hours || 0,
            'Cost': mission.route_optimization?.estimated_total_cost || 0,
            'Weight %': mission.capacity_utilization?.weight_utilization_percentage || 0,
            'Volume %': mission.capacity_utilization?.volume_utilization_percentage || 0
        })));
    }
}

// Helper method for date formatting
BulkMissionWidget.prototype.formatDateTimeForInput = function(dateTimeString) {
    if (!dateTimeString) return '';
    return dateTimeString.slice(0, 16);
};

// Register the widget
registry.category("fields").add("bulk_mission_widget", BulkMissionWidget);

// Also register as a standalone widget
registry.category("view_widgets").add("bulk_mission_widget", BulkMissionWidget);