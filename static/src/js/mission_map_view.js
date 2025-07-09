/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const { Component, onMounted, onWillUpdateProps, onWillUnmount, useRef, useState } = owl;

export class MissionMapViewWidget extends Component {
    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.markers = {}; // Store markers by destination virtual ID
        this.state = useState({
            selectedDestinationId: null,
        });

        this.rootRef = useRef("root");
        onMounted(() => {
            this.initializeMap();
            // Listen for clicks within the entire form view to detect row selections
            this.rootRef.el.closest('.o_form_view').addEventListener('click', this.onRowClick.bind(this), true);
        });
        
        onWillUnmount(() => {
            // Clean up the event listener when the component is destroyed to prevent memory leaks
            const formView = this.rootRef.el.closest('.o_form_view');
            if(formView) {
                formView.removeEventListener('click', this.onRowClick.bind(this), true);
            }
        });

        onWillUpdateProps((nextProps) => {
            // Re-draw markers when the destination list changes
            this.updateMarkers(nextProps.record.data.destination_ids);
        });
    }

    onRowClick(ev) {
        // Find the closest table row (tr) for a destination
        const destinationRow = ev.target.closest('.o_field_x2many_list .o_data_row');
        if (!destinationRow) {
            // If the click is outside a row and not on the map, unselect
            if(!ev.target.closest('.tm-map-container')) {
                 this.unselectRow();
            }
            return;
        }

        const destinationId = destinationRow.dataset.id;
        if (destinationId && destinationId !== this.state.selectedDestinationId) {
            this.selectRow(destinationId, destinationRow);
        }
    }

    selectRow(destinationId, rowElement) {
        this.unselectRow(); // Unselect previous row first
        this.state.selectedDestinationId = destinationId;
        rowElement.classList.add('tm-row-selected');

        // Pan map to the corresponding marker and open its popup
        if (this.markers[destinationId]) {
            const marker = this.markers[destinationId].marker;
            this.map.panTo(marker.getLatLng(), { animate: true });
            marker.openPopup();
        }
    }

    unselectRow() {
        if (!this.state.selectedDestinationId) return;

        const formView = this.rootRef.el.closest('.o_form_view');
        const selectedRow = formView ? formView.querySelector('.tm-row-selected') : null;
        if (selectedRow) {
            selectedRow.classList.remove('tm-row-selected');
        }

        if(this.markers[this.state.selectedDestinationId]){
            this.markers[this.state.selectedDestinationId].marker.closePopup();
        }
        this.state.selectedDestinationId = null;
    }

    initializeMap() {
        this.map = L.map(this.mapRef.el).setView([46.603354, 1.888334], 5); // Default view (France)

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);

        this.updateMarkers(this.props.record.data.destination_ids);
        this.map.on('click', this.onMapClick.bind(this));
    }

    updateMarkers(destinations) {
        const destinationRecords = destinations.records;
        const currentMarkerIds = Object.keys(this.markers);
        const newMarkerIds = destinationRecords.map(rec => rec.id);

        // Remove markers for deleted destinations
        currentMarkerIds.forEach(id => {
            if (!newMarkerIds.includes(id)) {
                this.markers[id].marker.remove();
                delete this.markers[id];
            }
        });

        // Add or update markers
        destinationRecords.forEach((rec, index) => {
            const lat = rec.data.latitude;
            const lon = rec.data.longitude;
            const locationName = rec.data.location || `Destination ${index + 1}`;

            if (lat && lon) {
                if (this.markers[rec.id]) {
                    this.markers[rec.id].marker.setLatLng([lat, lon]);
                    this.markers[rec.id].marker.getPopup().setContent(`<b>${index + 1}. ${locationName}</b>`);
                } else {
                    const marker = L.marker([lat, lon]).addTo(this.map)
                        .bindPopup(`<b>${index + 1}. ${locationName}</b>`);
                    this.markers[rec.id] = { marker: marker };
                }
            }
        });
    }

    async onMapClick(e) {
        if (!this.state.selectedDestinationId) {
            this.env.services.notification.add(
                "Please select a destination from the list to update its location.",
                { type: "info" }
            );
            return;
        }

        const { lat, lng } = e.latlng;
        const address = await this.reverseGeocode(lat, lng);

        // Update the Odoo record for the selected destination
        this.props.record.update({
            destination_ids: [
                [1, this.state.selectedDestinationId, {
                    latitude: lat,
                    longitude: lng,
                    location: address,
                }]
            ]
        });
    }

    async reverseGeocode(lat, lng) {
        const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`;
        try {
            const response = await fetch(url);
            if (!response.ok) return "Could not fetch address";
            const data = await response.json();
            return data.display_name || "Unknown Location";
        } catch (error) {
            console.error("Reverse geocoding failed:", error);
            return "Geocoding service unavailable";
        }
    }
}

MissionMapViewWidget.template = "transport_management.MissionMapViewWidget";
MissionMapViewWidget.props = { ...standardFieldProps };

registry.category("fields").add("mission_map_view", {
    component: MissionMapViewWidget,
});