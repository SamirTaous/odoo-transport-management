"use client"

/** @odoo-module **/
import { registry } from "@web/core/registry"
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl"
const { L } = window // Access Leaflet from global scope

export class MissionMapPlannerWidget extends Component {
  setup() {
    this.mapRef = useRef("map")
    this.map = null
    this.sourceMarker = null
    this.destinationMarkers = []
    this.routeLayer = null

    this.state = useState({
      sourceLocation: "",
      destinations: [],
      totalDistance: 0,
    })

    // All hooks must be called in the exact same order in every component render
    onMounted(() => {
      setTimeout(this.initializeMap.bind(this), 100)
    })

    onWillUnmount(() => {
      if (this.map) {
        this.map.remove()
        this.map = null
      }
    })
  }

  initializeMap() {
    if (this.map || !this.mapRef.el) return

    // Check if Leaflet is available
    if (typeof L === "undefined") {
      console.error("Leaflet library not found. Please include Leaflet CSS and JS files.")
      return
    }

    // Initialize map centered on UK
    this.map = L.map(this.mapRef.el, {
      zoomControl: true,
      scrollWheelZoom: true,
    }).setView([54.5, -2.0], 6)

    // Add tile layer
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(this.map)

    // Add custom controls
    this.addMapControls()

    // Set up event handlers
    this.setupMapEvents()

    // Load existing data if available
    this.loadExistingData()
  }

  addMapControls() {
    // Custom control for map legend
    const legendControl = L.control({ position: "topright" })
    legendControl.onAdd = () => {
      const div = L.DomUtil.create("div", "tm-map-legend")
      div.innerHTML = `
                <div class="tm-legend-item">
                    <i class="fa fa-map-marker-alt" style="color: #007bff;"></i>
                    <span>Source</span>
                </div>
                <div class="tm-legend-item">
                    <i class="fa fa-map-marker-alt" style="color: #dc3545;"></i>
                    <span>Destinations</span>
                </div>
            `
      return div
    }
    legendControl.addTo(this.map)
  }

  setupMapEvents() {
    // Left click to set source
    this.map.on("click", (e) => {
      this.setSourceLocation(e.latlng.lat, e.latlng.lng)
    })

    // Right click to add destination
    this.map.on("contextmenu", (e) => {
      e.originalEvent.preventDefault()
      this.addDestination(e.latlng.lat, e.latlng.lng)
    })

    // Set up control button events using event delegation
    setTimeout(() => {
      const clearBtn = document.getElementById("clear_all_markers")
      const optimizeBtn = document.getElementById("optimize_route")

      if (clearBtn) {
        clearBtn.addEventListener("click", () => this.clearAllMarkers())
      }
      if (optimizeBtn) {
        optimizeBtn.addEventListener("click", () => this.optimizeRoute())
      }
    }, 500)
  }

  async setSourceLocation(lat, lng) {
    // Remove existing source marker
    if (this.sourceMarker) {
      this.map.removeLayer(this.sourceMarker)
    }

    // Create new source marker (blue)
    this.sourceMarker = L.marker([lat, lng], {
      draggable: true,
      icon: L.divIcon({
        className: "tm-source-marker",
        html: '<i class="fa fa-map-marker-alt" style="color: #007bff; font-size: 24px;"></i>',
        iconSize: [24, 24],
        iconAnchor: [12, 24],
      }),
    }).addTo(this.map)

    // Handle marker drag
    this.sourceMarker.on("dragend", (e) => {
      const latLng = e.target.getLatLng()
      this.setSourceLocation(latLng.lat, latLng.lng)
    })

    // Get address and update form
    const address = await this.reverseGeocode(lat, lng)
    this.state.sourceLocation = address

    // Update form fields
    this.updateSourceDisplay(address, lat, lng)
    this.updateFormData()
    this.calculateRoute()
  }

  async addDestination(lat, lng) {
    const destinationIndex = this.destinationMarkers.length + 1

    // Create destination marker (red)
    const marker = L.marker([lat, lng], {
      draggable: true,
      icon: L.divIcon({
        className: "tm-destination-marker",
        html: `<div class="tm-marker-number">${destinationIndex}</div>`,
        iconSize: [30, 30],
        iconAnchor: [15, 30],
      }),
    }).addTo(this.map)

    // Handle marker drag
    marker.on("dragend", (e) => {
      const latLng = e.target.getLatLng()
      const index = this.destinationMarkers.indexOf(marker)
      this.updateDestination(index, latLng.lat, latLng.lng)
    })

    // Get address
    const address = await this.reverseGeocode(lat, lng)

    // Add to destinations array
    const destination = {
      sequence: destinationIndex,
      location: address,
      latitude: lat,
      longitude: lng,
      marker: marker,
      is_completed: false,
    }

    this.destinationMarkers.push(marker)
    this.state.destinations.push(destination)

    this.updateDestinationsDisplay()
    this.updateFormData()
    this.calculateRoute()
  }

  async updateDestination(index, lat, lng) {
    if (index >= 0 && index < this.state.destinations.length) {
      const address = await this.reverseGeocode(lat, lng)
      this.state.destinations[index].location = address
      this.state.destinations[index].latitude = lat
      this.state.destinations[index].longitude = lng

      this.updateDestinationsDisplay()
      this.updateFormData()
      this.calculateRoute()
    }
  }

  removeDestination(index) {
    if (index >= 0 && index < this.state.destinations.length) {
      // Remove marker from map
      this.map.removeLayer(this.destinationMarkers[index])

      // Remove from arrays
      this.destinationMarkers.splice(index, 1)
      this.state.destinations.splice(index, 1)

      // Renumber remaining destinations
      this.renumberDestinations()

      this.updateDestinationsDisplay()
      this.updateFormData()
      this.calculateRoute()
    }
  }

  renumberDestinations() {
    this.state.destinations.forEach((dest, index) => {
      dest.sequence = index + 1
      // Update marker number
      const markerElement = dest.marker.getElement()
      if (markerElement) {
        const numberEl = markerElement.querySelector(".tm-marker-number")
        if (numberEl) {
          numberEl.textContent = index + 1
        }
      }
    })
  }

  clearAllMarkers() {
    // Remove source marker
    if (this.sourceMarker) {
      this.map.removeLayer(this.sourceMarker)
      this.sourceMarker = null
    }

    // Remove all destination markers
    this.destinationMarkers.forEach((marker) => {
      this.map.removeLayer(marker)
    })

    // Clear route
    if (this.routeLayer) {
      this.map.removeLayer(this.routeLayer)
      this.routeLayer = null
    }

    // Reset state
    this.destinationMarkers = []
    this.state.sourceLocation = ""
    this.state.destinations = []
    this.state.totalDistance = 0

    // Update displays
    this.updateSourceDisplay("", 0, 0)
    this.updateDestinationsDisplay()
    this.updateFormData()
  }

  optimizeRoute() {
    if (this.state.destinations.length < 2) return

    // Simple optimization: sort by distance from source
    if (this.sourceMarker) {
      const sourceLatLng = this.sourceMarker.getLatLng()

      this.state.destinations.sort((a, b) => {
        const distA = this.calculateDistance(sourceLatLng.lat, sourceLatLng.lng, a.latitude, a.longitude)
        const distB = this.calculateDistance(sourceLatLng.lat, sourceLatLng.lng, b.latitude, b.longitude)
        return distA - distB
      })

      this.renumberDestinations()
      this.updateDestinationsDisplay()
      this.updateFormData()
      this.calculateRoute()
    }
  }

  async calculateRoute() {
    if (this.routeLayer) {
      this.map.removeLayer(this.routeLayer)
    }

    if (!this.sourceMarker || this.state.destinations.length === 0) {
      this.state.totalDistance = 0
      this.updateDistanceDisplay()
      return
    }

    // Create route line
    const waypoints = [this.sourceMarker.getLatLng()]
    this.state.destinations.forEach((dest) => {
      waypoints.push(L.latLng(dest.latitude, dest.longitude))
    })

    this.routeLayer = L.polyline(waypoints, {
      color: "#007bff",
      weight: 4,
      opacity: 0.7,
      dashArray: "10, 5",
    }).addTo(this.map)

    // Calculate total distance
    let totalDistance = 0
    for (let i = 0; i < waypoints.length - 1; i++) {
      totalDistance += this.calculateDistance(
        waypoints[i].lat,
        waypoints[i].lng,
        waypoints[i + 1].lat,
        waypoints[i + 1].lng,
      )
    }

    this.state.totalDistance = totalDistance
    this.updateDistanceDisplay()
  }

  calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371 // Earth's radius in km
    const dLat = ((lat2 - lat1) * Math.PI) / 180
    const dLon = ((lon2 - lon1) * Math.PI) / 180
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2)
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
    return R * c
  }

  async reverseGeocode(lat, lng) {
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`)
      const data = await response.json()
      return data.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`
    } catch (error) {
      console.error("Geocoding failed:", error)
      return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
    }
  }

  updateSourceDisplay(address, lat, lng) {
    setTimeout(() => {
      const sourceDisplay = document.getElementById("source_display")
      const addressEl = document.getElementById("source_address")
      const coordsEl = document.getElementById("source_coords")

      if (addressEl && coordsEl) {
        if (address) {
          addressEl.textContent = address
          coordsEl.textContent = `${lat.toFixed(4)}, ${lng.toFixed(4)}`
          if (sourceDisplay) {
            sourceDisplay.classList.add("tm-location-set")
          }
        } else {
          addressEl.textContent = "Click on map to set source location"
          coordsEl.textContent = ""
          if (sourceDisplay) {
            sourceDisplay.classList.remove("tm-location-set")
          }
        }
      }
    }, 100)
  }

  updateDestinationsDisplay() {
    setTimeout(() => {
      const container = document.getElementById("destinations_display")
      const countBadge = document.getElementById("destination_count")

      if (!container || !countBadge) return

      countBadge.textContent = this.state.destinations.length

      if (this.state.destinations.length === 0) {
        container.innerHTML = `
                    <div class="tm_empty_destinations">
                        <i class="fa fa-map-signs fa-2x text-muted"></i>
                        <p>Right-click on map to add destinations</p>
                    </div>
                `
        return
      }

      const destinationsHtml = this.state.destinations
        .map(
          (dest, index) => `
                <div class="tm_location_item tm_destination_item">
                    <div class="tm_destination_number">${dest.sequence}</div>
                    <div class="tm_location_info">
                        <span class="tm_location_address">${dest.location}</span>
                        <small class="tm_location_coords">${dest.latitude.toFixed(4)}, ${dest.longitude.toFixed(4)}</small>
                    </div>
                    <div class="tm_location_actions">
                        <button type="button" class="btn btn-sm btn-outline-danger" data-index="${index}">
                            <i class="fa fa-trash"></i>
                        </button>
                    </div>
                </div>
            `,
        )
        .join("")

      container.innerHTML = destinationsHtml

      // Add event listeners for delete buttons
      container.querySelectorAll(".btn-outline-danger").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const index = Number.parseInt(e.currentTarget.getAttribute("data-index"))
          this.removeDestination(index)
        })
      })
    }, 100)
  }

  updateDistanceDisplay() {
    setTimeout(() => {
      // Update the total distance field in the form
      const distanceField = document.querySelector('input[name="total_distance_km"]')
      if (distanceField) {
        distanceField.value = this.state.totalDistance.toFixed(2)
        // Trigger change event
        distanceField.dispatchEvent(new Event("change"))
      }
    }, 100)
  }

  updateFormData() {
    // Update source location fields
    if (this.props.record) {
      const updates = {}

      if (this.sourceMarker) {
        const latLng = this.sourceMarker.getLatLng()
        updates.source_location = this.state.sourceLocation
        updates.source_latitude = latLng.lat
        updates.source_longitude = latLng.lng
      }

      updates.total_distance_km = this.state.totalDistance

      this.props.record.update(updates)
    }
  }

  loadExistingData() {
    if (!this.props.record) return

    // Load existing source location
    const sourceLocation = this.props.record.data.source_location
    const sourceLat = this.props.record.data.source_latitude
    const sourceLng = this.props.record.data.source_longitude

    if (sourceLat && sourceLng) {
      this.setSourceLocation(sourceLat, sourceLng)
    }

    // Load existing destinations would require additional logic
    // to sync with the destination_ids field
  }
}

MissionMapPlannerWidget.template = "transport_management.MissionMapPlannerWidget"
MissionMapPlannerWidget.supportedTypes = ["char"]

registry.category("fields").add("mission_map_planner", MissionMapPlannerWidget)
