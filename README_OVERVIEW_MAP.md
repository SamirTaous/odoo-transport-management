# Transport Mission Overview Map

## Overview
The Mission Overview Map provides a comprehensive visual representation of all confirmed and in-progress transport missions. This feature gives dispatchers and managers a real-time view of active operations across their fleet.

## Features

### 🗺️ Interactive Map Display
- **Real-time Mission Visualization**: Shows all confirmed and in-progress missions on an interactive map
- **Route Rendering**: Displays actual driving routes between source and destination points using OSRM routing
- **Mission Type Differentiation**: Visual distinction between pickup and delivery missions
- **Status Indicators**: Clear visual indicators for mission states (confirmed vs in-progress)

### 📊 Mission Status Overview
- **Live Statistics**: Real-time counts of confirmed, in-progress, and total active missions
- **Auto-refresh**: Automatically updates every 30 seconds to show latest mission status
- **Last Update Timestamp**: Shows when data was last refreshed

### 🎯 Smart Markers
- **Source Markers**: Distinctive markers for mission starting points with mission names
- **Destination Markers**: Numbered sequence markers showing delivery/pickup order
- **Completion Status**: Visual indicators showing completed vs pending destinations
- **Interactive Popups**: Detailed mission information on marker click

### 📋 Mission Sidebar
- **Mission Cards**: Compact cards showing key mission details
- **Progress Tracking**: Visual progress bars showing completion percentage
- **Quick Details**: Driver, vehicle, distance, and destination count at a glance
- **Status Color Coding**: Color-coded borders based on mission state

### 🎨 Visual Legend
- **Mission Types**: Clear legend showing pickup vs delivery marker meanings
- **Status Indicators**: Legend explaining confirmed (dashed) vs in-progress (solid) routes
- **Completion States**: Visual guide for completed vs pending destinations

## Access Points

### 1. Main Menu
Navigate to: **Transport → Overview Map**

### 2. Kanban View Button
From the missions kanban view, click the **"Overview Map"** button in the control panel

### 3. Direct URL
Access directly via the client action: `transport_mission_overview_map`

## Technical Details

### Data Filtering
- Only shows missions with state: `confirmed` or `in_progress`
- Automatically excludes draft, done, and cancelled missions
- Requires missions to have valid source coordinates

### Route Calculation
- Uses OSRM (Open Source Routing Machine) for accurate driving routes
- Falls back to straight-line connections if routing service unavailable
- Respects destination sequence for multi-stop missions

### Performance
- Efficient data loading with minimal database queries
- Client-side route caching to reduce API calls
- Responsive design that works on various screen sizes

### Auto-refresh
- Updates mission data every 30 seconds
- Shows loading indicators during refresh
- Preserves map zoom and position during updates

## Mission States Displayed

### Confirmed Missions
- **Visual**: Dashed route lines
- **Color**: Blue for pickup, Green for delivery
- **Meaning**: Mission approved but not yet started

### In-Progress Missions
- **Visual**: Solid route lines with pulsing source markers
- **Color**: Same as confirmed but with full opacity
- **Meaning**: Mission actively being executed

## Marker Types

### Source Markers
- **Pickup**: 🏭 Factory/warehouse icon
- **Delivery**: 📦 Package icon
- **Label**: Shows mission reference number

### Destination Markers
- **Pickup**: 📤 Upload icon with sequence number
- **Delivery**: 📥 Download icon with sequence number
- **Status**: ✅ checkmark overlay for completed destinations

## Use Cases

### Dispatch Management
- Monitor all active missions at a glance
- Identify potential route conflicts or optimizations
- Track mission progress in real-time

### Fleet Coordination
- Visualize fleet distribution across service area
- Plan new missions based on current fleet positions
- Coordinate emergency responses or route changes

### Customer Service
- Provide accurate delivery estimates based on current positions
- Quickly locate missions for customer inquiries
- Monitor service area coverage

## Browser Compatibility
- Modern browsers with JavaScript enabled
- Leaflet.js map library support required
- Responsive design for desktop and tablet use

## Demo Data
The module includes demo data with sample missions across France to demonstrate the overview map functionality. This can be enabled by installing the module with demo data.