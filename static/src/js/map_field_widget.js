"use client"

/** @odoo-module **/
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"
import { Component, onMounted, onWillUnmount, onWillUpdateProps, useRef, useState } from "odoo/owl"
import L from "leaflet"

// Helper to calculate distance
function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371 // Earth's radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

export class MissionMapPlannerWidget extends Component {
  setup() {
    this.mapContainer = useRef("mapContainer")
    this.notification = useService("notification")
    this.orm = useService("orm")

    this.map = null
    this.sourceMarker = null
    this.destinationMarkers = {}
    this.routeLayer = null

    this.state = useState({
      source: null,
      destinations: [],
      totalDistance: 0,
    })

    onMounted(() => {
      console.log("MissionMapPlannerWidget mounted")
      setTimeout(() => this.initializeMap(), 100)
    })

    onWillUpdateProps(async (nextProps) => {
      console.log("Props updating, syncing state...")
      this.syncStateFromRecord(nextProps.record)
      setTimeout(() => {
        this.updateMarkers()
        this.drawRoute()
      }, 50)
    })

    onWillUnmount(() => {
      if (this.map) {
        this.map.remove()
        this.map = null
      }
    })

    // Initial sync
    this.syncStateFromRecord(this.props.record)
  }

  async initializeMap() {
    if (this.map || !this.mapContainer.el) return

    if (typeof L === "undefined") {
      this.notification.add("Leaflet library not found. Please ensure Leaflet is loaded.", { type: "danger" })
      return
    }

    try {
      this.map = L.map(this.mapContainer.el).setView([54.5, -2.0], 6)

      // Add tile layer
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
        maxZoom: 19,
      }).addTo(this.map)

      // Left click to set source location
      this.map.on("click", (e) => {
        console.log("Map clicked at:", e.latlng)
        this.setSourceLocation(e.latlng.lat, e.latlng.lng)
      })

      // Right click to add destination
      this.map.on("contextmenu", (e) => {
        console.log("Right click at:", e.latlng)
        e.originalEvent.preventDefault()
        this.addDestination(e.latlng.lat, e.latlng.lng)
      })

      // Initial setup
      setTimeout(() => {
        this.updateMarkers()
        this.drawRoute()
        this.fitMapToMarkers()
      }, 100)

      console.log("Map initialized successfully")
    } catch (error) {
      console.error("Error initializing map:", error)
      this.notification.add("Failed to initialize map. Please refresh the page.", { type: "danger" })
    }
  }

  syncStateFromRecord(record) {
    console.log("Syncing state from record:", record.data)

    const { source_location, source_latitude, source_longitude } = record.data

    if (source_latitude && source_longitude) {
      this.state.source = {
        location: source_location || `${source_latitude.toFixed(4)}, ${source_longitude.toFixed(4)}`,
        latitude: source_latitude,
        longitude: source_longitude,
      }
    } else {
      this.state.source = null
    }

    // Handle destinations - check if destination_ids exists and has records
    const destinationIds = record.data.destination_ids
    if (destinationIds && destinationIds.records) {
      this.state.destinations = destinationIds.records
        .map((rec) => ({
          id: rec.resId,
          localId: rec.id,
          location: rec.data.location || `${rec.data.latitude?.toFixed(4)}, ${rec.data.longitude?.toFixed(4)}`,
          latitude: rec.data.latitude,
          longitude: rec.data.longitude,
          sequence: rec.data.sequence || 1,
        }))
        .filter((dest) => dest.latitude && dest.longitude)
        .sort((a, b) => a.sequence - b.sequence)
    } else {
      this.state.destinations = []
    }

    console.log("State synced:", {
      source: this.state.source,
      destinations: this.state.destinations,
    })
  }

  updateMarkers() {
    if (!this.map) return

    // Clear existing destination markers
    Object.values(this.destinationMarkers).forEach((m) => this.map.removeLayer(m))
    this.destinationMarkers = {}

    // Update source marker
    if (this.state.source) {
      const latLng = [this.state.source.latitude, this.state.source.longitude]

      if (!this.sourceMarker) {
        this.sourceMarker = L.marker(latLng, {
          draggable: true,
          icon: this.createMarkerIcon("blue"),
        }).addTo(this.map)

        this.sourceMarker.bindPopup(`
                    <div>
                        <strong>Source Location</strong><br>${this.state.source.location}<br>
                        <small>Lat: ${this.state.source.latitude.toFixed(4)}, Lng: ${this.state.source.longitude.toFixed(4)}</small>
                    </div>
                `)

        this.sourceMarker.on("dragend", (e) => {
          const newLatLng = e.target.getLatLng()
          this.setSourceLocation(newLatLng.lat, newLatLng.lng)
        })
      } else {
        this.sourceMarker.setLatLng(latLng)
        this.sourceMarker.getPopup().setContent(`
                    <div>
                        <strong>Source Location</strong><br>${this.state.source.location}<br>
                        <small>Lat: ${this.state.source.latitude.toFixed(4)}, Lng: ${this.state.source.longitude.toFixed(4)}</small>
                    </div>
                `)
      }
    } else if (this.sourceMarker) {
      this.map.removeLayer(this.sourceMarker)
      this.sourceMarker = null
    }

    // Update destination markers
    this.state.destinations.forEach((dest, index) => {
      const latLng = [dest.latitude, dest.longitude]
      const marker = L.marker(latLng, {
        draggable: true,
        icon: this.createMarkerIcon("red", dest.sequence),
      }).addTo(this.map)

      marker.localId = dest.localId
      marker.bindPopup(`
                <div>
                    <strong>Destination ${dest.sequence}</strong><br>${dest.location}<br>
                    <small>Lat: ${dest.latitude.toFixed(4)}, Lng: ${dest.longitude.toFixed(4)}</small>
                </div>
            `)

      marker.on("dragend", (e) => {
        const newLatLng = e.target.getLatLng()
        this.updateDestination(e.target.localId, newLatLng.lat, newLatLng.lng)
      })

      this.destinationMarkers[dest.localId] = marker
    })

    console.log("Markers updated:", {
      source: !!this.sourceMarker,
      destinations: Object.keys(this.destinationMarkers).length,
    })
  }

  createMarkerIcon(color, number = null) {
    const backgroundColor = color === "blue" ? "#007bff" : "#dc3545"
    let html

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
            `
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
            `
    }

    return L.divIcon({
      className: "tm-custom-marker",
      html: html,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    })
  }

  async reverseGeocode(lat, lng) {
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`)
      if (!response.ok) throw new Error("Geocoding failed")
      const data = await response.json()
      return data.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`
    } catch (error) {
      console.warn("Reverse geocoding failed:", error)
      return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
    }
  }

  async setSourceLocation(lat, lng) {
    try {
      const address = await this.reverseGeocode(lat, lng)
      console.log("Setting source location:", { address, lat, lng })

      await this.props.record.update({
        source_location: address,
        source_latitude: lat,
        source_longitude: lng,
      })

      this.notification.add("Source location updated", { type: "success" })
    } catch (error) {
      console.error("Error setting source location:", error)
      this.notification.add("Failed to set source location", { type: "danger" })
    }
  }

  async addDestination(lat, lng) {
    try {
      const address = await this.reverseGeocode(lat, lng)
      const newSequence =
        this.state.destinations.length > 0 ? Math.max(...this.state.destinations.map((d) => d.sequence)) + 1 : 1

      console.log("Adding destination:", { address, lat, lng, sequence: newSequence })

      // Create new destination using ORM
      const missionId = this.props.record.resId
      if (!missionId) {
        this.notification.add("Please save the mission first", { type: "warning" })
        return
      }

      await this.orm.create("transport.destination", [
        {
          mission_id: missionId,
          location: address,
          latitude: lat,
          longitude: lng,
          sequence: newSequence,
        },
      ])

      // Reload the record to get updated destinations
      await this.props.record.load()

      this.notification.add(`Destination ${newSequence} added`, { type: "success" })
    } catch (error) {
      console.error("Error adding destination:", error)
      this.notification.add("Failed to add destination", { type: "danger" })
    }
  }

  async updateDestination(localId, lat, lng) {
    try {
      const address = await this.reverseGeocode(lat, lng)
      const destToUpdate = this.state.destinations.find((d) => d.localId === localId)
      if (!destToUpdate || !destToUpdate.id) return

      console.log("Updating destination:", { localId, address, lat, lng })

      await this.orm.write("transport.destination", [destToUpdate.id], {
        location: address,
        latitude: lat,
        longitude: lng,
      })

      // Reload the record
      await this.props.record.load()

      this.notification.add("Destination updated", { type: "success" })
    } catch (error) {
      console.error("Error updating destination:", error)
      this.notification.add("Failed to update destination", { type: "danger" })
    }
  }

  async removeDestination(index) {
    try {
      const destToRemove = this.state.destinations[index]
      if (!destToRemove || !destToRemove.id) return

      console.log("Removing destination:", destToRemove)

      await this.orm.unlink("transport.destination", [destToRemove.id])

      // Reload the record
      await this.props.record.load()

      this.notification.add("Destination removed", { type: "success" })
    } catch (error) {
      console.error("Error removing destination:", error)
      this.notification.add("Failed to remove destination", { type: "danger" })
    }
  }

  async clearAllMarkers() {
    if (confirm("Are you sure you want to clear all markers?")) {
      try {
        // Clear destinations
        const destinationIds = this.state.destinations.map((d) => d.id).filter((id) => id)
        if (destinationIds.length > 0) {
          await this.orm.unlink("transport.destination", destinationIds)
        }

        // Clear source
        await this.props.record.update({
          source_location: false,
          source_latitude: false,
          source_longitude: false,
        })

        // Reload the record
        await this.props.record.load()

        this.notification.add("All markers cleared", { type: "success" })
      } catch (error) {
        console.error("Error clearing markers:", error)
        this.notification.add("Failed to clear markers", { type: "danger" })
      }
    }
  }

  fitMapToMarkers() {
    if (!this.map) return

    if (this.state.destinations.length > 0 || this.state.source) {
      const allMarkers = [...Object.values(this.destinationMarkers), ...(this.sourceMarker ? [this.sourceMarker] : [])]

      if (allMarkers.length > 0) {
        const bounds = new L.FeatureGroup(allMarkers).getBounds()
        if (bounds.isValid()) {
          this.map.fitBounds(bounds, { padding: [50, 50] })
        }
      }
    }
  }

  drawRoute() {
    if (!this.map) return

    if (this.routeLayer) {
      this.map.removeLayer(this.routeLayer)
    }

    const points = []
    if (this.state.source) {
      points.push([this.state.source.latitude, this.state.source.longitude])
    }

    this.state.destinations.forEach((d) => points.push([d.latitude, d.longitude]))

    if (points.length > 1) {
      // Draw route line
      this.routeLayer = L.polyline(points, {
        color: "#007bff",
        weight: 4,
        opacity: 0.7,
        dashArray: "10, 5",
      }).addTo(this.map)

      // Calculate total distance
      let distance = 0
      for (let i = 0; i < points.length - 1; i++) {
        distance += haversineDistance(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
      }

      this.state.totalDistance = distance

      // Update record if distance changed
      if (Math.abs(this.props.record.data.total_distance_km - distance) > 0.01) {
        this.props.record.update({ total_distance_km: distance })
      }
    } else {
      this.state.totalDistance = 0
      if (this.props.record.data.total_distance_km !== 0) {
        this.props.record.update({ total_distance_km: 0 })
      }
    }
  }
}

MissionMapPlannerWidget.template = "transport_management.MissionMapPlannerWidget"

// Register as a field widget, not view widget
registry.category("fields").add("mission_map_planner", MissionMapPlannerWidget)

