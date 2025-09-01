# In: models/transport_mission.py

# --- Imports are correct ---
import requests
import json
import logging
from . import ai_analyst_service

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from math import radians, sin, cos, sqrt, atan2
import requests
import json

# --- Logger is correct ---
_logger = logging.getLogger(__name__)

# --- Helper function is correct ---
def _haversine_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    r = 6371
    return c * r

class TransportMission(models.Model):
    _name = 'transport.mission'
    _description = 'Transport Mission'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'mission_date desc, priority desc, name desc'

    # --- All fields are correct ---
    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    mission_date = fields.Date(string='Date', required=True, tracking=True, default=fields.Date.context_today)
    source_location = fields.Char(string='Source Location', tracking=True)
    source_latitude = fields.Float(string='Source Latitude', digits=(10, 7))
    source_longitude = fields.Float(string='Source Longitude', digits=(10, 7))
    destination_ids = fields.One2many('transport.destination', 'mission_id', string='Destinations')
    driver_id = fields.Many2one('res.partner', string='Driver', tracking=True, domain=[('is_company', '=', False)])
    vehicle_id = fields.Many2one('truck.vehicle', string='Vehicle', tracking=True, ondelete='set null')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('in_progress', 'In Progress'), ('done', 'Done'), ('cancelled', 'Cancelled')], default='draft', string='Status', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    notes = fields.Text(string='Internal Notes', tracking=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High')
    ], string='Priority', default='1', tracking=True) # Default to Normal
    destination_progress = fields.Float(string="Destination Progress", compute='_compute_destination_progress', store=True, help="Progress of completed destinations for this mission.")
    total_distance_km = fields.Float(string="Total Distance (km)", compute='_compute_total_distance', store=True, help="Estimated total travel distance for the mission.")
    estimated_duration_minutes = fields.Float(string="Estimated Duration (min)", compute='_compute_total_distance', store=True, default=0.0, help="Estimated total travel time for the mission in minutes.")
    distance_calculation_method = fields.Selection([
        ('haversine', 'Haversine (Straight Line)'),
        ('osrm', 'OSRM (Road Distance)'),
        ('cached', 'Cached Route')
    ], string="Distance Calculation Method", default='osrm', help="Method used to calculate the total distance")
    
    # Package summary fields
    total_packages = fields.Integer(string="Total Packages", compute='_compute_package_summary', store=True)
    total_weight = fields.Float(string="Total Weight (kg)", compute='_compute_package_summary', store=True, digits=(8, 2))
    total_volume = fields.Float(string="Total Volume (m³)", compute='_compute_package_summary', store=True, digits=(8, 3))
    starting_weight = fields.Float(string="Starting Weight (kg)", digits=(8, 2), help="Initial weight of the truck before loading any cargo")
    
    # Mission type summary fields
    pickup_count = fields.Integer(string="Pickup Destinations", compute='_compute_mission_type_summary', store=True)
    delivery_count = fields.Integer(string="Delivery Destinations", compute='_compute_mission_type_summary', store=True)
    mission_type_summary = fields.Char(string="Mission Type Summary", compute='_compute_mission_type_summary', store=True)
    
    # Time constraint fields
    earliest_delivery = fields.Datetime(string="Earliest Delivery", compute='_compute_time_constraints', store=True)
    latest_delivery = fields.Datetime(string="Latest Delivery", compute='_compute_time_constraints', store=True)
    has_time_constraints = fields.Boolean(string="Has Time Constraints", compute='_compute_time_constraints', store=True)
    
    # Cost calculation fields
    cost_parameters_id = fields.Many2one('transport.cost.parameters', string='Cost Parameters', 
                                        default=lambda self: self.env['transport.cost.parameters'].get_default_parameters())
    total_cost = fields.Monetary(string="Total Mission Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    base_cost = fields.Monetary(string="Base Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    distance_cost = fields.Monetary(string="Distance Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    time_cost = fields.Monetary(string="Time Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    fuel_cost = fields.Monetary(string="Fuel Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    driver_cost = fields.Monetary(string="Driver Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    vehicle_cost = fields.Monetary(string="Vehicle Cost", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    other_costs = fields.Monetary(string="Other Costs", compute='_compute_mission_cost', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self._get_mad_currency())
    
    def _get_mad_currency(self):
        """Get MAD currency or fallback to company currency"""
        mad_currency = self.env['res.currency'].search([('name', '=', 'MAD')], limit=1)
        return mad_currency if mad_currency else self.env.company.currency_id

    # --- All standard methods are correct ---
    @api.depends('source_latitude', 'source_longitude', 'destination_ids.latitude', 'destination_ids.longitude', 'destination_ids.sequence')
    def _compute_total_distance(self):
        # Skip computation if this is being called from widget update
        if self.env.context.get('widget_update'):
            return
            
        for mission in self:
            # Skip if distance was recently set by widget (method is 'osrm' and distance > 0)
            if (mission.distance_calculation_method == 'osrm' and 
                mission.total_distance_km > 0):
                continue
                
            distance = 0.0
            duration = 0.0
            calculation_method = 'osrm'
            
            if mission.source_latitude and mission.source_longitude:
                # Build waypoints array
                waypoints = [[mission.source_latitude, mission.source_longitude]]
                
                # Add destinations in sequence order
                destinations = mission.destination_ids.filtered(lambda d: d.latitude and d.longitude).sorted('sequence')
                for dest in destinations:
                    waypoints.append([dest.latitude, dest.longitude])
                    
                if len(waypoints) >= 2:
                    # Try to get from cache first
                    route_cache = self.env['transport.route.cache']
                    cached_route = route_cache.get_cached_route(waypoints)
                    
                    if cached_route:
                        distance = cached_route.get('distance', 0.0)
                        duration = cached_route.get('duration', 0.0)
                        # Mark as cached since we got it from cache
                        calculation_method = 'cached'
                    else:
                        # Calculate and cache the route immediately - this is a fresh calculation
                        try:
                            route_data = mission._calculate_and_cache_route(waypoints)
                            if route_data:
                                distance = route_data.get('distance', 0.0)
                                duration = route_data.get('duration', 0.0)
                                # This is a fresh calculation, so mark appropriately
                                if route_data.get('is_fallback'):
                                    calculation_method = 'haversine'
                                else:
                                    calculation_method = 'osrm'
                        except Exception as e:
                            _logger.warning(f"Failed to calculate route for mission {mission.name}: {e}")
                            # Only if OSRM completely fails, leave distance as 0
                            distance = 0.0
                            duration = 0.0
                            calculation_method = 'osrm'
            
            mission.total_distance_km = distance
            mission.estimated_duration_minutes = duration
            mission.distance_calculation_method = calculation_method
            
    @api.depends('destination_ids.is_completed')
    def _compute_destination_progress(self):
        for mission in self:
            total_destinations = len(mission.destination_ids)
            if not total_destinations:
                mission.destination_progress = 0.0
            else:
                completed_count = len(mission.destination_ids.filtered(lambda d: d.is_completed))
                mission.destination_progress = (completed_count / total_destinations) * 100

    @api.depends('destination_ids.total_weight', 'destination_ids.total_volume', 'destination_ids.package_type')
    def _compute_package_summary(self):
        for mission in self:
            # Count destinations as "packages" - could be pallets or individual package groups
            mission.total_packages = len(mission.destination_ids)
            mission.total_weight = sum(mission.destination_ids.mapped('total_weight'))
            mission.total_volume = sum(mission.destination_ids.mapped('total_volume'))

    @api.depends('destination_ids.mission_type')
    def _compute_mission_type_summary(self):
        for mission in self:
            pickup_destinations = mission.destination_ids.filtered(lambda d: d.mission_type == 'pickup')
            delivery_destinations = mission.destination_ids.filtered(lambda d: d.mission_type == 'delivery')
            
            mission.pickup_count = len(pickup_destinations)
            mission.delivery_count = len(delivery_destinations)
            
            # Create a summary string
            summary_parts = []
            if mission.pickup_count > 0:
                summary_parts.append(f"{mission.pickup_count} Pickup{'s' if mission.pickup_count > 1 else ''}")
            if mission.delivery_count > 0:
                summary_parts.append(f"{mission.delivery_count} Deliver{'ies' if mission.delivery_count > 1 else 'y'}")
            
            mission.mission_type_summary = " + ".join(summary_parts) if summary_parts else "No Destinations"

    @api.depends('destination_ids.expected_arrival_time', 'destination_ids.estimated_arrival_time')
    def _compute_time_constraints(self):
        for mission in self:
            destinations_with_times = mission.destination_ids.filtered(lambda d: d.expected_arrival_time or d.estimated_arrival_time)
            
            if destinations_with_times:
                mission.has_time_constraints = True
                
                # Find earliest and latest times (prefer expected over estimated)
                all_times = []
                for dest in destinations_with_times:
                    if dest.expected_arrival_time:
                        all_times.append(dest.expected_arrival_time)
                    elif dest.estimated_arrival_time:
                        all_times.append(dest.estimated_arrival_time)
                
                mission.earliest_delivery = min(all_times) if all_times else False
                mission.latest_delivery = max(all_times) if all_times else False
            else:
                mission.has_time_constraints = False
                mission.earliest_delivery = False
                mission.latest_delivery = False

    @api.depends('total_distance_km', 'estimated_duration_minutes', 'vehicle_id', 'cost_parameters_id')
    def _compute_mission_cost(self):
        for mission in self:
            if not mission.cost_parameters_id:
                mission.cost_parameters_id = self.env['transport.cost.parameters'].get_default_parameters()
            
            params = mission.cost_parameters_id
            distance_km = mission.total_distance_km or 0
            duration_hours = (mission.estimated_duration_minutes or 0) / 60
            
            # Base cost
            mission.base_cost = params.base_mission_cost + params.insurance_cost_per_mission
            
            # Distance-based costs
            mission.distance_cost = distance_km * params.cost_per_km
            
            # Time-based costs
            mission.time_cost = duration_hours * params.cost_per_hour
            
            # Driver costs
            mission.driver_cost = duration_hours * params.driver_cost_per_hour
            
            # Fuel costs (using vehicle-specific consumption if available)
            fuel_consumption_per_100km = 0
            if mission.vehicle_id and mission.vehicle_id.fuel_consumption:
                fuel_consumption_per_100km = mission.vehicle_id.fuel_consumption
            else:
                # Default fuel consumption if no vehicle or no consumption data
                fuel_consumption_per_100km = 25.0  # L/100km default for trucks
            
            fuel_needed = (distance_km / 100) * fuel_consumption_per_100km
            mission.fuel_cost = fuel_needed * params.fuel_price_per_liter
            
            # Vehicle-specific costs (rental cost if applicable)
            mission.vehicle_cost = 0
            if mission.vehicle_id and mission.vehicle_id.ownership_type == 'rented' and mission.vehicle_id.rental_cost_per_day:
                # Calculate rental cost based on mission duration (minimum 1 day)
                days = max(1, duration_hours / 24)
                mission.vehicle_cost = days * mission.vehicle_id.rental_cost_per_day
            
            # Other costs (tolls, maintenance)
            toll_cost = distance_km * params.toll_cost_per_km
            maintenance_cost = distance_km * params.maintenance_cost_per_km
            mission.other_costs = toll_cost + maintenance_cost
            
            # Total cost
            mission.total_cost = (mission.base_cost + mission.distance_cost + mission.time_cost + 
                                mission.fuel_cost + mission.driver_cost + mission.vehicle_cost + mission.other_costs)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.mission.sequence') or _('New')
        missions = super().create(vals_list)
        # Force distance calculation for new missions
        for mission in missions:
            if mission.source_latitude and mission.source_longitude and mission.destination_ids:
                mission._compute_total_distance()
        return missions

    def write(self, vals):
        result = super().write(vals)
        # If coordinates or destinations changed, recalculate distance
        if any(field in vals for field in ['source_latitude', 'source_longitude']):
            for mission in self:
                if mission.source_latitude and mission.source_longitude and mission.destination_ids:
                    mission._compute_total_distance()
        
        # If vehicle or cost parameters changed, recalculate costs
        if any(field in vals for field in ['vehicle_id', 'cost_parameters_id']):
            for mission in self:
                mission._compute_mission_cost()
        
        return result

    def action_confirm(self): self.write({'state': 'confirmed'})
    def action_start_mission(self): self.write({'state': 'in_progress'})
    def action_done(self): self.write({'state': 'done'})
    def action_cancel(self): self.write({'state': 'cancelled'})
    def action_reset_to_draft(self): self.write({'state': 'draft'})

    # --- THIS IS THE FINAL, CORRECTED OPTIMIZATION ACTION ---
    def action_optimize_route(self):
        self.ensure_one()

        if len(self.destination_ids) < 2:
            raise UserError("Optimization requires at least two destinations.")

        destinations_payload = [
            {'id': dest.id, 'lat': dest.latitude, 'lon': dest.longitude}
            for dest in self.destination_ids
        ]
        mission_payload = {
            'mission_id': self.name or f'mission_{self.id}',
            'source': {'lat': self.source_latitude, 'lon': self.source_longitude},
            'destinations': destinations_payload,
        }

        try:
            analyst = ai_analyst_service.AiAnalystService(self.env)
            optimized_data = analyst.optimize_route(mission_payload)
            
            optimized_ids = optimized_data.get('optimized_sequence')
            if not optimized_ids:
                raise UserError("AI response did not contain a valid 'optimized_sequence'.")

            with self.env.cr.savepoint():
                for new_sequence, dest_id in enumerate(optimized_ids, start=1):
                    self.env['transport.destination'].browse(dest_id).write({'sequence': new_sequence})
            
            if optimized_data.get('route_summary'):
                self.write({
                    'total_distance_km': optimized_data['route_summary'].get('total_distance_km', self.total_distance_km)
                })
            
            # Force recalculation of distance after optimization
            self._compute_total_distance()
            
            # --- THIS IS THE NEW, CORRECT WAY TO SHOW A SUCCESS MESSAGE ---
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Success"),
                    'message': _("The route has been optimized successfully."),
                    'type': 'success',
                    'sticky': False,
                }
            }
            # -----------------------------------------------------------------
            
        except UserError as e:
            raise e
        except Exception as e:
            _logger.error(f"An unexpected error occurred during route optimization for mission {self.id}: {e}")
            raise UserError(f"An unexpected error occurred: {e}")

    def action_recalculate_distance(self):
        """Manually recalculate distance using OSRM/cached route data"""
        self.ensure_one()
        old_distance = self.total_distance_km
        
        # Clear any existing cache for this route to force fresh calculation
        if self.source_latitude and self.source_longitude and self.destination_ids:
            waypoints = [[self.source_latitude, self.source_longitude]]
            destinations = self.destination_ids.filtered(lambda d: d.latitude and d.longitude).sorted('sequence')
            for dest in destinations:
                waypoints.append([dest.latitude, dest.longitude])
            
            if len(waypoints) >= 2:
                route_cache = self.env['transport.route.cache']
                route_hash = route_cache.generate_route_hash(waypoints)
                existing_cache = route_cache.search([('route_hash', '=', route_hash)])
                if existing_cache:
                    existing_cache.unlink()
        
        # Force recalculation
        self._compute_total_distance()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Distance Updated"),
                'message': _("Distance updated from %.2f km to %.2f km using %s") % (
                    old_distance, self.total_distance_km, self.distance_calculation_method
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    def update_distance_from_widget(self, distance_km, duration_minutes=0):
        """Update distance and duration from the JavaScript widget with OSRM calculation"""
        self.ensure_one()
        # Set a flag to indicate this was set by widget
        self.with_context(widget_update=True).write({
            'total_distance_km': distance_km,
            'estimated_duration_minutes': duration_minutes,
            'distance_calculation_method': 'osrm'
        })
        return True

    @api.model
    def recalculate_all_distances(self):
        """Recalculate distances for all missions using OSRM/cached data"""
        missions = self.search([('source_latitude', '!=', False), ('source_longitude', '!=', False)])
        updated_count = 0
        
        for mission in missions:
            old_distance = mission.total_distance_km
            mission._compute_total_distance()
            if abs(old_distance - mission.total_distance_km) > 0.01:
                updated_count += 1
                _logger.info(f"Updated distance for mission {mission.name}: {old_distance:.2f} -> {mission.total_distance_km:.2f} km")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Distance Recalculation Complete"),
                'message': _("Updated distances for %d missions") % updated_count,
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def fix_distance_discrepancies(self):
        """Fix missions that have distance calculation method as haversine"""
        missions_to_fix = self.search([
            ('distance_calculation_method', '=', 'haversine'),
            ('source_latitude', '!=', False),
            ('source_longitude', '!=', False)
        ])
        
        fixed_count = 0
        for mission in missions_to_fix:
            old_distance = mission.total_distance_km
            old_method = mission.distance_calculation_method
            
            # Force OSRM calculation
            mission._compute_total_distance()
            
            if mission.distance_calculation_method != 'haversine':
                fixed_count += 1
                _logger.info(f"Fixed mission {mission.name}: {old_distance:.2f} km ({old_method}) -> {mission.total_distance_km:.2f} km ({mission.distance_calculation_method})")
        
        return fixed_count

    @api.model
    def fix_all_distances_now(self):
        """Immediate fix for all missions - can be called from anywhere"""
        missions = self.search([
            ('source_latitude', '!=', False),
            ('source_longitude', '!=', False)
        ])
        
        fixed_count = 0
        for mission in missions:
            try:
                old_distance = mission.total_distance_km
                old_method = getattr(mission, 'distance_calculation_method', 'unknown')
                
                # Clear cache and force recalculation
                if mission.destination_ids:
                    waypoints = [[mission.source_latitude, mission.source_longitude]]
                    destinations = mission.destination_ids.filtered(lambda d: d.latitude and d.longitude).sorted('sequence')
                    for dest in destinations:
                        waypoints.append([dest.latitude, dest.longitude])
                    
                    if len(waypoints) >= 2:
                        route_cache = self.env['transport.route.cache']
                        route_hash = route_cache.generate_route_hash(waypoints)
                        existing_cache = route_cache.search([('route_hash', '=', route_hash)])
                        if existing_cache:
                            existing_cache.unlink()
                
                mission._compute_total_distance()
                
                if abs(old_distance - mission.total_distance_km) > 0.01:
                    fixed_count += 1
                    _logger.info(f"Fixed {mission.name}: {old_distance:.2f} km -> {mission.total_distance_km:.2f} km")
                    
            except Exception as e:
                _logger.error(f"Error fixing mission {mission.name}: {e}")
        
        _logger.info(f"Distance fix complete: {fixed_count} missions updated")
        return fixed_count

    @api.model
    def check_distance_consistency(self):
        """Check for missions with potential distance calculation issues"""
        missions = self.search([
            ('source_latitude', '!=', False),
            ('source_longitude', '!=', False)
        ])
        
        issues = []
        for mission in missions:
            # Check if using haversine method (indicates potential issue)
            if getattr(mission, 'distance_calculation_method', 'haversine') == 'haversine':
                issues.append({
                    'mission': mission.name,
                    'distance': mission.total_distance_km,
                    'method': mission.distance_calculation_method,
                    'issue': 'Using straight-line calculation instead of road distance'
                })
        
        return issues

    def action_open_overview_map(self):
        """Open the mission overview map"""
        return {
            'type': 'ir.actions.client',
            'tag': 'transport_mission_overview_map',
            'name': _('Mission Overview Map'),
        }

    def get_cached_route_data(self):
        """Get cached route data for this mission"""
        self.ensure_one()
        
        if not self.source_latitude or not self.source_longitude:
            return None
            
        # Build waypoints array
        waypoints = [[self.source_latitude, self.source_longitude]]
        
        # Add destinations in sequence order
        destinations = self.destination_ids.filtered(lambda d: d.latitude and d.longitude).sorted('sequence')
        for dest in destinations:
            waypoints.append([dest.latitude, dest.longitude])
            
        if len(waypoints) < 2:
            return None
            
        # Try to get from cache first
        route_cache = self.env['transport.route.cache']
        cached_route = route_cache.get_cached_route(waypoints)
        
        if cached_route:
            return cached_route
            
        # If not cached, calculate and cache the route
        return self._calculate_and_cache_route(waypoints)
    
    def _calculate_and_cache_route(self, waypoints):
        """Calculate route using OSRM and cache the result"""
        route_cache = self.env['transport.route.cache']
        
        try:
            # Prepare OSRM request
            coordinates = []
            for waypoint in waypoints:
                coordinates.append(f"{waypoint[1]},{waypoint[0]}")  # OSRM expects lon,lat
            
            coordinates_str = ';'.join(coordinates)
            osrm_url = f"https://router.project-osrm.org/route/v1/driving/{coordinates_str}?overview=full&geometries=polyline"
            
            response = requests.get(osrm_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('code') == 'Ok' and data.get('routes'):
                    # Cache successful OSRM response
                    route_cache.cache_route(waypoints, osrm_response=data)
                    
                    route = data['routes'][0]
                    return {
                        'geometry': route.get('geometry', ''),
                        'distance': route.get('distance', 0) / 1000,  # Convert to km
                        'duration': route.get('duration', 0) / 60,    # Convert to minutes
                        'is_fallback': False,
                        'cached': False
                    }
                else:
                    raise Exception(f"OSRM API error: {data.get('message', 'Unknown error')}")
            else:
                raise Exception(f"OSRM API request failed with status {response.status_code}")
                
        except Exception as e:
            _logger.warning(f"OSRM route calculation failed for mission {self.name}: {e}")
            
            # Create fallback straight-line route
            fallback_data = self._create_fallback_route(waypoints)
            
            # Cache the fallback route
            route_cache.cache_route(waypoints, fallback_data=fallback_data)
            
            return {
                'geometry': fallback_data.get('geometry', ''),
                'distance': fallback_data.get('distance', 0),
                'duration': fallback_data.get('duration', 0),
                'is_fallback': True,
                'cached': False
            }
    
    def _create_fallback_route(self, waypoints):
        """Create a fallback straight-line route when OSRM fails"""
        # Calculate total straight-line distance
        total_distance = 0
        
        for i in range(len(waypoints) - 1):
            lat1, lon1 = waypoints[i]
            lat2, lon2 = waypoints[i + 1]
            distance = _haversine_distance(lat1, lon1, lat2, lon2)
            total_distance += distance
        
        # Estimate duration (assuming 50 km/h average speed)
        estimated_duration = (total_distance / 50) * 60  # minutes
        
        # Create simple polyline geometry (just the waypoints)
        geometry_points = []
        for lat, lon in waypoints:
            geometry_points.append([lat, lon])
        
        return {
            'geometry': json.dumps(geometry_points),  # Store as JSON for fallback
            'distance': total_distance,
            'duration': estimated_duration
        }

    @api.model
    def get_route_cache_stats(self):
        """Get route cache statistics for admin purposes"""
        route_cache = self.env['transport.route.cache']
        return route_cache.get_cache_stats()
    
    @api.model
    def cleanup_route_cache(self, days_old=30):
        """Clean up old route cache entries"""
        route_cache = self.env['transport.route.cache']
        return route_cache.cleanup_old_cache(days_old)