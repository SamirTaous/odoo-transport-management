# Transport Management Module - Technical Documentation

> **Note**: This is the complete technical documentation for developers and system administrators. For a quick overview and getting started guide, see the main [README.md](readme.md).

## Table of Contents
1. [Module Overview](#module-overview)
2. [Architecture & Design](#architecture--design)
3. [Models & Data Structure](#models--data-structure)
4. [Security & Access Control](#security--access-control)
5. [User Interface](#user-interface)
6. [JavaScript Components](#javascript-components)
7. [AI Integration](#ai-integration)
8. [Route Caching System](#route-caching-system)
9. [Configuration & Setup](#configuration--setup)
10. [Demo Data](#demo-data)
11. [API Reference](#api-reference)
12. [Troubleshooting](#troubleshooting)

---

## Module Overview

The Transport Management module is a comprehensive Odoo 16 application designed to manage transport operations, including mission planning, route optimization, and real-time tracking. It provides an intuitive interface for creating and managing transport missions with advanced features like AI-powered route optimization and interactive map planning.

### Key Features
- **Mission Management**: Create, track, and manage transport missions with complete lifecycle support
- **Interactive Map Planning**: Visual mission planning with drag-and-drop markers and real-time route calculation
- **AI Route Optimization**: Intelligent route optimization using Google's Gemini AI
- **Route Caching**: Performance optimization through intelligent route caching
- **Real-time Overview**: Live mission overview map showing all active operations
- **Vehicle Management**: Comprehensive vehicle tracking and assignment
- **Multi-destination Support**: Handle complex routes with multiple stops
- **Status Workflow**: Clear mission lifecycle with proper state management

### Technical Specifications
- **Odoo Version**: 16.0
- **License**: LGPL-3
- **Dependencies**: base, fleet, mail, base_geolocalize
- **External Dependencies**: requests (Python), Leaflet.js (JavaScript)
- **Database Models**: 5 custom models with proper relationships

---

## Architecture & Design

### Module Structure
```
transport_management/
├── __manifest__.py              # Module configuration
├── models/                      # Business logic layer
│   ├── __init__.py
│   ├── transport_mission.py     # Core mission model
│   ├── transport_destination.py # Destination management
│   ├── ai_analyst_service.py    # AI integration service
│   └── route_cache.py          # Route caching system
├── views/                       # User interface definitions
│   ├── actions.xml             # Action definitions
│   ├── menus.xml               # Menu structure
│   ├── transport_mission_views.xml
│   └── route_cache_views.xml
├── security/                    # Access control
│   └── ir.model.access.csv     # Model permissions
├── data/                        # Configuration data
│   ├── sequence_data.xml       # Auto-numbering sequences
│   ├── ir_config_parameter_data.xml
│   └── demo_data.xml           # Sample data
└── static/                      # Frontend assets
    ├── src/js/                 # JavaScript components
    ├── src/xml/                # QWeb templates
    ├── src/scss/               # Stylesheets
    └── lib/                    # Third-party libraries
```

### Design Patterns
- **MVC Architecture**: Clear separation between models, views, and controllers
- **Service Layer**: AI and caching services as separate, reusable components
- **Observer Pattern**: Real-time updates through Odoo's ORM change tracking
- **Strategy Pattern**: Multiple route calculation strategies (OSRM, fallback)
- **Cache-Aside Pattern**: Intelligent route caching for performance optimization

---

## Models & Data Structure

### 1. Transport Mission (`transport.mission`)

The core model representing a transport job.

#### Fields
```python
# Basic Information
name = fields.Char()                    # Auto-generated reference (TM/00001)
mission_type = fields.Selection()       # 'pickup' or 'delivery'
mission_date = fields.Date()            # Scheduled date
state = fields.Selection()              # Workflow status
priority = fields.Selection()           # 0=Low, 1=Normal, 2=High

# Location Data
source_location = fields.Char()         # Human-readable address
source_latitude = fields.Float()        # GPS coordinates
source_longitude = fields.Float()       # GPS coordinates

# Relationships
driver_id = fields.Many2one('res.partner')      # Assigned driver
vehicle_id = fields.Many2one('truck.vehicle') # Assigned vehicle (from truck_maintenance module)
destination_ids = fields.One2many()     # List of destinations

# Computed Fields
destination_progress = fields.Float()    # Completion percentage
total_distance_km = fields.Float()      # Calculated route distance

# Metadata
company_id = fields.Many2one('res.company')
notes = fields.Text()                   # Internal notes
```

#### State Workflow
```
Draft → Confirmed → In Progress → Done
  ↓         ↓           ↓
Cancelled ← ← ← ← ← ← ← ←
  ↓
Reset to Draft
```

#### Key Methods
- `action_confirm()`: Move to confirmed state
- `action_start_mission()`: Start mission execution
- `action_done()`: Mark mission as completed
- `action_optimize_route()`: AI-powered route optimization
- `get_cached_route_data()`: Retrieve cached route information

### 2. Transport Destination (`transport.destination`)

Represents individual stops within a mission.

#### Fields
```python
mission_id = fields.Many2one('transport.mission')  # Parent mission
sequence = fields.Integer()                         # Stop order
location = fields.Char()                           # Address
latitude = fields.Float()                          # GPS coordinates
longitude = fields.Float()                         # GPS coordinates
is_completed = fields.Boolean()                    # Completion status
```

### 3. Vehicle Integration

Vehicle management has been moved to the separate `truck_maintenance` module. Transport missions now reference `truck.vehicle` for vehicle assignments.

#### Fields
```python
name = fields.Char()                    # Auto-generated reference
model_id = fields.Many2one('fleet.vehicle.model')
license_plate = fields.Char()
driver_id = fields.Many2one('res.partner')
fuel_capacity = fields.Float()
mission_ids = fields.One2many()         # Related missions
mission_count = fields.Integer()        # Computed mission count
image = fields.Image()                  # Vehicle photo
active = fields.Boolean()               # Active status
```

### 4. Route Cache (`transport.route.cache`)

Performance optimization through intelligent route caching.

#### Fields
```python
route_hash = fields.Char()              # Unique route identifier
waypoints = fields.Text()               # JSON waypoint data
route_geometry = fields.Text()          # OSRM polyline or fallback
route_distance = fields.Float()         # Distance in kilometers
route_duration = fields.Float()         # Duration in minutes
osrm_response = fields.Text()           # Full API response
is_fallback = fields.Boolean()          # Fallback route flag
use_count = fields.Integer()            # Usage statistics
last_used = fields.Datetime()           # Last access time
```

### 5. AI Analyst Service (`ai_analyst_service.AiAnalystService`)

Service class for AI-powered route optimization.

#### Key Methods
- `optimize_route(mission_payload)`: Main optimization function
- `_get_api_key()`: Secure API key retrieval
- Internal prompt engineering for optimal AI responses

---

## Security & Access Control

### Access Rights Matrix

| Model | Group | Read | Write | Create | Delete |
|-------|-------|------|-------|--------|--------|
| transport.mission | base.group_user | ✓ | ✓ | ✓ | ✓ |
| transport.destination | base.group_user | ✓ | ✓ | ✓ | ✓ |
| transport.route.cache | base.group_user | ✓ | ✓ | ✓ | ✗ |
| transport.route.cache | base.group_system | ✓ | ✓ | ✓ | ✓ |

**Note**: Vehicle management (`truck.vehicle`) is now handled by the separate `truck_maintenance` module.

### Security Features
- **Role-based Access**: Different permissions for users vs administrators
- **Company Isolation**: Multi-company support with proper data isolation
- **API Key Security**: Secure storage of AI service credentials
- **Input Validation**: Comprehensive validation of user inputs
- **SQL Injection Protection**: Proper ORM usage throughout

---

## User Interface

### Menu Structure
```
Transport (Main Menu)
├── Missions                    # Mission management
├── Overview Map               # Real-time mission overview
├── Vehicles                   # Vehicle management
└── Configuration
    ├── Route Cache           # Cache management
    ├── Cache Statistics      # Performance metrics
    └── Cleanup Old Routes    # Maintenance tools
```

### View Types

#### 1. Mission Views
- **Kanban View**: Card-based mission overview with status indicators
- **Tree View**: Tabular mission list with sorting and filtering
- **Form View**: Interactive map-based mission planner
- **Search View**: Advanced filtering and grouping options

#### 2. Vehicle Views
- **Kanban View**: Visual vehicle cards with photos
- **Tree View**: Detailed vehicle listing
- **Form View**: Complete vehicle information with mission statistics

#### 3. Route Cache Views
- **Tree View**: Cache entry management
- **Form View**: Detailed cache inspection
- **Search View**: Cache filtering and analysis

### Interactive Features
- **Drag & Drop**: Move markers on map to update locations
- **Right-click Context**: Add destinations via right-click
- **Real-time Updates**: Live route calculation and distance updates
- **Status Workflow**: Visual status bar with action buttons
- **Smart Buttons**: Quick access to related records

---

## JavaScript Components

### 1. Mission Map Planner Widget (`mission_map_planner_widget.js`)

The core interactive mapping component for mission planning.

#### Key Features
- **Leaflet Integration**: Full-featured mapping with OpenStreetMap
- **Marker Management**: Draggable source and destination markers
- **Route Visualization**: Real-time route drawing with OSRM integration
- **Geocoding**: Automatic address resolution for coordinates
- **State Synchronization**: Bidirectional sync with Odoo records

#### Component Lifecycle
```javascript
setup() → onMounted() → initializeMap() → updateMarkers() → drawRoute()
```

#### Key Methods
- `initializeMap()`: Initialize Leaflet map with event handlers
- `updateMarkers()`: Sync visual markers with data state
- `drawRoute()`: Calculate and display optimal routes
- `setSourceLocation()`: Handle source location updates
- `addDestination()`: Add new destination points
- `optimizeRoute()`: Trigger AI route optimization

### 2. Mission Overview Simple (`mission_overview_simple.js`)

Real-time mission overview dashboard.

#### Features
- **Live Updates**: Auto-refresh every 30 seconds
- **Mission Filtering**: Show only active missions
- **Route Rendering**: Display all mission routes simultaneously
- **Status Indicators**: Visual mission state representation
- **Performance Optimization**: Efficient data loading and rendering

---

## AI Integration

### Google Gemini Integration

The module integrates with Google's Gemini AI for intelligent route optimization.

#### Configuration
```xml
<!-- System Parameter -->
<record id="gemini_api_key" model="ir.config_parameter">
    <field name="key">transport_management.gemini_api_key</field>
    <field name="value">YOUR_API_KEY_HERE</field>
</record>
```

#### Prompt Engineering
The AI service uses carefully crafted prompts to ensure consistent, reliable responses:

```python
PROMPT_TEMPLATE = """
You are a high-performance Logistics Optimization API...
[Detailed prompt engineering for optimal results]
"""
```

#### Request/Response Flow
1. **Input Validation**: Verify mission has sufficient destinations
2. **Payload Construction**: Format mission data for AI consumption
3. **API Call**: Secure request to Google AI Studio
4. **Response Parsing**: Extract optimized sequence from JSON response
5. **Database Update**: Apply optimization results to mission

#### Error Handling
- **API Failures**: Graceful degradation with user feedback
- **Invalid Responses**: Comprehensive validation and error reporting
- **Rate Limiting**: Proper handling of API quotas and limits

---

## Route Caching System

### Performance Optimization

The route caching system dramatically improves performance by storing calculated routes.

#### Cache Strategy
- **Hash-based Keys**: Unique identifiers for route combinations
- **Dual Storage**: Both OSRM and fallback routes cached
- **Usage Tracking**: Statistics for cache effectiveness
- **Automatic Cleanup**: Configurable cache expiration

#### Cache Hit Benefits
- **Reduced API Calls**: Minimize external service dependencies
- **Faster Load Times**: Instant route display for cached routes
- **Offline Capability**: Fallback routes work without internet
- **Cost Savings**: Reduced API usage costs

#### Management Tools
- **Statistics Dashboard**: Cache performance metrics
- **Manual Cleanup**: Administrative cache management
- **Automatic Expiration**: Configurable cache lifetime

---

## Configuration & Setup

### Installation Requirements

#### System Dependencies
```bash
# Python packages
pip install requests

# JavaScript libraries (included)
- Leaflet.js 1.9.x
- OpenStreetMap tiles
```

#### Odoo Dependencies
- base (core framework)
- fleet (vehicle management)
- mail (messaging and activities)
- base_geolocalize (geolocation services)

### Configuration Steps

1. **Install Module**
   ```bash
   # Place module in custom_addons directory
   # Restart Odoo server
   # Install via Apps menu
   ```

2. **Configure AI Service**
   ```python
   # Set system parameter
   transport_management.gemini_api_key = "your_api_key_here"
   ```

3. **Set OSRM URL** (optional)
   ```python
   # Default: http://router.project-osrm.org/route/v1/driving/
   transport_management.osrm_route_url = "your_osrm_server"
   ```

### Environment Variables
```bash
# Optional: Custom OSRM server
OSRM_SERVER_URL=http://your-osrm-server.com

# Optional: Custom tile server
TILE_SERVER_URL=https://your-tiles.com/{z}/{x}/{y}.png
```

---

## Demo Data

### Sample Missions

The module includes comprehensive demo data for testing and demonstration:

#### Mission Types
- **Pickup Missions**: Industrial equipment collection
- **Delivery Missions**: Multi-stop delivery routes
- **Mixed Priorities**: Low, normal, and high priority examples
- **Various States**: Draft, confirmed, in-progress, and completed missions

#### Geographic Coverage
- **France-wide**: Missions across major French cities
- **Realistic Routes**: Paris, Lyon, Marseille, Toulouse, Bordeaux
- **Distance Variety**: Short local routes to long-distance missions
- **Completion States**: Mix of completed and pending destinations

#### Data Structure
```xml
<!-- Example mission -->
<record id="demo_mission_pickup_1" model="transport.mission">
    <field name="name">PICKUP-001</field>
    <field name="mission_type">pickup</field>
    <field name="state">confirmed</field>
    <field name="source_location">Paris, France</field>
    <field name="source_latitude">48.8566</field>
    <field name="source_longitude">2.3522</field>
</record>
```

---

## API Reference

### Model Methods

#### Transport Mission
```python
# State Management
mission.action_confirm()           # Confirm mission
mission.action_start_mission()     # Start execution
mission.action_done()             # Mark complete
mission.action_cancel()           # Cancel mission
mission.action_reset_to_draft()   # Reset to draft

# Route Operations
mission.action_optimize_route()    # AI optimization
mission.get_cached_route_data()   # Get cached route
mission.action_open_overview_map() # Open overview

# Utility Methods
mission._compute_total_distance()  # Calculate distance
mission._compute_destination_progress() # Calculate progress
```

#### Route Cache
```python
# Cache Management
cache.get_cached_route(waypoints)     # Retrieve cached route
cache.cache_route(waypoints, data)    # Store route data
cache.cleanup_old_cache(days)         # Clean old entries
cache.get_cache_stats()               # Performance statistics
```

### JavaScript API

#### Map Widget
```javascript
// Core Methods
widget.initializeMap()              // Initialize Leaflet map
widget.updateMarkers()              // Sync visual markers
widget.drawRoute()                  // Calculate and draw route
widget.setSourceLocation(lat, lng)  # Set source coordinates
widget.addDestination(lat, lng)     # Add destination point
widget.optimizeRoute()              # Trigger AI optimization

// Event Handlers
widget.onMissionTypeChange(event)   # Handle type changes
widget.onMissionDateChange(event)   # Handle date changes
widget.onPriorityChange(event)      # Handle priority changes
```

### REST API Endpoints

#### Mission Data
```http
GET /web/dataset/call_kw/transport.mission/search_read
POST /web/dataset/call_kw/transport.mission/create
PUT /web/dataset/call_kw/transport.mission/write
DELETE /web/dataset/call_kw/transport.mission/unlink
```

#### Route Optimization
```http
POST /web/dataset/call_kw/transport.mission/action_optimize_route
```

---

## Troubleshooting

### Common Issues

#### 1. Map Not Loading
**Symptoms**: Blank map area, JavaScript errors
**Solutions**:
- Verify Leaflet.js is loaded correctly
- Check browser console for JavaScript errors
- Ensure OpenStreetMap tiles are accessible
- Verify internet connectivity

#### 2. Route Calculation Failures
**Symptoms**: Straight lines instead of roads, error messages
**Solutions**:
- Check OSRM service availability
- Verify coordinate validity (latitude/longitude ranges)
- Review network connectivity
- Check route cache for corrupted entries

#### 3. AI Optimization Not Working
**Symptoms**: "API not configured" errors, optimization failures
**Solutions**:
- Verify Gemini API key is set correctly
- Check API key permissions and quotas
- Review system parameters configuration
- Test API connectivity manually

#### 4. Performance Issues
**Symptoms**: Slow loading, timeout errors
**Solutions**:
- Enable route caching
- Clean old cache entries
- Optimize database indexes
- Review server resources

### Debug Mode

Enable debug logging for detailed troubleshooting:

```python
# In odoo.conf
log_level = debug
log_handler = :DEBUG

# Or via environment
ODOO_LOG_LEVEL=debug
```

### Log Analysis

Key log patterns to monitor:

```bash
# Route calculation
grep "OSRM route calculation" odoo.log

# AI optimization
grep "Google AI Studio API" odoo.log

# Cache operations
grep "Route cache" odoo.log

# JavaScript errors
grep "mission_map_planner" odoo.log
```

### Performance Monitoring

#### Database Queries
```sql
-- Monitor mission queries
SELECT * FROM transport_mission WHERE state IN ('confirmed', 'in_progress');

-- Cache effectiveness
SELECT COUNT(*), is_fallback FROM transport_route_cache GROUP BY is_fallback;

-- Usage statistics
SELECT AVG(use_count), MAX(use_count) FROM transport_route_cache;
```

#### JavaScript Performance
```javascript
// Monitor widget initialization time
console.time('map-init');
// ... initialization code ...
console.timeEnd('map-init');

// Track route calculation performance
console.time('route-calc');
// ... route calculation ...
console.timeEnd('route-calc');
```

---

## Conclusion

The Transport Management module provides a comprehensive solution for managing transport operations in Odoo 16. With its advanced features like AI-powered optimization, interactive mapping, and intelligent caching, it offers both powerful functionality and excellent performance.

The modular architecture ensures easy maintenance and extensibility, while the comprehensive documentation and demo data facilitate quick adoption and customization.

For additional support or customization requests, please refer to the module's issue tracker or contact the development team.

---

**Version**: 16.0.2.0.0  
**Author**: Samir Taous  
**License**: LGPL-3  
**Last Updated**: 2024