from odoo import models, fields, api
import hashlib
import json
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)

class RouteCache(models.Model):
    _name = 'transport.route.cache'
    _description = 'OSRM Route Cache'
    _rec_name = 'route_hash'

    route_hash = fields.Char(string='Route Hash', required=True, index=True)
    waypoints = fields.Text(string='Waypoints JSON', required=True, help="JSON array of [lat, lng] coordinates")
    route_geometry = fields.Text(string='Route Geometry', help="OSRM polyline geometry")
    route_distance = fields.Float(string='Route Distance (km)', help="Total route distance in kilometers")
    route_duration = fields.Float(string='Route Duration (min)', help="Total route duration in minutes")
    osrm_response = fields.Text(string='Full OSRM Response', help="Complete OSRM API response for debugging")
    created_date = fields.Datetime(string='Created Date', default=fields.Datetime.now)
    last_used = fields.Datetime(string='Last Used', default=fields.Datetime.now)
    use_count = fields.Integer(string='Use Count', default=1)
    is_fallback = fields.Boolean(string='Is Fallback Route', default=False, help="True if this is a straight-line fallback route")

    _sql_constraints = [
        ('unique_route_hash', 'unique(route_hash)', 'Route hash must be unique'),
    ]

    @api.model
    def generate_route_hash(self, waypoints):
        """Generate a unique hash for a set of waypoints"""
        # Sort waypoints to ensure consistent hashing regardless of order
        # But keep the first waypoint (source) in place for route calculation
        if len(waypoints) > 2:
            source = waypoints[0]
            destinations = sorted(waypoints[1:], key=lambda x: (x[0], x[1]))
            normalized_waypoints = [source] + destinations
        else:
            normalized_waypoints = waypoints
        
        waypoints_str = json.dumps(normalized_waypoints, sort_keys=True)
        return hashlib.md5(waypoints_str.encode()).hexdigest()

    @api.model
    def get_cached_route(self, waypoints):
        """Get cached route for given waypoints"""
        route_hash = self.generate_route_hash(waypoints)
        cached_route = self.search([('route_hash', '=', route_hash)], limit=1)
        
        if cached_route:
            # Update usage statistics
            cached_route.write({
                'last_used': fields.Datetime.now(),
                'use_count': cached_route.use_count + 1
            })
            
            return {
                'geometry': cached_route.route_geometry,
                'distance': cached_route.route_distance,
                'duration': cached_route.route_duration,
                'is_fallback': cached_route.is_fallback,
                'cached': True
            }
        
        return None

    @api.model
    def cache_route(self, waypoints, osrm_response=None, fallback_data=None):
        """Cache a route calculation result"""
        route_hash = self.generate_route_hash(waypoints)
        
        # Check if already cached
        existing = self.search([('route_hash', '=', route_hash)], limit=1)
        if existing:
            return existing

        if osrm_response:
            # Cache successful OSRM response
            route = osrm_response.get('routes', [{}])[0]
            cache_data = {
                'route_hash': route_hash,
                'waypoints': json.dumps(waypoints),
                'route_geometry': route.get('geometry', ''),
                'route_distance': route.get('distance', 0) / 1000,  # Convert to km
                'route_duration': route.get('duration', 0) / 60,    # Convert to minutes
                'osrm_response': json.dumps(osrm_response),
                'is_fallback': False
            }
        elif fallback_data:
            # Cache fallback route
            cache_data = {
                'route_hash': route_hash,
                'waypoints': json.dumps(waypoints),
                'route_geometry': fallback_data.get('geometry', ''),
                'route_distance': fallback_data.get('distance', 0),
                'route_duration': fallback_data.get('duration', 0),
                'osrm_response': json.dumps({'fallback': True}),
                'is_fallback': True
            }
        else:
            _logger.warning("No route data provided for caching")
            return None

        return self.create(cache_data)

    @api.model
    def cleanup_old_cache(self, days_old=30):
        """Clean up cache entries older than specified days"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days_old)
        old_entries = self.search([('last_used', '<', cutoff_date)])
        
        if old_entries:
            _logger.info(f"Cleaning up {len(old_entries)} old route cache entries")
            old_entries.unlink()
        
        return len(old_entries)

    @api.model
    def get_cache_stats(self):
        """Get cache statistics"""
        total_entries = self.search_count([])
        fallback_entries = self.search_count([('is_fallback', '=', True)])
        osrm_entries = total_entries - fallback_entries
        
        # Calculate total usage
        total_usage = sum(self.search([]).mapped('use_count'))
        
        return {
            'total_entries': total_entries,
            'osrm_entries': osrm_entries,
            'fallback_entries': fallback_entries,
            'total_usage': total_usage,
            'cache_hit_potential': total_usage - total_entries if total_usage > total_entries else 0
        }