/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { Component, onMounted, onWillUnmount, onWillUpdateProps, useRef, useState } = owl;

// Helper to calculate distance
function haversineDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth's radius in km
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

export class MissionMapPlannerWidget extends Component {
    setup() {
        this.mapContainer = useRef("mapContainer");
        this.notification = useService("notification");
        
        this.map = null;
        this.sourceMarker = null;
        this.destinationMarkers = {}; // Use object for easy lookup by localId
        this.routeLayer = null;

        this.state = useState({
            source: null,
            destinations: [],
            totalDistance: 0,
        });

        onMounted(() => {
            console.log("MissionMapPlannerWidget mounted");
            this.initializeMap();
        });

        onWillUpdateProps(async (nextProps) => {
            console.log("Props updating, syncing state...");
            this.syncStateFromRecord(nextProps.record);
            this.updateMarkers();
            this.drawRoute();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });

        // Initial sync
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
            
            // Add tile layer
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(this.map);

            // Left click to set source location
            this.map.on("click", (e) => {
                console.log("Map clicked at:", e.latlng);
                this.setSourceLocation(e.latlng.lat, e.latlng.lng);
            });

            // Right click to add destination
            this.map.on("contextmenu", (e) => {
                console.log("Right click at:", e.latlng);
                e.originalEvent.preventDefault();
                 e.originalEvent.stopPropagation();
                this.addDestination(e.latlng.lat, e.latlng.lng);
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
        if (destinationIds && destinationIds.records) {
            this.state.destinations = destinationIds.records.map(rec => ({
                id: rec.resId,
                localId: rec.id,
                location: rec.data.location || `${rec.data.latitude?.toFixed(4)}, ${rec.data.longitude?.toFixed(4)}`,
                latitude: rec.data.latitude,
                longitude: rec.data.longitude,
                sequence: rec.data.sequence || 1
            })).filter(dest => dest.latitude && dest.longitude)
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
        if (!this.map) return;

        // Clear existing destination markers
        Object.values(this.destinationMarkers).forEach(m => this.map.removeLayer(m));
        this.destinationMarkers = {};

        // Update source marker
        if (this.state.source) {
            const latLng = [this.state.source.latitude, this.state.source.longitude];
            if (!this.sourceMarker) {
                this.sourceMarker = L.marker(latLng, { 
                    draggable: true, 
                    icon: this.createMarkerIcon('blue') 
                }).addTo(this.map);
                
                this.sourceMarker.bindPopup(`
                    <div>
                        <strong>Source Location</strong><br>
                        ${this.state.source.location}<br>
                        <small>Lat: ${this.state.source.latitude.toFixed(4)}, Lng: ${this.state.source.longitude.toFixed(4)}</small>
                    </div>
                `);
                
                this.sourceMarker.on("dragend", (e) => {
                    const newLatLng = e.target.getLatLng();
                    this.setSourceLocation(newLatLng.lat, newLatLng.lng);
                });
            } else {
                this.sourceMarker.setLatLng(latLng);
                this.sourceMarker.getPopup().setContent(`
                    <div>
                        <strong>Source Location</strong><br>
                        ${this.state.source.location}<br>
                        <small>Lat: ${this.state.source.latitude.toFixed(4)}, Lng: ${this.state.source.longitude.toFixed(4)}</small>
                    </div>
                `);
            }
        } else if (this.sourceMarker) {
            this.map.removeLayer(this.sourceMarker);
            this.sourceMarker = null;
        }

        // Update destination markers
        this.state.destinations.forEach((dest, index) => {
            const latLng = [dest.latitude, dest.longitude];
            const marker = L.marker(latLng, { 
                draggable: true, 
                icon: this.createMarkerIcon('red', dest.sequence) 
            }).addTo(this.map);
            
            marker.localId = dest.localId;
            
            marker.bindPopup(`
                <div>
                    <strong>Destination ${dest.sequence}</strong><br>
                    ${dest.location}<br>
                    <small>Lat: ${dest.latitude.toFixed(4)}, Lng: ${dest.longitude.toFixed(4)}</small>
                </div>
            `);
            
            marker.on("dragend", (e) => {
                const newLatLng = e.target.getLatLng();
                this.updateDestination(e.target.localId, newLatLng.lat, newLatLng.lng);
            });
            
            this.destinationMarkers[dest.localId] = marker;
        });

        console.log("Markers updated:", {
            source: !!this.sourceMarker,
            destinations: Object.keys(this.destinationMarkers).length
        });
    }

    createMarkerIcon(color, number = null) {
        const faColor = color === 'blue' ? '#007bff' : '#dc3545';
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
            // [THE FIX]
            // We must call addNew() with a position argument.
            // We can get the current number of records and use that as the index
            // to add the new line at the end of the list.
            const list = this.props.record.data.destination_ids;
            const newRecord = await list.addNew(
                {
                    position: "bottom"
                }
            );
            
            // Now that we have the new (empty) record, we can update it.
            const address = await this.reverseGeocode(lat, lng);
            const newSequence = (this.state.destinations.length > 0)
                ? Math.max(0, ...this.state.destinations.map(d => d.sequence)) + 1 : 1;

            console.log("Updating new record with data:", { address, lat, lng, sequence: newSequence });

            // Call .update() on the new record itself.
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
            const destToUpdate = this.state.destinations.find(d => d.localId === localId);
            if (!destToUpdate) return;

            console.log("Updating destination:", { localId, address, lat, lng });

            const command = destToUpdate.id 
                ? [1, destToUpdate.id, { location: address, latitude: lat, longitude: lng }]
                : [1, localId, { location: address, latitude: lat, longitude: lng }];

            await this.props.record.update({ destination_ids: [command] });
            this.notification.add("Destination updated", { type: "success" });
        } catch (error) {
            console.error('Error updating destination:', error);
            this.notification.add("Failed to update destination", { type: "danger" });
        }
    }

    async removeDestination(index) {
        try {
            const destToRemove = this.state.destinations[index];
            if (!destToRemove) return;
            
            console.log("Removing destination:", destToRemove);
            
            const command = destToRemove.id ? [2, destToRemove.id] : [2, destToRemove.localId];
            await this.props.record.update({ destination_ids: [command] });
            this.notification.add("Destination removed", { type: "success" });
        } catch (error) {
            console.error('Error removing destination:', error);
            this.notification.add("Failed to remove destination", { type: "danger" });
        }
    }

    clearAllMarkers() {
        if (confirm('Are you sure you want to clear all markers?')) {
            this.props.record.update({
                source_location: false,
                source_latitude: false,
                source_longitude: false,
                destination_ids: [[5, 0, 0]]
            });
            this.notification.add("All markers cleared", { type: "success" });
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

    drawRoute() {
        if (!this.map) return;
        
        if (this.routeLayer) {
            this.map.removeLayer(this.routeLayer);
        }
        
        const points = [];
        if (this.state.source) {
            points.push([this.state.source.latitude, this.state.source.longitude]);
        }
        this.state.destinations.forEach(d => points.push([d.latitude, d.longitude]));

        if (points.length > 1) {
            // Draw route line
            this.routeLayer = L.polyline(points, { 
                color: '#007bff', 
                weight: 4, 
                opacity: 0.7,
                dashArray: '10, 5'
            }).addTo(this.map);
            
            // Calculate total distance
            let distance = 0;
            for (let i = 0; i < points.length - 1; i++) {
                distance += haversineDistance(points[i][0], points[i][1], points[i+1][0], points[i+1][1]);
            }
            this.state.totalDistance = distance;
            
            // Update record if distance changed
            if (Math.abs(this.props.record.data.total_distance_km - distance) > 0.01) {
                this.props.record.update({ total_distance_km: distance });
            }
        } else {
            this.state.totalDistance = 0;
            if (this.props.record.data.total_distance_km !== 0) {
                this.props.record.update({ total_distance_km: 0 });
            }
        }
    }
}

MissionMapPlannerWidget.template = "transport_management.MissionMapPlannerWidget";
registry.category("view_widgets").add("mission_map_planner", MissionMapPlannerWidget);