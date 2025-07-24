/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { Component, onMounted, onWillUnmount, onPatched, onWillUpdateProps, useRef, useState } = owl;

// Helper function to calculate osrm distance 
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
    setup() {
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
        });

        onMounted(() => {
            console.log("MissionMapPlannerWidget mounted");
            this.initializeMap();
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
                    sequence: rec.data.sequence || 1
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
        const backgroundColor = color === 'blue' ? '#007bff' : '#dc3545';

        let html;
        if (number) {
            html = `
                <div class="tm-marker-number" style="
                    background-color: ${backgroundColor}; 
                    color: white; 
                    width: 30px; 
                    height: 30px; 
                    border-radius: 50%; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    font-weight: bold; 
                    font-size: 14px;
                    border: 2px solid white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                ">${number}</div>
            `;
        } else {
            html = `
                <div style="
                    background-color: ${backgroundColor}; 
                    color: white; 
                    width: 30px; 
                    height: 30px; 
                    border-radius: 50%; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    font-weight: bold; 
                    font-size: 16px;
                    border: 2px solid white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                ">S</div>
            `;
        }

        return L.divIcon({
            className: 'tm-custom-marker',
            html: html,
            iconSize: [30, 30],
            iconAnchor: [15, 15]
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
            if (this.props.record.data.total_distance_km !== 0) {
                this.props.record.update({ total_distance_km: 0 });
            }
            return;
        }

        // Proceed with fetching and drawing the new route
        const coordinates = points.map(p => p.join(',')).join(';');
        const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${coordinates}?overview=full&geometries=polyline`;

        try {
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

            // Clear route again before adding new one (extra safety)
            this.clearRoute();

            this.routeLayer = L.polyline(routeGeometry, {
                color: '#007bff',
                weight: 5,
                opacity: 0.7
            }).addTo(this.map);

            if (Math.abs(this.props.record.data.total_distance_km - routeDistance) > 0.01) {
                this.props.record.update({ total_distance_km: routeDistance });
            }
        } catch (error) {
            console.error("Error fetching route from OSRM:", error);
            this.notification.add("Could not calculate road route.", { type: "warning" });

            if (!this.map) return;

            // Clear route before adding fallback route
            this.clearRoute();

            const latLngPoints = points.map(p => [p[1], p[0]]);
            this.routeLayer = L.polyline(latLngPoints, {
                color: 'red',
                weight: 3,
                opacity: 0.5,
                dashArray: '5, 10'
            }).addTo(this.map);
        }
    }
}

MissionMapPlannerWidget.template = "transport_management.MissionMapPlannerWidget";
registry.category("view_widgets").add("mission_map_planner", MissionMapPlannerWidget);