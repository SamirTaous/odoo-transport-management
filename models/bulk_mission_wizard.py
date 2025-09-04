# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class BulkMissionWizard(models.TransientModel):
    _name = 'bulk.mission.wizard'
    _description = 'Bulk Mission Creation Wizard'

    name = fields.Char(string='Batch Name', required=True, default=lambda self: _('Bulk Mission Batch'))
    mission_date = fields.Date(string='Mission Date', required=True, default=fields.Date.context_today)
    driver_id = fields.Many2one('res.partner', string='Default Driver', domain=[('is_company', '=', False)])
    vehicle_id = fields.Many2one('truck.vehicle', string='Default Vehicle')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High')
    ], string='Default Priority', default='1')
    
    # Mission template data
    mission_templates = fields.Text(string='Mission Templates', default='[]')
    
    # Bulk creation settings
    auto_optimize_routes = fields.Boolean(string='Auto-optimize Routes', default=True)
    create_confirmed = fields.Boolean(string='Create as Confirmed', default=False)
    
    def get_mission_templates(self):
        """Return parsed mission templates"""
        try:
            return json.loads(self.mission_templates or '[]')
        except:
            return []
    
    def set_mission_templates(self, templates):
        """Set mission templates as JSON"""
        self.mission_templates = json.dumps(templates)
    
    @api.model
    def default_get(self, fields_list):
        """Set default values"""
        defaults = super().default_get(fields_list)
        defaults['mission_templates'] = '[]'
        return defaults
    
    def action_create_missions(self):
        """Create multiple missions from templates"""
        templates = self.get_mission_templates()
        
        if not templates:
            raise UserError(_("No mission templates defined. Please add at least one mission."))
        
        created_missions = []
        
        for template in templates:
            try:
                # Create mission
                mission_vals = {
                    'mission_date': self.mission_date,
                    'driver_id': template.get('driver_id') or self.driver_id.id,
                    'vehicle_id': template.get('vehicle_id') or self.vehicle_id.id,
                    'priority': template.get('priority') or self.priority,
                    'source_location': template.get('source_location'),
                    'source_latitude': template.get('source_latitude'),
                    'source_longitude': template.get('source_longitude'),
                    'notes': template.get('notes', ''),
                }
                
                mission = self.env['transport.mission'].create(mission_vals)
                
                # Create destinations
                destinations = template.get('destinations', [])
                for dest_data in destinations:
                    dest_vals = {
                        'mission_id': mission.id,
                        'location': dest_data.get('location'),
                        'latitude': dest_data.get('latitude'),
                        'longitude': dest_data.get('longitude'),
                        'sequence': dest_data.get('sequence', 1),
                        'mission_type': dest_data.get('mission_type', 'delivery'),
                        'expected_arrival_time': dest_data.get('expected_arrival_time'),
                        'service_duration': dest_data.get('service_duration', 0),
                        'package_type': dest_data.get('package_type', 'individual'),
                        'total_weight': dest_data.get('total_weight', 0),
                        'total_volume': dest_data.get('total_volume', 0),
                        'requires_signature': dest_data.get('requires_signature', False),
                    }
                    self.env['transport.destination'].create(dest_vals)
                
                # Auto-optimize route if requested
                if self.auto_optimize_routes and len(destinations) > 1:
                    try:
                        mission.action_optimize_route()
                    except Exception as e:
                        _logger.warning(f"Failed to optimize route for mission {mission.name}: {e}")
                
                # Confirm mission if requested
                if self.create_confirmed:
                    mission.action_confirm()
                
                created_missions.append(mission)
                
            except Exception as e:
                _logger.error(f"Failed to create mission from template: {e}")
                raise UserError(_("Failed to create mission: %s") % str(e))
        
        # Return action to view created missions
        if len(created_missions) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Created Mission'),
                'res_model': 'transport.mission',
                'res_id': created_missions[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Created Missions'),
                'res_model': 'transport.mission',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', [m.id for m in created_missions])],
                'target': 'current',
            }
    
    def action_generate_json(self):
        """Generate and log complete JSON data for bulk locations"""
        try:
            location_data = json.loads(self.mission_templates or '{"sources": [], "destinations": []}')
        except:
            location_data = {"sources": [], "destinations": []}
        
        sources = location_data.get('sources', [])
        destinations = location_data.get('destinations', [])
        
        if not sources and not destinations:
            raise UserError(_("No locations selected. Please add sources and destinations using the map interface first."))
        
        # Get all available vehicles with complete information
        try:
            vehicles = self.env['truck.vehicle'].search([]).read([
                'id', 'name', 'license_plate', 'vin_number', 'year', 'brand', 'model_name',
                'ownership_type', 'driver_id', 'truck_type', 'max_payload', 'cargo_volume',
                'cargo_length', 'cargo_width', 'cargo_height', 'overall_length', 'overall_width', 
                'overall_height', 'gross_vehicle_weight', 'engine_power', 'fuel_type', 
                'fuel_capacity', 'fuel_consumption', 'has_crane', 'has_tailgate', 
                'has_refrigeration', 'has_gps', 'special_equipment', 'registration_expiry',
                'insurance_expiry', 'inspection_due', 'maintenance_status', 'odometer',
                'last_service_odometer', 'service_interval_km', 'purchase_price', 
                'current_value', 'is_available', 'rental_status', 'km_until_service',
                'rental_start_date', 'rental_end_date', 'rental_cost_per_day', 'subcontractor_id'
            ])
        except Exception as e:
            _logger.warning(f"Could not load from truck.vehicle: {e}")
            try:
                vehicles = self.env['fleet.vehicle'].search([]).read(['id', 'name', 'model_id'])
            except Exception as e2:
                _logger.warning(f"Could not load from fleet.vehicle: {e2}")
                vehicles = []
        
        try:
            drivers = self.env['res.partner'].search([('is_company', '=', False)]).read(['id', 'name'])
        except:
            try:
                drivers = self.env['hr.employee'].search([]).read(['id', 'name'])
            except:
                drivers = []
        
        complete_data = {
            'bulk_location_data': {
                'created_at': fields.Datetime.now().isoformat(),
                'total_sources': len(sources),
                'total_destinations': len(destinations),
                'sources': [
                    {
                        **source,
                        # Ensure all required fields are present with defaults
                        'source_type': source.get('source_type', 'warehouse'),
                        'name': source.get('name', 'Unnamed Source')
                    }
                    for source in sources
                ],
                'destinations': [
                    {
                        **dest,
                        # Ensure all required fields are present with defaults
                        'mission_type': dest.get('mission_type', 'delivery'),
                        'package_type': dest.get('package_type', 'individual'),
                        'total_weight': dest.get('total_weight', 0),
                        'total_volume': dest.get('total_volume', 0),
                        'service_duration': dest.get('service_duration', 0),
                        'requires_signature': dest.get('requires_signature', False),
                        'expected_arrival_time': dest.get('expected_arrival_time'),
                        'name': dest.get('name', 'Unnamed Destination')
                    }
                    for dest in destinations
                ],
                'available_vehicles': [
                    {
                        **vehicle,
                        # Ensure all truck fields are properly formatted
                        'max_payload': vehicle.get('max_payload', 0),
                        'cargo_volume': vehicle.get('cargo_volume', 0),
                        'license_plate': vehicle.get('license_plate', 'N/A'),
                        'brand': vehicle.get('brand', 'unknown'),
                        'model_name': vehicle.get('model_name', 'unknown'),
                        'truck_type': vehicle.get('truck_type', 'rigid'),
                        'fuel_type': vehicle.get('fuel_type', 'diesel'),
                        'ownership_type': vehicle.get('ownership_type', 'owned'),
                        'maintenance_status': vehicle.get('maintenance_status', 'good'),
                        'is_available': vehicle.get('is_available', True),
                        'rental_status': vehicle.get('rental_status', 'N/A'),
                        # Convert date fields to strings for JSON serialization
                        'registration_expiry': str(vehicle.get('registration_expiry')) if vehicle.get('registration_expiry') else None,
                        'insurance_expiry': str(vehicle.get('insurance_expiry')) if vehicle.get('insurance_expiry') else None,
                        'inspection_due': str(vehicle.get('inspection_due')) if vehicle.get('inspection_due') else None,
                        'rental_start_date': str(vehicle.get('rental_start_date')) if vehicle.get('rental_start_date') else None,
                        'rental_end_date': str(vehicle.get('rental_end_date')) if vehicle.get('rental_end_date') else None,
                    }
                    for vehicle in vehicles
                ],
                'available_drivers': drivers,
                'summary': {
                    'total_locations': len(sources) + len(destinations),
                    'pickup_destinations': len([d for d in destinations if d.get('mission_type') == 'pickup']),
                    'delivery_destinations': len([d for d in destinations if d.get('mission_type') == 'delivery']),
                    'total_weight': sum(d.get('total_weight', 0) for d in destinations),
                    'total_volume': sum(d.get('total_volume', 0) for d in destinations)
                }
            }
        }
        
        # Log the complete JSON
        _logger.info("=== COMPLETE BULK LOCATION JSON ===")
        _logger.info(json.dumps(complete_data, indent=2, default=str))
        _logger.info("=== END JSON ===")
        
        # Print summary
        summary = f"""
BULK LOCATION SUMMARY:
- Total Sources: {len(sources)}
- Total Destinations: {len(destinations)}
- Pickup Destinations: {len([d for d in destinations if d.get('mission_type') == 'pickup'])}
- Delivery Destinations: {len([d for d in destinations if d.get('mission_type') == 'delivery'])}
- Total Weight: {sum(d.get('total_weight', 0) for d in destinations)} kg
- Total Volume: {sum(d.get('total_volume', 0) for d in destinations)} m³
- Available Vehicles: {len(vehicles)}
- Available Drivers: {len(drivers)}

JSON has been logged to server console. Check the logs for complete data.
        """
        
        _logger.info(summary)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'JSON Generated Successfully',
                'message': f'Complete JSON with {len(sources)} sources, {len(destinations)} destinations, and {len(vehicles)} vehicles logged to console.',
                'type': 'success',
                'sticky': True,
            }
        }

    def action_preview_missions(self):
        """Preview selected locations"""
        try:
            location_data = json.loads(self.mission_templates or '{"sources": [], "destinations": []}')
        except:
            location_data = {"sources": [], "destinations": []}
        
        sources = location_data.get('sources', [])
        destinations = location_data.get('destinations', [])
        
        if not sources and not destinations:
            raise UserError(_("No locations selected."))
        
        preview_data = []
        
        # Add sources to preview
        for i, source in enumerate(sources, 1):
            preview_data.append({
                'mission_number': f'S{i}',
                'source': source.get('location', 'Unknown location'),
                'destination_count': 0,
                'total_weight': 0,
                'driver': 'Source Location',
                'vehicle': source.get('source_type', 'warehouse').title(),
            })
        
        # Add destinations to preview
        for i, dest in enumerate(destinations, 1):
            preview_data.append({
                'mission_number': f'D{i}',
                'source': dest.get('location', 'Unknown location'),
                'destination_count': 1,
                'total_weight': dest.get('total_weight', 0),
                'driver': dest.get('mission_type', 'delivery').title(),
                'vehicle': dest.get('package_type', 'individual').title(),
            })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Location Preview'),
            'res_model': 'bulk.mission.preview',
            'view_mode': 'tree',
            'target': 'new',
            'context': {
                'default_preview_data': json.dumps(preview_data),
                'default_wizard_id': self.id,
            }
        }

class BulkMissionPreview(models.TransientModel):
    _name = 'bulk.mission.preview'
    _description = 'Bulk Mission Preview'
    
    wizard_id = fields.Many2one('bulk.mission.wizard', string='Wizard')
    preview_data = fields.Text(string='Preview Data')
    mission_number = fields.Integer(string='Mission #')
    source = fields.Char(string='Source Location')
    destination_count = fields.Integer(string='Destinations')
    total_weight = fields.Float(string='Total Weight (kg)')
    driver = fields.Char(string='Driver')
    vehicle = fields.Char(string='Vehicle')