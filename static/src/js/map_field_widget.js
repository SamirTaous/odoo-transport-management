/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";

const { Component, onMounted, onWillUpdateProps, onWillUnmount, useRef, useState } = owl;

export class MapFieldWidget extends Component {
    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.marker = null;
        this.state = useState({
            locationText: this.props.record.data[this.props.name] || ""
        });

        onMounted(() => {
            // Defer initialization to ensure the DOM element is fully rendered, especially in modals
            setTimeout(this.initializeMap.bind(this), 0);
        });

        onWillUpdateProps((nextProps) => {
            this.state.locationText = nextProps.record.data[nextProps.name] || "";
            if (this.map && this.marker) {
                const lat = nextProps.record.data.latitude;
                const lon = nextProps.record.data.longitude;
                if (lat && lon) {
                    const newLatLng = L.latLng(lat, lon);
                    if (!this.marker.getLatLng().equals(newLatLng)) {
                        this.marker.setLatLng(newLatLng);
                        this.map.panTo(newLatLng);
                    }
                }
            }
        });

        onWillUnmount(() => {
            // Clean up the map instance to prevent memory leaks when the component is destroyed
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    initializeMap() {
        // Guard: Do not initialize if map already exists or the element isn't there
        if (this.map || !this.mapRef.el) {
            return;
        }

        const lat = this.props.record.data.latitude || 51.505; // Default to London
        const lon = this.props.record.data.longitude || -0.09; // if no coords
        const zoom = (this.props.record.data.latitude && this.props.record.data.longitude) ? 13 : 7;

        this.map = L.map(this.mapRef.el).setView([lat, lon], zoom);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);

        this.marker = L.marker([lat, lon], { draggable: !this.props.readonly }).addTo(this.map);
        
        if (!this.props.readonly) {
            this.map.on('click', (e) => this.updateCoordinates(e.latlng.lat, e.latlng.lng));
            this.marker.on('dragend', (e) => {
                const latLng = e.target.getLatLng();
                this.updateCoordinates(latLng.lat, latLng.lng);
            });
        }
    }

    async updateCoordinates(lat, lng) {
        if (!this.marker) return;
        const latLng = L.latLng(lat, lng);
        this.marker.setLatLng(latLng);
        this.map.panTo(latLng);
        
        const address = await this.reverseGeocode(lat, lng);

        // This is the correct way to update the record in Odoo 16
        await this.props.record.update({
            latitude: lat,
            longitude: lng,
            [this.props.name]: address,
        });

        // The state will be updated automatically by the framework after the record update
    }

    async reverseGeocode(lat, lng) {
        const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`;
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

    onInputChange(ev) {
        this.state.locationText = ev.target.value;
    }

    onInputBlur() {
        // Only update if the text has actually changed
        if (this.props.record.data[this.props.name] !== this.state.locationText) {
            this.props.record.update({ [this.props.name]: this.state.locationText });
        }
    }
}

// *** THIS IS THE CORRECT WAY TO DEFINE METADATA AND REGISTER THE WIDGET ***

// 1. Attach static properties directly to the component class
MapFieldWidget.template = "transport_management.MapFieldWidget";
MapFieldWidget.components = { CharField };
MapFieldWidget.supportedTypes = ["char"];

// 2. Add the component class directly to the registry
registry.category("fields").add("map_selector", MapFieldWidget);