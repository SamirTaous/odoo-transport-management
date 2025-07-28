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
    mission_type = fields.Selection([
        ('pickup', 'Pickup Mission'),
        ('delivery', 'Delivery Mission')
    ], string='Mission Type', required=True, default='pickup', tracking=True)
    mission_date = fields.Date(string='Date', required=True, tracking=True, default=fields.Date.context_today)
    source_location = fields.Char(string='Source Location', tracking=True)
    source_latitude = fields.Float(string='Source Latitude', digits=(10, 7))
    source_longitude = fields.Float(string='Source Longitude', digits=(10, 7))
    destination_ids = fields.One2many('transport.destination', 'mission_id', string='Destinations')
    driver_id = fields.Many2one('res.partner', string='Driver', tracking=True, domain=[('is_company', '=', False)])
    vehicle_id = fields.Many2one('transport.vehicle', string='Vehicle', tracking=True)
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

    # --- All standard methods are correct ---
    @api.depends('source_latitude', 'source_longitude', 'destination_ids.latitude', 'destination_ids.longitude', 'destination_ids.sequence')
    def _compute_total_distance(self):
        for mission in self:
            distance = 0.0
            if mission.source_latitude and mission.source_longitude:
                points = [(mission.source_latitude, mission.source_longitude)]
                sorted_destinations = mission.destination_ids.sorted('sequence')
                for dest in sorted_destinations:
                    if dest.latitude and dest.longitude:
                        points.append((dest.latitude, dest.longitude))
                if len(points) > 1:
                    for i in range(len(points) - 1):
                        p1, p2 = points[i], points[i+1]
                        distance += _haversine_distance(p1[0], p1[1], p2[0], p2[1])
            mission.total_distance_km = distance
            
    @api.depends('destination_ids.is_completed')
    def _compute_destination_progress(self):
        for mission in self:
            total_destinations = len(mission.destination_ids)
            if not total_destinations:
                mission.destination_progress = 0.0
            else:
                completed_count = len(mission.destination_ids.filtered(lambda d: d.is_completed))
                mission.destination_progress = (completed_count / total_destinations) * 100

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.mission.sequence') or _('New')
        return super().create(vals_list)

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