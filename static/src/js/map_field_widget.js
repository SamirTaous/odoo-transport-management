/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CharField } from "@web/views/fields/char/char_field";

const { Component, onMounted, onWillUpdateProps, useRef, useState } = owl;

export class MapFieldWidget extends Component {
    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.marker = null;

        // Set up the initial state for the location text
        this.state = useState({
            locationText: this.props.record.data[this.props.name] || ""
        });

        onMounted(() => {
            this.initializeMap();
        });

        onWillUpdateProps((nextProps) => {
            this.state.locationText = nextProps.record.data[nextProps.name] || "";
            if (this.map && this.marker) {
                const lat = nextProps.record.data.latitude;
                const lon = nextProps.record.data.longitude;
                if (lat && lon) {
                    const newLatLng = L.latLng(lat, lon);
                    this.marker.setLatLng(newLatLng);
                    this.map.panTo(newLatLng);
                }
            }
        });
    }

    initializeMap() {
        const lat = this.props.record.data.latitude || 51.505; // Default to London
        const lon = this.props.record.data.longitude || -0.09; // if no coords
        const zoom = (this.props.record.data.latitude) ? 13 : 7;

        this.map = L.map(this.mapRef.el).setView([lat, lon], zoom);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);

        this.marker = L.marker([lat, lon]).addTo(this.map);
        
        // Only allow map clicks if not in readonly mode
        if (!this.props.readonly) {
            this.map.on('click', this.onMapClick.bind(this));
        }
    }

    async onMapClick(e) {
        const { lat, lng } = e.latlng;
        this.marker.setLatLng(e.latlng);
        this.map.panTo(e.latlng);
        
        // Perform reverse geocoding to get the address
        const address = await this.reverseGeocode(lat, lng);

        // Update the Odoo record
        this.props.record.update({
            latitude: lat,
            longitude: lng,
            [this.props.name]: address, // Update the location field itself
        });

        // Update local state to immediately show the new address
        this.state.locationText = address;
    }

    async reverseGeocode(lat, lng) {
        const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`;
        try {
            const response = await fetch(url);
            if (!response.ok) {
                return "Could not fetch address";
            }
            const data = await response.json();
            return data.display_name || "Unknown Location";
        } catch (error) {
            console.error("Reverse geocoding failed:", error);
            return "Geocoding service unavailable";
        }
    }

    onInputChange(ev) {
        // This allows manual typing in the address box
        this.state.locationText = ev.target.value;
    }

    onInputBlur() {
        // When the user clicks away, update the record with the manually typed value
        this.props.record.update({ [this.props.name]: this.state.locationText });
    }
}

// Define the template for the component
MapFieldWidget.template = "transport_management.MapFieldWidget";

// Add our widget to the field registry
registry.category("fields").add("map_selector", {
    component: MapFieldWidget,
    supportedTypes: ["char"],
});