# Transport Management for Odoo 16

![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)
![Odoo Version: 16.0](https://img.shields.io/badge/Odoo-16.0-blueviolet.svg)
![Version: 16.0.2.0.0](https://img.shields.io/badge/Version-16.0.2.0.0-green.svg)

A comprehensive Odoo module for managing transport operations with advanced features including AI-powered route optimization, interactive map planning, and real-time mission tracking.

## Key Features

### 🗺️ Interactive Mission Planning
-   **Visual Map Interface:** Drag-and-drop mission planning with interactive Leaflet maps
-   **Real-time Route Calculation:** Automatic route optimization using OSRM routing service
-   **Multi-destination Support:** Handle complex routes with multiple ordered stops
-   **Geocoding Integration:** Automatic address resolution for coordinates

### 🤖 AI-Powered Optimization
-   **Route Optimization:** Google Gemini AI integration for intelligent route planning
-   **Performance Caching:** Smart route caching system for improved performance
-   **Fallback Routes:** Automatic fallback to straight-line routes when needed

### 📊 Mission Management
-   **Complete Lifecycle:** `Draft` → `Confirmed` → `In Progress` → `Done` workflow
-   **Progress Tracking:** Real-time destination completion tracking
-   **Priority Management:** Low, Normal, High priority levels
-   **Mission Types:** Support for both pickup and delivery missions

### 🚛 Fleet Integration
-   **Vehicle Management:** Enhanced vehicle tracking with mission statistics
-   **Driver Assignment:** Link missions to drivers and vehicles
-   **Mission History:** Complete mission history per vehicle

### 📈 Real-time Overview
-   **Live Mission Map:** Real-time overview of all active missions
-   **Status Monitoring:** Visual indicators for mission states
-   **Auto-refresh:** Automatic updates every 30 seconds

## Models

This module introduces two new models to the Odoo database:

### 1. Transport Mission (`transport.mission`)

This is the main model that represents a single transport job.
-   `name`: The unique reference (e.g., TM/00001).
-   `mission_date`: The date of the mission.
-   `driver_id`: A many-to-one link to a Partner (Driver).
-   `vehicle_id`: A many-to-one link to a Vehicle.
-   `destination_ids`: A one-to-many link to the `transport.destination` model.
-   `state`: The current status of the mission.

### 2. Transport Destination (`transport.destination`)

This model holds the details for each stop in a mission.
-   `mission_id`: A many-to-one link back to the parent mission.
-   `location`: A text field for the destination address or point.
-   `sequence`: An integer to define the order of the stops.

## Technical Details

-   **Dependencies:** This module depends on the following official Odoo apps:
    -   `base`: The core Odoo framework.
    -   `fleet`: For vehicle management (`fleet.vehicle` model).
    -   `mail`: For the chatter and activity features (`mail.thread` and `mail.activity.mixin`).
-   **Sequencing:** It uses an `ir.sequence` record to automatically generate mission reference numbers upon creation.

## Installation

1.  Place this module's folder (or a symbolic link to it) inside your Odoo `custom_addons` directory.
2.  Restart the Odoo server service.
3.  In the Odoo UI, navigate to the **Apps** menu.
4.  Click **Update Apps List** (Developer Mode may need to be activated).
5.  Search for "Transport Management" and click **Install**.

## Quick Start

1.  After installation, navigate to **Transport** in the main Odoo menu
2.  Go to **Transport** → **Missions** to view all missions
3.  Click **New** to create a mission with the interactive map planner
4.  Use **Transport** → **Overview Map** for real-time mission monitoring

### Creating Your First Mission
1. Click the map to set your source location
2. Right-click to add destination points
3. Drag markers to adjust positions
4. Use the "Test API Connection" button to optimize routes
5. Confirm and start your mission

## Screenshots

The module includes an interactive map-based mission planner and real-time overview dashboard. See the comprehensive documentation for detailed screenshots and usage examples.

## Documentation

For comprehensive technical documentation, see [COMPREHENSIVE_DOCUMENTATION.md](COMPREHENSIVE_DOCUMENTATION.md).

## Future Development (Planned Features)

-   [ ] Calculate total distance for a mission.
-   [ ] Manage and track mission-related costs (fuel, tolls, etc.).
-   [ ] Generate and print a "Mission Work Order" PDF report.
-   [ ] Integration with Odoo's Calendar app to show driver schedules.
-   [ ] A dashboard for mission analytics (missions per month, costs vs. time, etc.).

---

**Author:** Samir Taous
