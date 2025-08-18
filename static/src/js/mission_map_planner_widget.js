/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";


const { Component, onMounted, onWillUnmount, onPatched, onWillUpdateProps, useRef, useState } = owl;

// ... (your decodePolyline function remains the same)
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


export class MissionMapPlannerWidget extends Component {
    static components = {};

    setup() {
        // ... (the rest of your setup() method remains exactly the same)
        this.mapContainer = useRef("mapContainer");
        this.notification = useService("notification");

        this.map = null;
        this.sourceMarker = null;
        this.destinationMarkers = {};
        this.routeLayer = null;
        this.routeUpdateTimeout = null;

        this.state = useState({
            source: null,
            destinations: [],
            totalDistance: 0,
            totalDuration: 0,
            showDriverDropdown: false,
            showVehicleDropdown: false,
            drivers: [],
            vehicles: [],
            filteredDrivers: [],
            filteredVehicles: [],
            driverSearch: '',
            vehicleSearch: '',
        });

        onMounted(() => {
            console.log("MissionMapPlannerWidget mounted");
            this.initializeMap();
            this.loadDriversAndVehicles();
        });

        // --- CHANGED: onWillUpdateProps now ONLY syncs state. No map operations here. ---
        onWillUpdateProps(async (nextProps) => {
            console.log("Props updating, syncing state...");
            this.syncStateFromRecord(nextProps.record);
        });

        // --- CHANGED: onPatched is the new, SAFE place for all map drawing. ---
        onPatched(() => {
            console.log("Component patched. Updating map visuals.");
            try {
                this.updateMarkers();
                this.drawRoute();
            } catch (error) {
                console.error("Error in onPatched:", error);
            }
        });

        onWillUnmount(() => {
            if (this.map) {
                console.log("Unmounting map component.");
                this.map.remove();
                this.map = null;
            }
        });

        this.syncStateFromRecord(this.props.record);
    }

    // ... (All other methods like initializeMap, syncStateFromRecord, etc. remain unchanged)
    async initializeMap() {
        if (this.map || !this.mapContainer.el) return;

        if (typeof L === "undefined") {
            this.notification.add("Leaflet library not found. Please ensure Leaflet is loaded.", { type: "danger" });
            return;
        }

        try {
            this.map = L.map(this.mapContainer.el).setView([54.5, -2.0], 6);

            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(this.map);

            this.map.on("click", (e) => this.setSourceLocation(e.latlng.lat, e.latlng.lng));
            this.map.on("contextmenu", (e) => {
                e.originalEvent.preventDefault();
                e.originalEvent.stopPropagation();
                this.addDestination(e.latlng.lat, e.latlng.lng);
            });

            // --- CHANGED: Added robust event handler for delete buttons ---
            this.map.on('popupopen', (e) => {
                const deleteButton = e.popup._container.querySelector('.tm-delete-destination');
                if (deleteButton) {
                    deleteButton.addEventListener('click', () => {
                        const localId = deleteButton.dataset.localId;
                        this.removeDestinationByLocalId(localId);
                        this.map.closePopup();
                    });
                }
            });

            this.updateMarkers();
            this.drawRoute();
            this.fitMapToMarkers();

            console.log("Map initialized successfully");
        } catch (error) {
            console.error("Error initializing map:", error);
            this.notification.add("Failed to initialize map. Please refresh the page.", { type: "danger" });
        }
    }

    syncStateFromRecord(record) {
        console.log("Syncing state from record:", record.data);

        const { source_location, source_latitude, source_longitude } = record.data;
        if (source_latitude && source_longitude) {
            this.state.source = {
                location: source_location || `${source_latitude.toFixed(4)}, ${source_longitude.toFixed(4)}`,
                latitude: source_latitude,
                longitude: source_longitude
            };
        } else {
            this.state.source = null;
        }

        // Handle destinations - check if destination_ids exists and has records
        const destinationIds = record.data.destination_ids;
        if (destinationIds && destinationIds.records && Array.isArray(destinationIds.records)) {
            this.state.destinations = destinationIds.records
                .filter(rec => rec && rec.data && rec.id) // Filter out undefined/null records
                .map(rec => ({
                    id: rec.resId,
                    localId: rec.id,
                    location: rec.data.location || `${rec.data.latitude?.toFixed(4)}, ${rec.data.longitude?.toFixed(4)}`,
                    latitude: rec.data.latitude,
                    longitude: rec.data.longitude,
                    sequence: rec.data.sequence || 1,
                    expected_arrival_time: rec.data.expected_arrival_time,
                    estimated_arrival_time: rec.data.estimated_arrival_time,
                    estimated_departure_time: rec.data.estimated_departure_time,
                    service_duration: rec.data.service_duration || 0,
                    package_type: rec.data.package_type,
                    total_weight: rec.data.total_weight || 0,
                    total_volume: rec.data.total_volume || 0,
                    requires_signature: rec.data.requires_signature
                }))
                .filter(dest => dest.latitude && dest.longitude)
                .sort((a, b) => a.sequence - b.sequence);
        } else {
            this.state.destinations = [];
        }

        console.log("State synced:", {
            source: this.state.source,
            destinations: this.state.destinations
        });
    }

    updateMarkers() {
        // --- CHANGED: Added safety guard ---
        if (!this.map) return;

        Object.values(this.destinationMarkers).forEach(m => this.map.removeLayer(m));
        this.destinationMarkers = {};

        if (this.state.source) {
            const latLng = [this.state.source.latitude, this.state.source.longitude];
            if (!this.sourceMarker) {
                this.sourceMarker = L.marker(latLng, {
                    draggable: true,
                    icon: this.createMarkerIcon('blue')
                }).addTo(this.map);

                this.sourceMarker.on("dragend", async (e) => {
                    const newLatLng = e.target.getLatLng();
                    await this.setSourceLocation(newLatLng.lat, newLatLng.lng);
                });
            } else {
                this.sourceMarker.setLatLng(latLng);
                // FIXED: Update the source marker icon when mission type changes
                this.sourceMarker.setIcon(this.createMarkerIcon('blue'));
            }
            this.sourceMarker.bindPopup(`...`).getPopup().setContent(`
                <div>
                    <strong>Source Location</strong><br>
                    ${this.state.source.location}<br>
                    <small>Lat: ${this.state.source.latitude.toFixed(4)}, Lng: ${this.state.source.longitude.toFixed(4)}</small>
                </div>
            `);
        } else if (this.sourceMarker) {
            this.map.removeLayer(this.sourceMarker);
            this.sourceMarker = null;
        }

        this.state.destinations.forEach((dest) => {
            const latLng = [dest.latitude, dest.longitude];
            const marker = L.marker(latLng, {
                draggable: true,
                icon: this.createMarkerIcon('red', dest.sequence)
            }).addTo(this.map);

            marker.localId = dest.localId;

            // --- CHANGED: Popup uses a class and data-attributes instead of window hack ---
            const popupContent = `
                <div>
                    <strong>Destination ${dest.sequence}</strong><br>
                    ${dest.location}<br>
                    <small>Lat: ${dest.latitude.toFixed(4)}, Lng: ${dest.longitude.toFixed(4)}</small><br>
                    <button class="tm-delete-destination" data-local-id="${dest.localId}"
                            style="background: #dc3545; color: white; border: none; padding: 5px 10px; margin-top: 5px; border-radius: 3px; cursor: pointer;">
                        🗑️ Delete
                    </button>
                </div>
            `;

            marker.bindPopup(popupContent);

            marker.on("dragend", async (e) => {
                const newLatLng = e.target.getLatLng();
                await this.updateDestination(e.target.localId, newLatLng.lat, newLatLng.lng);
            });

            this.destinationMarkers[dest.localId] = marker;
        });
    }

    createMarkerIcon(color, number = null) {
        const isSource = color === 'blue';
        const missionType = this.props.record.data.mission_type || 'delivery';

        let missionTypeClass;

        if (isSource) {
            missionTypeClass = missionType === 'pickup' ? 'tm-pickup-source' : 'tm-delivery-source';
        } else {
            missionTypeClass = missionType === 'pickup' ? 'tm-pickup-destination' : 'tm-delivery-destination';
        }

        let html;

        if (isSource) {
            // Source marker with compact design
            const sourceIcon = missionType === 'pickup' ? '🏭' : '📦';
            html = `
                <div class="tm-compact-marker ${missionTypeClass}">
                    <div class="tm-marker-pin">
                        <div class="tm-marker-icon">${sourceIcon}</div>
                    </div>
                </div>
            `;
        } else {
            // Destination marker with compact design and number
            const destinationIcon = missionType === 'pickup' ? '📤' : '📥';
            html = `
                <div class="tm-compact-marker ${missionTypeClass}">
                    <div class="tm-marker-pin">
                        <div class="tm-marker-number">${number}</div>
                        <div class="tm-marker-icon">${destinationIcon}</div>
                    </div>
                </div>
            `;
        }

        return L.divIcon({
            className: 'tm-custom-marker',
            html: html,
            iconSize: [40, 50],
            iconAnchor: [20, 45]
        });
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

    async setSourceLocation(lat, lng) {
        try {
            const address = await this.reverseGeocode(lat, lng);
            console.log("Setting source location:", { address, lat, lng });

            await this.props.record.update({
                source_location: address,
                source_latitude: lat,
                source_longitude: lng,
            });

            this.notification.add("Source location updated", { type: "success" });
        } catch (error) {
            console.error('Error setting source location:', error);
            this.notification.add("Failed to set source location", { type: "danger" });
        }
    }

    async addDestination(lat, lng) {
        try {
            const list = this.props.record.data.destination_ids;
            const newRecord = await list.addNew({ position: "bottom" });

            const address = await this.reverseGeocode(lat, lng);
            const newSequence = (this.state.destinations.length > 0)
                ? Math.max(0, ...this.state.destinations.map(d => d.sequence)) + 1 : 1;

            console.log("Updating new record with data:", { address, lat, lng, sequence: newSequence });

            await newRecord.update({
                location: address,
                latitude: lat,
                longitude: lng,
                sequence: newSequence,
            });

            this.notification.add(`Destination ${newSequence} added`, { type: "success" });

        } catch (error) {
            console.error('Error adding destination:', error);
            this.notification.add("Failed to add destination", { type: "danger" });
        }
    }

    async updateDestination(localId, lat, lng) {
        try {
            const address = await this.reverseGeocode(lat, lng);
            const recordToUpdate = this.props.record.data.destination_ids.records.find(rec => rec.id === localId);

            if (recordToUpdate) {
                await recordToUpdate.update({
                    location: address,
                    latitude: lat,
                    longitude: lng
                });

                this.notification.add("Destination updated", { type: "success" });

                // --- THIS IS THE CRITICAL FIX ---
                // Manually trigger a redraw of the route after the drag operation completes.
                await this.drawRoute();
                // -----------------------------
            }
        } catch (error) {
            console.error('Error updating destination:', error);
            this.notification.add("Failed to update destination", { type: "danger" });
        }
    }

    // FIXED: Method for removing destination by localId
    async removeDestinationByLocalId(localId) {
        try {
            console.log("Removing destination with localId:", localId);

            const list = this.props.record.data.destination_ids;
            if (!list || !list.records) {
                console.error("No destination list found");
                return;
            }

            const recordToDelete = list.records.find(rec => rec && rec.id === localId);

            if (recordToDelete) {
                // Check if it's a virtual record (new, unsaved record)
                if (typeof recordToDelete.resId !== 'number' || recordToDelete.resId <= 0) {
                    // For virtual records, use the list's removeRecord method
                    console.log("Removing virtual record:", localId);
                    await list.removeRecord(recordToDelete);
                } else {
                    // For saved records, use the normal delete method
                    console.log("Deleting saved record:", recordToDelete.resId);
                    await recordToDelete.delete();
                }
                this.notification.add("Destination removed", { type: "success" });
            } else {
                console.error("Record not found for localId:", localId);
                this.notification.add("Failed to remove destination", { type: "danger" });
            }
        } catch (error) {
            console.error('Error removing destination:', error);
            this.notification.add("Failed to remove destination", { type: "danger" });
        }
    }

    // Keep the original method for backward compatibility
    async removeDestination(index) {
        try {
            const destToRemove = this.state.destinations[index];
            if (!destToRemove) return;

            await this.removeDestinationByLocalId(destToRemove.localId);
        } catch (error) {
            console.error('Error removing destination:', error);
            this.notification.add("Failed to remove destination", { type: "danger" });
        }
    }

    async clearAllMarkers() {
        if (confirm('Are you sure you want to clear all markers?')) {
            try {
                console.log("Starting clearAllMarkers operation");

                // Clear all routes immediately - this should remove ghost routes
                this.clearRoute();

                // Clear source first
                await this.props.record.update({
                    source_location: false,
                    source_latitude: false,
                    source_longitude: false,
                });

                // Get the list of destinations
                const list = this.props.record.data.destination_ids;

                if (list && list.records && list.records.length > 0) {
                    console.log(`Clearing ${list.records.length} destination records`);

                    // Clear destinations one by one to ensure proper deletion
                    const recordsToDelete = [...list.records]; // Create a copy to avoid mutation issues

                    for (const record of recordsToDelete) {
                        try {
                            if (typeof record.resId === 'number' && record.resId > 0) {
                                // For saved records, use delete
                                console.log(`Deleting saved record ${record.resId}`);
                                await record.delete();
                            } else {
                                // For virtual/new records, use removeRecord
                                console.log(`Removing virtual record ${record.id}`);
                                await list.removeRecord(record);
                            }
                        } catch (recordError) {
                            console.error(`Error deleting record ${record.id}:`, recordError);
                            // Continue with other records even if one fails
                        }
                    }
                }

                // Clear visual elements immediately to prevent UI issues
                this.clearRoute();
                if (this.sourceMarker && this.map) {
                    try {
                        this.map.removeLayer(this.sourceMarker);
                    } catch (e) {
                        console.warn("Error removing source marker:", e);
                    }
                    this.sourceMarker = null;
                }

                // Clear destination markers safely
                Object.values(this.destinationMarkers).forEach(marker => {
                    if (marker && this.map) {
                        try {
                            this.map.removeLayer(marker);
                        } catch (e) {
                            console.warn("Error removing destination marker:", e);
                        }
                    }
                });
                this.destinationMarkers = {};

                // Force state sync to ensure UI reflects the cleared state
                this.state.source = null;
                this.state.destinations = [];

                // Wait a moment for the UI to update before proceeding
                await new Promise(resolve => setTimeout(resolve, 50));

                // Final route clearing to ensure no ghost routes remain
                this.clearRoute();

                this.notification.add("All markers cleared", { type: "success" });
                console.log("clearAllMarkers operation completed");
            } catch (error) {
                console.error('Error clearing markers:', error);
                this.notification.add("Failed to clear all markers", { type: "danger" });
            }
        }
    }

    fitMapToMarkers() {
        if (!this.map) return;

        if (this.state.destinations.length > 0 || this.state.source) {
            const allMarkers = [
                ...Object.values(this.destinationMarkers),
                ...(this.sourceMarker ? [this.sourceMarker] : [])
            ];
            if (allMarkers.length > 0) {
                const bounds = new L.FeatureGroup(allMarkers).getBounds();
                if (bounds.isValid()) {
                    this.map.fitBounds(bounds, { padding: [50, 50] });
                }
            }
        }
    }

    clearRoute() {
        if (!this.map) return;

        // Remove the tracked route layer
        if (this.routeLayer) {
            try {
                this.map.removeLayer(this.routeLayer);
            } catch (error) {
                console.warn('Error removing tracked route layer:', error);
            }
            this.routeLayer = null;
        }

        // Also remove any polyline layers that might be lingering
        // This is a more aggressive cleanup to handle ghost routes
        this.map.eachLayer((layer) => {
            if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
                try {
                    this.map.removeLayer(layer);
                } catch (error) {
                    console.warn('Error removing polyline layer:', error);
                }
            }
        });
    }

    debouncedDrawRoute() {
        // Clear any existing timeout
        if (this.routeUpdateTimeout) {
            clearTimeout(this.routeUpdateTimeout);
        }

        // Set a new timeout to debounce rapid route updates
        this.routeUpdateTimeout = setTimeout(() => {
            this.drawRoute();
        }, 100);
    }

    async drawRoute() {
        if (!this.map) return;

        // Always clear existing route first to prevent ghost routes
        this.clearRoute();

        // Small delay to ensure the route layer is fully removed
        await new Promise(resolve => setTimeout(resolve, 10));

        // Gather all current points
        const points = [];
        if (this.state.source) {
            points.push([this.state.source.longitude, this.state.source.latitude]);
        }
        this.state.destinations.forEach(d => {
            if (d.latitude && d.longitude) {
                points.push([d.longitude, d.latitude]);
            }
        });

        // If not enough points for a route, ensure distance is zero and exit
        if (points.length < 2) {
            this.state.totalDistance = 0;
            this.state.totalDuration = 0;
            if (this.props.record.data.total_distance_km !== 0) {
                if (this.props.record.resId) {
                    this.props.record.model.orm.call(
                        "transport.mission",
                        "update_distance_from_widget",
                        [this.props.record.resId, 0, 0]
                    );
                } else {
                    this.props.record.update({ 
                        total_distance_km: 0,
                        estimated_duration_minutes: 0
                    });
                }
            }
            return;
        }

        try {
            // Try to get cached route data from backend if this is a saved mission
            let routeData = null;
            if (this.props.record.resId) {
                try {
                    routeData = await this.props.record.model.orm.call(
                        "transport.mission",
                        "get_cached_route_data",
                        [this.props.record.resId]
                    );
                } catch (e) {
                    console.warn("Failed to get cached route, falling back to OSRM:", e);
                }
            }

            if (routeData) {
                // Use cached route
                let routeGeometry;
                
                if (routeData.is_fallback) {
                    // Handle fallback route (stored as JSON points)
                    const cachedPoints = JSON.parse(routeData.geometry);
                    routeGeometry = cachedPoints;
                } else {
                    // Handle OSRM polyline geometry
                    routeGeometry = decodePolyline(routeData.geometry);
                }

                const missionType = this.props.record.data.mission_type || 'delivery';
                const routeColor = missionType === 'pickup' ? '#17a2b8' : '#28a745';

                const routeOptions = {
                    className: 'tm-route-line',
                    color: routeColor,
                    weight: 6,
                    opacity: 0.8
                };

                // Add visual indicator for fallback routes
                if (routeData.is_fallback) {
                    routeOptions.dashArray = '10, 5';
                    routeOptions.opacity = 0.6;
                    routeOptions.className += ' tm-route-fallback';
                }

                this.routeLayer = L.polyline(routeGeometry, routeOptions).addTo(this.map);

                // Update distance and duration from cached data
                this.state.totalDistance = routeData.distance;
                this.state.totalDuration = routeData.duration;
                if (Math.abs(this.props.record.data.total_distance_km - routeData.distance) > 0.01) {
                    // Use the new method to update distance with proper calculation method tracking
                    if (this.props.record.resId) {
                        this.props.record.model.orm.call(
                            "transport.mission",
                            "update_distance_from_widget",
                            [this.props.record.resId, routeData.distance, routeData.duration]
                        );
                    } else {
                        this.props.record.update({ 
                            total_distance_km: routeData.distance,
                            estimated_duration_minutes: routeData.duration
                        });
                    }
                }

                console.log(`Using cached route (${routeData.is_fallback ? 'fallback' : 'OSRM'})`);
                return;
            }

            // No cached route available, proceed with OSRM calculation
            const coordinates = points.map(p => p.join(',')).join(';');
            const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${coordinates}?overview=full&geometries=polyline`;

            const response = await fetch(osrmUrl);
            if (!response.ok) throw new Error(`OSRM request failed: ${response.statusText}`);
            const data = await response.json();

            // Safety check - component might have been unmounted during async operation
            if (!this.map) return;

            if (data.code !== "Ok" || !data.routes || data.routes.length === 0) {
                throw new Error(data.message || "No route found by OSRM.");
            }

            const route = data.routes[0];
            const routeGeometry = decodePolyline(route.geometry);
            const routeDistance = route.distance / 1000;
            const routeDuration = route.duration / 60; // Convert seconds to minutes

            const missionType = this.props.record.data.mission_type || 'delivery';
            const routeColor = missionType === 'pickup' ? '#17a2b8' : '#28a745';

            this.routeLayer = L.polyline(routeGeometry, {
                className: 'tm-route-line',
                color: routeColor,
                weight: 6,
                opacity: 0.8
            }).addTo(this.map);

            // Update both the record and the state for UI display
            this.state.totalDistance = routeDistance;
            this.state.totalDuration = routeDuration;
            if (Math.abs(this.props.record.data.total_distance_km - routeDistance) > 0.01) {
                // Use the new method to update distance with proper calculation method tracking
                if (this.props.record.resId) {
                    this.props.record.model.orm.call(
                        "transport.mission",
                        "update_distance_from_widget",
                        [this.props.record.resId, routeDistance, routeDuration]
                    );
                } else {
                    this.props.record.update({ 
                        total_distance_km: routeDistance,
                        estimated_duration_minutes: routeDuration
                    });
                }
            }

            console.log("Calculated new OSRM route");
            
            // Also trigger backend recalculation to ensure consistency
            if (this.props.record.resId) {
                this.props.record.model.orm.call(
                    "transport.mission",
                    "action_recalculate_distance",
                    [this.props.record.resId]
                ).catch(error => {
                    console.warn("Failed to trigger backend distance recalculation:", error);
                });
            }

        } catch (error) {
            console.error("Error fetching route:", error);
            this.notification.add("Could not calculate road route.", { type: "warning" });

            if (!this.map) return;

            // Clear route before adding fallback route
            this.clearRoute();

            const missionType = this.props.record.data.mission_type || 'delivery';
            const fallbackColor = missionType === 'pickup' ? '#6f42c1' : '#dc3545';

            const latLngPoints = points.map(p => [p[1], p[0]]);
            this.routeLayer = L.polyline(latLngPoints, {
                className: 'tm-route-line tm-route-fallback',
                color: fallbackColor,
                weight: 4,
                opacity: 0.6,
                dashArray: '10, 5'
            }).addTo(this.map);
        }
    }

    /**
    * A generic method to update any field on the mission record.
    * This is a robust way to avoid repeating code.
    * @param {string} fieldName The technical name of the field to update.
    * @param {any} value The new value for the field.
    */
    async _updateRecord(fieldName, value) {
        try {
            await this.props.record.update({ [fieldName]: value });
        } catch (error) {
            console.error(`Error updating field ${fieldName}:`, error);
            this.notification.add(`Failed to update ${fieldName}.`, { type: 'danger' });
        }
    }

    /**
     * Handles changes for the Mission Type radio buttons.
     * @param {Event} ev The browser event.
     */
    async onMissionTypeChange(ev) {
        await this._updateRecord('mission_type', ev.target.value);
        // Refresh markers to reflect the new mission type styling
        this.updateMarkers();
        // Also update the route color to match the new mission type
        this.drawRoute();
    }



    /**
     * Handles changes for the Priority radio buttons.
     * @param {Event} ev The browser event.
     */
    onPriorityChange(ev) {
        this._updateRecord('priority', ev.target.value);
    }

    /**
     * Handles changes for the Notes textarea.
     * @param {Event} ev The browser event.
     */
    onNotesChange(ev) {
        this._updateRecord('notes', ev.target.value);
    }

    /**
     * Updates the mission state (status workflow).
     * @param {string} newState The new state to set.
     */
    async updateMissionState(newState) {
        try {
            await this.props.record.update({ state: newState });
            this.notification.add(`Mission status updated to ${newState}`, { type: "success" });
        } catch (error) {
            console.error('Error updating mission state:', error);
            this.notification.add("Failed to update mission status", { type: "danger" });
        }
    }

    /**
     * Optimizes the route by reordering destinations for shortest path.
     */
    async optimizeRoute() {
        if (!this.state.source || this.state.destinations.length < 2) {
            this.notification.add("Need at least 2 destinations to optimize route", { type: "warning" });
            return;
        }

        try {
            this.notification.add("Optimizing route...", { type: "info" });

            // Create points array with source first
            const points = [
                [this.state.source.longitude, this.state.source.latitude],
                ...this.state.destinations.map(d => [d.longitude, d.latitude])
            ];

            // Use OSRM Table API to get distance matrix
            const coordinates = points.map(p => p.join(',')).join(';');
            const tableUrl = `https://router.project-osrm.org/table/v1/driving/${coordinates}`;

            const response = await fetch(tableUrl);
            if (!response.ok) throw new Error('OSRM table request failed');
            const data = await response.json();

            if (data.code !== "Ok" || !data.durations) {
                throw new Error("Failed to get distance matrix");
            }

            // Simple nearest neighbor optimization starting from source (index 0)
            const distances = data.durations;
            const unvisited = new Set(Array.from({ length: this.state.destinations.length }, (_, i) => i + 1));
            const optimizedOrder = [];
            let current = 0; // Start from source

            while (unvisited.size > 0) {
                let nearest = null;
                let nearestDistance = Infinity;

                for (const dest of unvisited) {
                    if (distances[current][dest] < nearestDistance) {
                        nearestDistance = distances[current][dest];
                        nearest = dest;
                    }
                }

                if (nearest !== null) {
                    optimizedOrder.push(nearest - 1); // Convert back to destination index
                    unvisited.delete(nearest);
                    current = nearest;
                }
            }

            // Update destination sequences based on optimized order
            const list = this.props.record.data.destination_ids;
            for (let i = 0; i < optimizedOrder.length; i++) {
                const destIndex = optimizedOrder[i];
                const record = list.records[destIndex];
                if (record) {
                    await record.update({ sequence: i + 1 });
                }
            }

            this.notification.add("Route optimized successfully!", { type: "success" });
        } catch (error) {
            console.error('Error optimizing route:', error);
            this.notification.add("Failed to optimize route", { type: "danger" });
        }
    }

    async loadDriversAndVehicles() {
        try {
            // Load drivers
            const drivers = await this.env.services.orm.searchRead(
                'res.partner',
                [['is_company', '=', false]],
                ['id', 'name'],
                { limit: 100, order: 'name' }
            );
            
            // Load vehicles
            const vehicles = await this.env.services.orm.searchRead(
                'transport.vehicle',
                [],
                ['id', 'name'],
                { limit: 100, order: 'name' }
            );

            this.state.drivers = drivers;
            this.state.vehicles = vehicles;
            this.state.filteredDrivers = drivers;
            this.state.filteredVehicles = vehicles;
        } catch (error) {
            console.error('Error loading drivers and vehicles:', error);
        }
    }

    toggleDriverDropdown() {
        this.state.showDriverDropdown = !this.state.showDriverDropdown;
        this.state.showVehicleDropdown = false; // Close vehicle dropdown
        if (this.state.showDriverDropdown) {
            this.state.driverSearch = '';
            this.state.filteredDrivers = this.state.drivers;
        }
    }

    toggleVehicleDropdown() {
        this.state.showVehicleDropdown = !this.state.showVehicleDropdown;
        this.state.showDriverDropdown = false; // Close driver dropdown
        if (this.state.showVehicleDropdown) {
            this.state.vehicleSearch = '';
            this.state.filteredVehicles = this.state.vehicles;
        }
    }

    filterDrivers() {
        const search = this.state.driverSearch.toLowerCase();
        this.state.filteredDrivers = this.state.drivers.filter(driver => 
            driver.name.toLowerCase().includes(search)
        );
    }

    filterVehicles() {
        const search = this.state.vehicleSearch.toLowerCase();
        this.state.filteredVehicles = this.state.vehicles.filter(vehicle => 
            vehicle.name.toLowerCase().includes(search)
        );
    }

    async selectDriver(driver) {
        try {
            console.log('Selecting driver:', driver);
            
            // For Many2one fields, we need to pass [id, name] tuple
            const driverValue = [driver.id, driver.name];
            
            await this.props.record.update({
                driver_id: driverValue
            });
            
            this.state.showDriverDropdown = false;
            this.notification.add(`Driver "${driver.name}" selected successfully`, { type: "success" });
            
            console.log('Driver updated, new record data:', this.props.record.data);
        } catch (error) {
            console.error('Error selecting driver:', error);
            this.notification.add("Failed to select driver", { type: "danger" });
        }
    }

    async selectVehicle(vehicle) {
        try {
            console.log('Selecting vehicle:', vehicle);
            
            // For Many2one fields, we need to pass [id, name] tuple
            const vehicleValue = [vehicle.id, vehicle.name];
            
            await this.props.record.update({
                vehicle_id: vehicleValue
            });
            
            this.state.showVehicleDropdown = false;
            this.notification.add(`Vehicle "${vehicle.name}" selected successfully`, { type: "success" });
            
            console.log('Vehicle updated, new record data:', this.props.record.data);
        } catch (error) {
            console.error('Error selecting vehicle:', error);
            this.notification.add("Failed to select vehicle", { type: "danger" });
        }
    }
}

MissionMapPlannerWidget.template = "transport_management.MissionMapPlannerWidget";
registry.category("view_widgets").add("mission_map_planner", MissionMapPlannerWidget);