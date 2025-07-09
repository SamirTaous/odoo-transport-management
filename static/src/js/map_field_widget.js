/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";

const { Component, onMounted, onWillUpdateProps, onWillUnmount, useRef, useState } = owl;

export class MapFieldWidget extends Component {
    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.marker = null;

        // Get lat/lon field names from options passed in the XML
        this.latField = this.props.options?.latitude_field || 'latitude';
        this.lonField = this.props.options?.longitude_field || 'longitude';

        this.state = useState({
            locationText: this.props.record.data[this.props.name] || ""
        });

        onMounted(() => {
            setTimeout(this.initializeMap.bind(this), 0);
        });

        onWillUpdateProps((nextProps) => {
            this.state.locationText = nextProps.record.data[nextProps.name] || "";
            if (this.map && this.marker) {
                const lat = nextProps.record.data[this.latField];
                const lon = nextProps.record.data[this.lonField];
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
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    initializeMap() {
        if (this.map || !this.mapRef.el) return;

        const lat = this.props.record.data[this.latField] || 51.505;
        const lon = this.props.record.data[this.lonField] || -0.09;
        const zoom = (this.props.record.data[this.latField] && this.props.record.data[this.lonField]) ? 13 : 7;

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

        // --- CORE CHANGE IS HERE ---
        // We no longer update the lat/lon fields directly from JS.
        // Instead, we update our main field and pass the coordinates in the context.
        // An onchange method in Python will catch this context and do the work.
        this.props.record.update(
            { [this.props.name]: address },
            {
                // This 'context' key is a special option for the update method
                context: {
                    [this.latField]: lat,
                    [this.lonField]: lng,
                }
            }
        );
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
        if (this.props.record.data[this.props.name] !== this.state.locationText) {
            this.props.record.update({ [this.props.name]: this.state.locationText });
        }
    }
}

MapFieldWidget.template = "transport_management.MapFieldWidget";
MapFieldWidget.components = { CharField };
MapFieldWidget.supportedTypes = ["char"];

registry.category("fields").add("map_selector", MapFieldWidget);