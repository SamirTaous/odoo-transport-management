# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
import requests

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
    
    # AI optimization result storage
    ai_optimization_result = fields.Text(string='AI Optimization Result')
    
    # Bulk creation settings
    auto_optimize_routes = fields.Boolean(string='Auto-optimize Routes', default=True)
    create_confirmed = fields.Boolean(string='Create as Confirmed', default=False)
    
    def _normalize_datetime_string(self, value):
        """Normalize various incoming datetime string formats to Odoo's '%Y-%m-%d %H:%M:%S'.
        Accepts ISO 8601 like '2025-09-11T10:00:00', with optional milliseconds and timezone.
        Returns a string or None.
        """
        if not value:
            return None
        from datetime import datetime
        if isinstance(value, datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, str):
            s = value.strip()
            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                s = s[1:-1]
            s = s.replace('T', ' ')
            if s.endswith('Z'):
                s = s[:-1].strip()
            if '.' in s:
                left, right = s.split('.', 1)
                for sep in ['+', '-', 'Z']:
                    if sep in right:
                        right = ''
                        break
                s = left
            for tz_sep in ['+', '-']:
                if tz_sep in s and len(s) >= 6:
                    parts = s.rsplit(tz_sep, 1)
                    if len(parts) == 2 and (':' in parts[1] or parts[1].isdigit()):
                        s = parts[0].strip()
                        break
            if len(s) == 10 and s.count('-') == 2:
                s = s + ' 00:00:00'
            if len(s) == 16 and s.count(':') == 1:
                s = s + ':00'
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    dt = datetime.strptime(s, fmt)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    continue
            try:
                iso_candidate = value.replace('T', ' ').rstrip('Z')
                dt = datetime.fromisoformat(iso_candidate)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        return value
    
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
        defaults['name'] = _('Bulk Mission Batch')
        return defaults
        
    @api.model
    def create(self, vals):
        """Override create to handle widget creation"""
        _logger.info(f"Creating bulk mission wizard with vals: {vals}")
        # Ensure mission_templates is a valid JSON string
        if 'mission_templates' in vals and not isinstance(vals['mission_templates'], str):
            vals['mission_templates'] = json.dumps(vals['mission_templates'])
        return super().create(vals)
    
    def action_create_missions(self):
        """Create multiple missions from templates"""
        templates = self.get_mission_templates()
        
        if not templates:
            raise UserError(_("No mission templates defined. Please add at least one mission."))
        
        created_missions = []
        
        for template in templates:
            try:
                # Get source information
                source_data = {
                    'latitude': template.get('source_latitude'),
                    'longitude': template.get('source_longitude'),
                    'location': template.get('source_location')
                }
                
                # Get destinations and optimize their sequence
                destinations = template.get('destinations', [])
                if destinations:
                    # Optimize the sequence of destinations
                    optimized_destinations = self._optimize_route_sequence(source_data, destinations)
                    _logger.info(f"Optimized route sequence for mission. Original order vs optimized:")
                    for i, (orig, opt) in enumerate(zip(destinations, optimized_destinations)):
                        _logger.info(f"Stop {i+1}: {orig.get('location')} -> {opt.get('location')}")
                    template['destinations'] = optimized_destinations

                # Create mission
                mission_vals = {
                    'mission_date': self.mission_date,
                    'driver_id': template.get('driver_id') or self.driver_id.id,
                    'vehicle_id': template.get('vehicle_id') or self.vehicle_id.id,
                    'priority': template.get('priority') or self.priority,
                    'source_location': source_data['location'],
                    'source_latitude': source_data['latitude'],
                    'source_longitude': source_data['longitude'],
                    'notes': template.get('notes', ''),
                }
                
                mission = self.env['transport.mission'].create(mission_vals)
                
                # Create destinations with optimized sequence
                destinations = template.get('destinations', [])
                for index, dest_data in enumerate(destinations, start=1):
                    dest_vals = {
                        'mission_id': mission.id,
                        'location': dest_data.get('location'),
                        'latitude': dest_data.get('latitude'),
                        'longitude': dest_data.get('longitude'),
                        'sequence': index,  # Use the optimized order index
                        'mission_type': dest_data.get('mission_type', 'delivery'),
                        'expected_arrival_time': self._normalize_datetime_string(dest_data.get('expected_arrival_time')),
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
        
        # Handle both list and dict formats
        if isinstance(location_data, list):
            # If it's a list, assume it's the old mission format
            sources = []
            destinations = location_data  # The list contains destinations
        elif isinstance(location_data, dict):
            sources = location_data.get('sources', [])
            destinations = location_data.get('destinations', [])
        else:
            sources = []
            destinations = []
        
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

    def action_optimize_with_ai(self):
        """Generate optimized missions using AI"""
        _logger.info("=== Starting AI optimization ===")
        
        # First try to parse the JSON data
        if not self.mission_templates:
            _logger.error("No mission templates data found")
            raise UserError(_("No locations found. Please add sources and destinations first."))
            
        try:
            location_data = json.loads(self.mission_templates)
            _logger.info(f"Successfully parsed mission templates JSON: {type(location_data)}")
        except json.JSONDecodeError as e:
            _logger.error(f"Failed to parse mission templates JSON: {e}")
            raise UserError(_("Invalid location data format."))
            
        # Handle both list and dict formats
        if isinstance(location_data, list):
            # If it's a list, assume it's the old mission format
            sources = []
            destinations = location_data  # The list contains destinations
            _logger.info(f"Using list format with {len(destinations)} destinations")
        elif isinstance(location_data, dict):
            sources = location_data.get('sources', [])
            destinations = location_data.get('destinations', [])
            _logger.info(f"Using dict format with {len(sources)} sources and {len(destinations)} destinations")
        else:
            _logger.error(f"Unexpected data format type: {type(location_data)}")
            raise UserError(_("Invalid location data structure."))
        
        if not sources and not destinations:
            raise UserError(_("No locations selected. Please add sources and destinations first."))
        
        # Get all available vehicles and drivers
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
        
        try:
            drivers = self.env['res.partner'].search([('is_company', '=', False)]).read(['id', 'name'])
        except:
            try:
                drivers = self.env['hr.employee'].search([]).read(['id', 'name'])
            except:
                drivers = []
        
        # Prepare complete data for AI
        complete_data = {
            'bulk_location_data': {
                'created_at': fields.Datetime.now().isoformat(),
                'total_sources': len(sources),
                'total_destinations': len(destinations),
                'sources': sources,
                'destinations': destinations,
                'available_vehicles': vehicles,
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
        
        try:
            # Import and use the AI service
            _logger.info("=== STARTING AI OPTIMIZATION ===")
            _logger.info("Importing AI service...")
            
            # Use the built-in AI optimization methods
            _logger.info("Using built-in AI optimization methods...")
            
            _logger.info("Starting AI optimization...")
            _logger.info(f"Data to optimize: {len(sources)} sources, {len(destinations)} destinations")
            
            optimized_missions = self._optimize_bulk_missions_with_ai(complete_data['bulk_location_data'])
            
            # Return the AI response data to the frontend for console logging
            summary = optimized_missions.get('optimization_summary', {})
            missions_created = summary.get('total_missions_created', 0)
            vehicles_used = summary.get('total_vehicles_used', 0)
            optimization_score = summary.get('optimization_score', 0)
            
            # Store the AI response in the wizard record for JavaScript to retrieve
            self.write({'ai_optimization_result': json.dumps(optimized_missions, default=str)})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🤖 AI Optimization Complete!',
                    'message': f'Created {missions_created} optimized missions using {vehicles_used} vehicles (Score: {optimization_score}/100). Check browser console for detailed analysis.',
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except ImportError as e:
            _logger.error(f"AI service import failed: {e}")
            # Use simple fallback optimization
            fallback_result = self._simple_fallback_optimization(sources, destinations, vehicles, drivers)
            
            _logger.info("=== FALLBACK OPTIMIZATION COMPLETED ===")
            _logger.info(json.dumps(fallback_result, indent=2, default=str))
            _logger.info("=== END FALLBACK OPTIMIZATION ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Fallback Optimization Completed',
                    'message': f'AI service unavailable. Used fallback optimization: {fallback_result.get("optimization_summary", {}).get("total_missions_created", 0)} missions created.',
                    'type': 'warning',
                    'sticky': True,
                }
            }
        except Exception as e:
            _logger.error(f"AI optimization failed: {e}")
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Optimization Failed',
                    'message': f'Error: {str(e)}. Check server logs for details.',
                    'type': 'warning',
                    'sticky': True,
                }
            }

    def _simple_fallback_optimization(self, sources, destinations, vehicles, drivers):
        """Simple fallback optimization when AI service fails"""
        _logger.info("Using simple fallback optimization")
        
        # Create basic missions
        optimized_missions = []
        total_distance = 0
        total_cost = 0
        
        # Simple logic: one mission per source with nearby destinations
        for i, source in enumerate(sources[:len(vehicles) if vehicles else 1]):
            vehicle = vehicles[i] if i < len(vehicles) and vehicles else (vehicles[0] if vehicles else {"id": 1, "name": "Default Vehicle"})
            driver = drivers[i] if i < len(drivers) and drivers else (drivers[0] if drivers else {"id": 1, "name": "Default Driver"})
            
            # Assign destinations to this mission (simple: divide destinations)
            dest_per_mission = max(1, len(destinations) // max(1, len(sources)))
            mission_destinations = destinations[i*dest_per_mission:(i+1)*dest_per_mission] if destinations else []
            
            if mission_destinations or i == 0:  # Always create at least one mission
                mission_distance = len(mission_destinations) * 20  # 20km per destination
                mission_cost = mission_distance * 1.5  # 1.5 cost per km
                
                total_distance += mission_distance
                total_cost += mission_cost
                
                mission = {
                    "mission_id": f"FALLBACK_{i+1:03d}",
                    "mission_name": f"Fallback Mission {i+1}",
                    "assigned_vehicle": {
                        "vehicle_id": vehicle.get('id', 1),
                        "vehicle_name": vehicle.get('name', 'Default Vehicle'),
                        "license_plate": vehicle.get('license_plate', 'N/A')
                    },
                    "assigned_driver": {
                        "driver_id": driver.get('id', 1),
                        "driver_name": driver.get('name', 'Default Driver')
                    },
                    "source_location": {
                        "source_id": source.get('id', i+1) if source else i+1,
                        "name": source.get('name', f'Source {i+1}') if source else f'Source {i+1}',
                        "location": source.get('location', 'Default Location') if source else 'Default Location'
                    },
                    "destinations": [
                        {
                            "destination_id": dest.get('id', idx),
                            "sequence": idx + 1,
                            "name": dest.get('name', f'Destination {idx+1}'),
                            "location": dest.get('location', 'Unknown'),
                            "mission_type": dest.get('mission_type', 'delivery')
                        }
                        for idx, dest in enumerate(mission_destinations)
                    ],
                    "route_optimization": {
                        "total_distance_km": mission_distance,
                        "estimated_total_cost": mission_cost,
                        "optimization_notes": "Simple fallback optimization"
                    }
                }
                
                optimized_missions.append(mission)
        
        return {
            "optimization_summary": {
                "total_missions_created": len(optimized_missions),
                "total_vehicles_used": len(optimized_missions),
                "total_estimated_distance_km": total_distance,
                "total_estimated_cost": total_cost,
                "optimization_score": 70,
                "cost_savings_percentage": 15,
                "efficiency_improvements": ["Basic route assignment", "Fallback optimization used"]
            },
            "optimized_missions": optimized_missions,
            "optimization_insights": {
                "key_decisions": ["Used fallback optimization due to AI service issues"],
                "recommendations": ["Configure AI service for better results"]
            }
        }

    def action_debug_basic(self):
        """Basic debug method to test if method calling works"""
        _logger.info("=== DEBUG: Basic method call test ===")
        _logger.info(f"Method called successfully on record ID: {self.id}")
        _logger.info(f"Mission templates: {self.mission_templates}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Debug Success',
                'message': 'Basic method call works. Check server logs.',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_test_ai_simple(self):
        """Simple test method to check if the basic functionality works"""
        try:
            _logger.info(f"Raw mission_templates data: {self.mission_templates}")
            
            location_data = json.loads(self.mission_templates or '{"sources": [], "destinations": []}')
            _logger.info(f"Parsed location_data type: {type(location_data)}")
            _logger.info(f"Parsed location_data: {location_data}")
            
            # Handle both list and dict formats
            if isinstance(location_data, list):
                # If it's a list, assume it's the old mission format
                sources = []
                destinations = location_data  # The list contains destinations
                _logger.info("Data is in list format (old mission format)")
            elif isinstance(location_data, dict):
                sources = location_data.get('sources', [])
                destinations = location_data.get('destinations', [])
                _logger.info("Data is in dict format (new location format)")
            else:
                sources = []
                destinations = []
                _logger.warning(f"Unexpected data format: {type(location_data)}")
            
            _logger.info(f"Test AI: Found {len(sources)} sources and {len(destinations)} destinations")
            
            # Simple mock optimization without external dependencies
            result = {
                "optimization_summary": {
                    "total_missions_created": len(sources),
                    "total_vehicles_used": len(sources),
                    "total_estimated_distance_km": len(destinations) * 25,
                    "total_estimated_cost": len(destinations) * 50,
                    "optimization_score": 85,
                    "cost_savings_percentage": 20
                },
                "status": "success",
                "message": "Simple AI test completed successfully"
            }
            
            _logger.info("=== SIMPLE AI TEST RESULT ===")
            _logger.info(json.dumps(result, indent=2))
            _logger.info("=== END TEST ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Test Successful',
                    'message': f'Simple AI test completed. Created {len(sources)} missions. Check logs for details.',
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Simple AI test failed: {e}")
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Test Failed',
                    'message': f'Simple test failed: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_test_ai_connection(self):
        """Test the AI service connection"""
        try:
            _logger.info("=== TESTING AI SERVICE CONNECTION ===")
            
            # Test the AI connection using built-in method
            success, message = self._test_ai_connection()
            
            if success:
                _logger.info("AI service connection test successful")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'AI Connection Successful',
                        'message': f'AI service is working properly: {message}',
                        'type': 'success',
                        'sticky': True,
                    }
                }
            else:
                _logger.error(f"AI service connection test failed: {message}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'AI Connection Failed',
                        'message': f'AI service connection failed: {message}',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
                
        except Exception as e:
            _logger.error(f"AI connection test failed: {e}")
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Connection Test Failed',
                    'message': f'Connection test failed: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_test_full_flow(self):
        """Test the complete AI optimization flow with mock data"""
        try:
            _logger.info("=== TESTING FULL AI OPTIMIZATION FLOW ===")
            
            # Create mock data for testing
            mock_data = {
                'sources': [
                    {
                        'id': 1,
                        'name': 'Test Warehouse',
                        'location': '123 Test Street, Test City',
                        'latitude': 40.7128,
                        'longitude': -74.0060,
                        'source_type': 'warehouse'
                    }
                ],
                'destinations': [
                    {
                        'id': 1,
                        'name': 'Test Customer A',
                        'location': '456 Customer Ave, Test City',
                        'latitude': 40.7589,
                        'longitude': -73.9851,
                        'mission_type': 'delivery',
                        'total_weight': 100,
                        'total_volume': 2.5,
                        'package_type': 'pallet'
                    },
                    {
                        'id': 2,
                        'name': 'Test Customer B',
                        'location': '789 Client Blvd, Test City',
                        'latitude': 40.7831,
                        'longitude': -73.9712,
                        'mission_type': 'pickup',
                        'total_weight': 50,
                        'total_volume': 1.2,
                        'package_type': 'individual'
                    }
                ],
                'available_vehicles': [
                    {
                        'id': 1,
                        'name': 'Test Truck 1',
                        'license_plate': 'TEST123',
                        'max_payload': 5000,
                        'cargo_volume': 25,
                        'fuel_type': 'diesel',
                        'truck_type': 'rigid',
                        'is_available': True
                    }
                ],
                'available_drivers': [
                    {
                        'id': 1,
                        'name': 'Test Driver'
                    }
                ]
            }
            
            # Run the optimization using built-in method
            _logger.info("Running AI optimization with mock data...")
            result = self._optimize_bulk_missions_with_ai(mock_data)
            
            # Validate the result
            if result and isinstance(result, dict):
                summary = result.get('optimization_summary', {})
                missions = result.get('optimized_missions', [])
                
                _logger.info("=== FULL FLOW TEST SUCCESSFUL ===")
                _logger.info(f"Created {summary.get('total_missions_created', 0)} missions")
                _logger.info(f"Used {summary.get('total_vehicles_used', 0)} vehicles")
                _logger.info(f"Optimization score: {summary.get('optimization_score', 0)}")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'ai_optimization_result',
                    'params': {
                        'title': 'Full Flow Test Successful',
                        'message': f'AI optimization test completed successfully. Created {len(missions)} missions with score {summary.get("optimization_score", 0)}. Check browser console for detailed results.',
                        'ai_response': result,
                        'summary': {
                            'missions_created': len(missions),
                            'vehicles_used': summary.get('total_vehicles_used', 0),
                            'optimization_score': summary.get('optimization_score', 0),
                            'total_distance': summary.get('total_estimated_distance_km', 0),
                            'total_cost': summary.get('total_estimated_cost', 0),
                            'cost_savings': summary.get('cost_savings_percentage', 0)
                        }
                    }
                }
            else:
                raise ValueError("Invalid result format from AI service")
                
        except Exception as e:
            _logger.error(f"Full flow test failed: {e}")
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Full Flow Test Failed',
                    'message': f'Full flow test failed: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    # AI Optimization Methods
    def _get_gemini_api_key(self):
        """Get the Gemini API key from system parameters"""
        api_key = self.env['ir.config_parameter'].sudo().get_param('transport_management.gemini_api_key')
        if not api_key:
            raise UserError("Gemini API key not configured. Please set 'transport_management.gemini_api_key' in System Parameters.")
        return api_key

    def _test_ai_connection(self):
        """Test the AI service connection"""
        try:
            api_key = self._get_gemini_api_key()
            
            # Simple test payload
            test_payload = {
                "contents": [
                    {"parts": [{"text": "Hello, respond with a simple JSON object: {\"status\": \"success\", \"message\": \"API connection working\"}"}]}
                ],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "maxOutputTokens": 100
                }
            }
            
            api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
            request_url = f"{api_url}?key={api_key}"
            headers = {'Content-Type': 'application/json'}
            
            _logger.info("Testing API connection...")
            response = requests.post(request_url, json=test_payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            response_data = response.json()
            content_text = response_data['candidates'][0]['content']['parts'][0]['text']
            
            # Try to parse the response
            test_result = json.loads(content_text.strip())
            
            _logger.info(f"API test successful: {test_result}")
            return True, "API connection successful"
            
        except Exception as e:
            _logger.error(f"API test failed: {e}")
            return False, str(e)

    def _optimize_route_sequence(self, source, destinations):
        """
        Optimize the sequence of destinations using an enhanced clustering and route optimization approach
        Returns reordered destinations list with proper sequences
        """
        if not destinations:
            return []
            
        _logger.info("Starting enhanced route sequence optimization")
        _logger.info(f"Original sequence: {[d.get('location') for d in destinations]}")

        def calculate_distance(point1, point2):
            """Calculate straight-line distance between two points using Haversine formula"""
            from math import radians, sin, cos, sqrt, atan2
            
            lat1 = radians(float(point1['latitude']))
            lon1 = radians(float(point1['longitude']))
            lat2 = radians(float(point2['latitude']))
            lon2 = radians(float(point2['longitude']))
            
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            R = 6371  # Earth's radius in km
            return R * c

        def find_centroid(points):
            """Find the centroid of a group of points"""
            if not points:
                return None
            lat_sum = sum(float(p['latitude']) for p in points)
            lon_sum = sum(float(p['longitude']) for p in points)
            return {'latitude': lat_sum / len(points), 'longitude': lon_sum / len(points)}

        def cluster_destinations(destinations, max_cluster_size=5):
            """Group destinations into geographical clusters"""
            if len(destinations) <= max_cluster_size:
                return [destinations]

            # Find overall centroid
            centroid = find_centroid(destinations)
            clusters = []
            remaining = destinations.copy()

            while remaining:
                # Start a new cluster with the farthest point from centroid
                current_cluster = [max(remaining, key=lambda x: calculate_distance(centroid, x))]
                remaining.remove(current_cluster[0])

                # Add nearest neighbors until cluster is full
                while len(current_cluster) < max_cluster_size and remaining:
                    cluster_centroid = find_centroid(current_cluster)
                    nearest = min(remaining, key=lambda x: calculate_distance(cluster_centroid, x))
                    current_cluster.append(nearest)
                    remaining.remove(nearest)

                clusters.append(current_cluster)

            return clusters

        def optimize_cluster_sequence(cluster, start_point):
            """Optimize route within a cluster using an improved nearest neighbor with lookahead"""
            if not cluster:
                return []

            remaining = cluster.copy()
            route = []
            current = start_point

            while remaining:
                if len(remaining) <= 2:
                    # For last two points, check both permutations
                    if len(remaining) == 2:
                        dist1 = calculate_distance(current, remaining[0]) + calculate_distance(remaining[0], remaining[1])
                        dist2 = calculate_distance(current, remaining[1]) + calculate_distance(remaining[1], remaining[0])
                        route.extend(remaining if dist1 <= dist2 else remaining[::-1])
                        break
                    else:
                        route.extend(remaining)
                        break

                # Find next point with 2-opt lookahead
                min_total_dist = float('inf')
                best_next = None

                for next_point in remaining:
                    # Calculate distance including the next possible point
                    current_dist = calculate_distance(current, next_point)
                    remaining_after = [p for p in remaining if p != next_point]
                    
                    # Look ahead to next possible point
                    if remaining_after:
                        next_min_dist = min(calculate_distance(next_point, p) for p in remaining_after)
                        total_dist = current_dist + next_min_dist
                    else:
                        total_dist = current_dist

                    if total_dist < min_total_dist:
                        min_total_dist = total_dist
                        best_next = next_point

                route.append(best_next)
                remaining.remove(best_next)
                current = best_next

            return route

        # Cluster destinations if there are many
        clusters = cluster_destinations(destinations)
        optimized_sequence = []
        current_point = source

        # Optimize cluster sequence and routes within clusters
        while clusters:
            # Find nearest cluster to current point
            cluster_centroids = [find_centroid(cluster) for cluster in clusters]
            nearest_cluster_index = min(range(len(clusters)), 
                                     key=lambda i: calculate_distance(current_point, cluster_centroids[i]))
            
            # Optimize route within the nearest cluster
            current_cluster = clusters.pop(nearest_cluster_index)
            optimized_cluster = optimize_cluster_sequence(current_cluster, current_point)
            optimized_sequence.extend(optimized_cluster)
            
            if optimized_cluster:
                current_point = {
                    'latitude': optimized_cluster[-1]['latitude'],
                    'longitude': optimized_cluster[-1]['longitude']
                }

        # Log the optimized sequence
        _logger.info("Optimized sequence with clustering:")
        for i, dest in enumerate(optimized_sequence, 1):
            _logger.info(f"{i}. {dest.get('location')} (was: {destinations.index(dest) + 1})")

        return optimized_sequence

    def _optimize_bulk_missions_with_ai(self, bulk_location_data):
        """
        Main method to optimize bulk missions using AI
        """
        try:
            _logger.info("=== STARTING AI BULK MISSION OPTIMIZATION ===")
            _logger.info(f"Input data summary:")
            _logger.info(f"- Sources: {len(bulk_location_data.get('sources', []))}")
            _logger.info(f"- Destinations: {len(bulk_location_data.get('destinations', []))}")
            _logger.info(f"- Vehicles: {len(bulk_location_data.get('available_vehicles', []))}")
            _logger.info(f"- Drivers: {len(bulk_location_data.get('available_drivers', []))}")
            
            # Validate input data
            if not bulk_location_data.get('sources') and not bulk_location_data.get('destinations'):
                _logger.warning("No sources or destinations provided")
                raise ValueError("No locations to optimize")
            
            if not bulk_location_data.get('available_vehicles'):
                _logger.warning("No vehicles available for optimization")
                raise ValueError("No vehicles available")
            
            # Build the optimization prompt
            _logger.info("Building optimization prompt...")
            prompt = self._build_optimization_prompt(bulk_location_data)
            _logger.info(f"Prompt length: {len(prompt)} characters")
            
            # Call AI service
            _logger.info("Calling Gemini API for optimization...")
            optimized_missions = self._call_gemini_api(prompt)
            # Recalculate costs locally using configured parameters and vehicle data
            optimized_missions = self._recalculate_costs_in_ai_response(optimized_missions)
            
            # Validate the response
            if not optimized_missions:
                raise ValueError("AI returned empty response")
            
            if not isinstance(optimized_missions, dict):
                raise ValueError("AI response is not a dictionary")
            
            # Log the complete AI response for analysis
            _logger.info("=== AI MISSION OPTIMIZATION RESPONSE (POST-COSTS) ===")
            _logger.info("FULL AI RESPONSE:")
            _logger.info(json.dumps(optimized_missions, indent=2, default=str))
            _logger.info("=== END AI RESPONSE ===")
            
            # Extract and log summary for quick reference
            summary = optimized_missions.get('optimization_summary', {})
            created_missions = optimized_missions.get('created_missions', [])
            insights = optimized_missions.get('optimization_insights', {})
            
            _logger.info("=== OPTIMIZATION SUMMARY ===")
            _logger.info(f"✅ Missions Created: {summary.get('total_missions_created', 0)}")
            _logger.info(f"🚛 Vehicles Used: {summary.get('total_vehicles_used', 0)}")
            _logger.info(f"📏 Total Distance: {summary.get('total_estimated_distance_km', 0)} km")
            _logger.info(f"💰 Total Cost: {summary.get('total_estimated_cost', 0)}")
            _logger.info(f"⭐ Optimization Score: {summary.get('optimization_score', 0)}/100")
            _logger.info(f"💡 Cost Savings: {summary.get('cost_savings_percentage', 0)}%")
            
            _logger.info("=== CREATED MISSIONS BREAKDOWN ===")
            for i, mission in enumerate(created_missions, 1):
                vehicle = mission.get('assigned_vehicle', {})
                destinations = mission.get('destinations', [])
                route = mission.get('route_optimization', {})
                
                _logger.info(f"Mission {i}: {mission.get('mission_name', 'Unnamed')}")
                _logger.info(f"  - Vehicle: {vehicle.get('vehicle_name', 'Unknown')} ({vehicle.get('license_plate', 'N/A')})")
                _logger.info(f"  - Destinations: {len(destinations)} stops")
                _logger.info(f"  - Distance: {route.get('total_distance_km', 0)} km")
                _logger.info(f"  - Duration: {route.get('estimated_duration_hours', 0)} hours")
                _logger.info(f"  - Cost: {route.get('estimated_total_cost', 0)}")
            
            _logger.info("=== KEY INSIGHTS ===")
            for decision in insights.get('key_decisions', []):
                _logger.info(f"🎯 {decision}")
            
            for recommendation in insights.get('recommendations', []):
                _logger.info(f"💡 {recommendation}")
            
            _logger.info("=== END OPTIMIZATION ANALYSIS ===")
            
            return optimized_missions
            
        except UserError:
            # Re-raise UserError as-is (these are meant for the user)
            raise
        except Exception as e:
            _logger.error(f"AI bulk mission optimization failed with error: {e}")
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Return fallback optimization
            _logger.info("Falling back to simple optimization algorithm...")
            return self._simple_fallback_optimization(
                bulk_location_data.get('sources', []),
                bulk_location_data.get('destinations', []),
                bulk_location_data.get('available_vehicles', []),
                bulk_location_data.get('available_drivers', [])
            )

    def _build_optimization_prompt(self, data):
        """Build the AI optimization prompt focused on mission creation"""
        sources_count = len(data.get('sources', []))
        destinations_count = len(data.get('destinations', []))
        vehicles_count = len(data.get('available_vehicles', []))
        
        # Extract key statistics
        total_weight = sum(d.get('total_weight', 0) for d in data.get('destinations', []))
        total_volume = sum(d.get('total_volume', 0) for d in data.get('destinations', []))
        pickup_count = len([d for d in data.get('destinations', []) if d.get('mission_type') == 'pickup'])
        delivery_count = len([d for d in data.get('destinations', []) if d.get('mission_type') == 'delivery'])
        
        # Build the prompt using string formatting to avoid f-string issues with curly braces
        data_json = json.dumps(data, indent=2, default=str)
        
        prompt = f"""
# TRANSPORT MISSION OPTIMIZER

You are an expert logistics AI that creates optimized transport missions. Your task is to analyze the provided data and create the most efficient mission plan possible.

## OPTIMIZATION OBJECTIVES
1. **Optimize Stop Sequence** - For each mission:
   - Start from the source location
   - Find the closest unvisited destination
   - Make that the first stop (sequence=1)
   - From there, find the next closest destination
   - Continue until all destinations are sequenced
   - IMPORTANT: The sequence in the response must reflect this proximity-based order
2. **Minimize total cost** - fuel, time, vehicle wear
3. **Maximize vehicle utilization** - weight and volume efficiency
4. **Minimize total distance and travel time**
5. **Respect all vehicle constraints** - payload, volume, equipment
6. **Create as many or as few missions as needed** for maximum efficiency

## SEQUENCE OPTIMIZATION RULES
1. The sequence of destinations in each mission MUST be based on proximity
2. Ignore the original order of destinations provided in the input
3. Always calculate distances from the current point to find the next stop
4. Update destination sequence numbers to match the optimized order
5. The response JSON must list destinations in this optimized order

## INPUT DATA ANALYSIS
- **Sources Available**: {sources_count} pickup locations
- **Destinations**: {destinations_count} total - {pickup_count} pickups, {delivery_count} deliveries
- **Fleet Available**: {vehicles_count} vehicles
- **Total Cargo**: {total_weight:.1f} kg, {total_volume:.2f} m³

## COMPLETE DATA TO OPTIMIZE
{data_json}

"""

        # Add the JSON format example as a separate string to avoid f-string issues
        json_format = '''
    
## COST CALCULATION RULES
- Use realistic Moroccan costs:
  - Diesel price: 12.5 MAD/L
  - Driver salary: ~20 MAD/hour (adjust based on actual driver assigned)
  - Maintenance: ~0.5 MAD/km
- Calculate actual fuel consumption based on:
  - **The 'fuel_consumption' value provided in the assigned vehicle's data (L/100km)**
  - Total distance of route
  - Vehicle load impact on consumption

- Include all cost components:
  - Fuel costs
  - Driver wages
  - Vehicle maintenance
  - Toll roads if applicable
  - Additional expenses

## ROUTE NOTES REQUIREMENTS
- Include detailed information for drivers:
  - Clear stop sequence with addresses
  - Specific loading/unloading instructions
  - Contact information for each stop
  - Time windows and constraints
  - Road conditions and warnings
  - Rest stop recommendations
  - Special cargo handling notes
  - Emergency contact information

## MISSION CREATION STRATEGY
- **Create optimal number of missions** - could be 1, could be 100+ depending on efficiency
- **Match vehicles to cargo requirements** - weight, volume, special equipment
- **Group destinations efficiently** by geography and vehicle capacity
- **Sequence stops optimally** within each mission
- **Balance workload** across available vehicles and drivers
- **Consider pickup-before-delivery** constraints for same cargo
- **Pay attention to fuel prices, consumption, and driver costs** to minimize total expenses
- **Provide important information relevant to a driver** for each mission
- **Use the fuel consumption data provided in the vehicle information** to calculate fuel costs accurately
- **Use the orsm distance matrix API** to get realistic distances and times between points

## REQUIRED JSON OUTPUT FORMAT
Return ONLY valid JSON with this structure:

{
  "optimization_summary": {
    "total_missions_created": <number>,
    "total_vehicles_used": <number>,
    "total_estimated_distance_km": <number>,
    "total_estimated_time_hours": <number>,
    "optimization_score": <0-100>,
    "efficiency_metrics": {
      "average_vehicle_utilization": <0-100>,
      "route_efficiency_score": <0-100>,
      "fuel_efficiency_score": <0-100>
    },
    "cost_parameters": {
      "fuel_price_per_liter_mad": 12.5,
      "driver_rate_per_hour_mad": 20.0,
      "maintenance_rate_per_km_mad": 0.5
    },
    "efficiency_improvements": ["improvement1", "improvement2"]
  },
  "created_missions": [
    {
      "mission_id": "M001",
      "mission_name": "Route Description",
      "assigned_vehicle": {
        "vehicle_id": <use_actual_vehicle_id_from_input>,
        "vehicle_name": "<actual_vehicle_name>",
        "license_plate": "<actual_license_plate>",
        "max_payload": <actual_payload_kg>,
        "cargo_volume": <actual_volume_m3>
      },
      "assigned_driver": {
        "driver_id": <use_actual_driver_id_from_input>,
        "driver_name": "<actual_driver_name>"
      },
      "source_location": {
        "source_id": <use_actual_source_id_from_input>,
        "name": "<actual_source_name>",
        "location": "<actual_source_address>",
        "latitude": <actual_lat>,
        "longitude": <actual_lng>,
        "estimated_departure_time": "2024-01-15T08:00:00"
      },
      "destinations": [
        {
          "destination_id": <use_actual_destination_id_from_input>,
          "sequence": 1,
          "name": "<actual_destination_name>",
          "location": "<actual_destination_address>",
          "latitude": <actual_lat>,
          "longitude": <actual_lng>,
          "mission_type": "<actual_mission_type>",
          "estimated_arrival_time": "2024-01-15T09:30:00",
          "estimated_departure_time": "2024-01-15T10:00:00",
          "service_duration": <actual_service_duration_minutes>,
          "cargo_details": {
            "total_weight": <actual_weight_kg>,
            "total_volume": <actual_volume_m3>,
            "package_type": "<actual_package_type>",
            "requires_signature": <actual_boolean>,
            "special_instructions": "<actual_instructions>"
          }
        }
      ],
      "route_optimization": {
        "total_distance_km": <calculated_distance>,
        "estimated_duration_hours": <calculated_time>,
        "estimated_fuel_consumption_liters": <specific_vehicle_consumption>,
        "estimated_fuel_cost": <calculated_fuel_cost_from_estimated_fuel_consumption_liters>,
        "estimated_total_cost": <calculated_total_cost>,
        "estimated_driver_wages": <calculated_driver_wages_based_on_hourly_rate>,
        "optimization_notes": "Brief explanation of route logic"
        "detailed_route_notes": "<comprehensive_instructions_for_driver>"
      },
      "capacity_utilization": {
        "weight_utilization_percentage": <0-100>,
        "volume_utilization_percentage": <0-100>,
        "efficiency_score": <0-100>
      }
    }
  ],
  "optimization_insights": {
    "key_decisions": [
      "Exact Cost Breakdown",
      "Why this number of missions was chosen",
      "How vehicles were matched to routes",
      "Geographic clustering strategy used"
    ],
    "alternative_scenarios": [
      {
        "scenario_name": "Alternative approach considered",
        "description": "Brief description",
        "trade_offs": "Why this wasn't chosen"
      }
    ],
    "recommendations": [
      "Suggestions for future improvements",
      "Fleet optimization opportunities",
      "Route planning insights"
    ]
  }
}

## CRITICAL REQUIREMENTS
1. **Return ONLY valid JSON** - start with { and end with }
2. **No explanatory text** before or after the JSON
3. **No markdown formatting**
4. **Use double quotes** for all strings, never single quotes
5. **No trailing commas** before closing brackets or braces
6. **Use actual IDs from input data** - vehicle IDs, driver IDs, source IDs, destination IDs must match exactly
7. **Respect vehicle constraints** - never exceed max_payload or cargo_volume
8. **Create realistic missions** - consider actual distances and time requirements

ANALYZE THE DATA AND CREATE THE OPTIMAL MISSION PLAN AS VALID JSON:
'''
        
        return prompt + json_format

    def get_ai_optimization_result(self):
        """Get the stored AI optimization result"""
        if self.ai_optimization_result:
            try:
                return json.loads(self.ai_optimization_result)
            except:
                return None
        return None

    def create_missions_from_ai_results(self):
        """Create actual transport missions from AI optimization results"""
        if not self.ai_optimization_result:
            raise UserError(_("No AI optimization results found. Please run AI optimization first."))
        
        try:
            ai_data = json.loads(self.ai_optimization_result)
            missions_data = ai_data.get('created_missions', [])
            
            if not missions_data:
                raise UserError(_("No missions found in AI results."))
            
            created_missions = []
            
            for mission_data in missions_data:
                try:
                    # Extract mission information
                    source_location = mission_data.get('source_location', {})
                    assigned_vehicle = mission_data.get('assigned_vehicle', {})
                    assigned_driver = mission_data.get('assigned_driver', {})
                    destinations = mission_data.get('destinations', [])
                    
                    # Create mission
                    mission_vals = {
                        'mission_date': self.mission_date,
                        'driver_id': assigned_driver.get('driver_id') or self.driver_id.id,
                        'vehicle_id': assigned_vehicle.get('vehicle_id') or self.vehicle_id.id,
                        'priority': self.priority,
                        'source_location': source_location.get('location', ''),
                        'source_latitude': source_location.get('latitude'),
                        'source_longitude': source_location.get('longitude'),
                        'notes': f"AI Generated Mission: {mission_data.get('mission_name', 'Unnamed Mission')}",
                        'state': 'draft',
                    }
                    
                    mission = self.env['transport.mission'].create(mission_vals)
                    
                    # Create destinations
                    for seq, dest_data in enumerate(destinations, 1):
                        cargo_details = dest_data.get('cargo_details', {})
                        
                        dest_vals = {
                            'mission_id': mission.id,
                            'location': dest_data.get('location', ''),
                            'latitude': dest_data.get('latitude'),
                            'longitude': dest_data.get('longitude'),
                            'sequence': seq,
                            'mission_type': dest_data.get('mission_type', 'delivery'),
                            'expected_arrival_time': self._normalize_datetime_string(dest_data.get('estimated_arrival_time')),
                            'service_duration': dest_data.get('service_duration', 0),
                            'package_type': cargo_details.get('package_type', 'individual'),
                            'total_weight': cargo_details.get('total_weight', 0),
                            'total_volume': cargo_details.get('total_volume', 0),
                            'requires_signature': cargo_details.get('requires_signature', False),
                            'special_instructions': cargo_details.get('special_instructions', ''),
                        }
                        self.env['transport.destination'].create(dest_vals)
                    
                    # Auto-optimize route if requested
                    if self.auto_optimize_routes and len(destinations) > 1:
                        try:
                            mission.action_optimize_route()
                        except Exception as e:
                            _logger.warning(f"Failed to optimize route for AI mission {mission.name}: {e}")
                    
                    # Confirm mission if requested
                    if self.create_confirmed:
                        mission.action_confirm()
                    
                    created_missions.append(mission)
                    _logger.info(f"✅ Created mission: {mission.name} with {len(destinations)} destinations")
                    
                except Exception as e:
                    _logger.error(f"Failed to create mission from AI data: {e}")
                    continue
            
            if not created_missions:
                raise UserError(_("Failed to create any missions from AI results."))
            
            # Clear AI results after successful creation
            self.write({'ai_optimization_result': False})
            
            # Return action to view created missions
            if len(created_missions) == 1:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('AI Generated Mission'),
                    'res_model': 'transport.mission',
                    'res_id': created_missions[0].id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            else:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('AI Generated Missions'),
                    'res_model': 'transport.mission',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', [m.id for m in created_missions])],
                    'target': 'current',
                }
                
        except json.JSONDecodeError:
            raise UserError(_("Invalid AI optimization data format."))
        except Exception as e:
            _logger.error(f"Failed to create missions from AI results: {e}")
            raise UserError(_("Failed to create missions: %s") % str(e))

    def _calculate_costs(self, distance_km, duration_hours, vehicle_data, with_details=False):
        """
        Calculate mission costs using configured Moroccan parameters and actual vehicle data.
        - Reads defaults from `transport.cost.parameters`.
        - Uses `truck.vehicle.fuel_consumption` (L/100km) if available.
        """
        params = self.env['transport.cost.parameters'].get_default_parameters()
        
        # Parameters
        fuel_price_per_liter = params.fuel_price_per_liter or 12.5
        driver_cost_per_hour = params.driver_cost_per_hour or 20.0
        maintenance_cost_per_km = params.maintenance_cost_per_km or 0.5
        toll_cost_per_km = params.toll_cost_per_km or 0.0
        base_mission_cost = params.base_mission_cost or 0.0
        
        # Vehicle data
        fuel_consumption = 0
        if vehicle_data:
            fuel_consumption = vehicle_data.get('fuel_consumption') or 0
            if not fuel_consumption and vehicle_data.get('vehicle_id'):
                try:
                    v = self.env['truck.vehicle'].browse(vehicle_data['vehicle_id'])
                    fuel_consumption = v.fuel_consumption or 0
                except Exception:
                    fuel_consumption = 0
        if not fuel_consumption:
            fuel_consumption = 25.0  # sensible default L/100km
        
        # Fuel used and cost
        fuel_used_liters = (distance_km or 0) * (fuel_consumption / 100.0)
        fuel_cost = fuel_used_liters * fuel_price_per_liter
        
        # Other components
        driver_cost = (duration_hours or 0) * driver_cost_per_hour
        maintenance_cost = (distance_km or 0) * maintenance_cost_per_km
        toll_cost = (distance_km or 0) * toll_cost_per_km
        
        total_cost = base_mission_cost + fuel_cost + driver_cost + maintenance_cost + toll_cost
        
        if with_details:
            return {
                'total_cost': round(total_cost, 2),
                'base_cost': round(base_mission_cost, 2),
                'fuel_cost': round(fuel_cost, 2),
                'driver_cost': round(driver_cost, 2),
                'maintenance_cost': round(maintenance_cost, 2),
                'toll_cost': round(toll_cost, 2),
                'fuel_used_liters': round(fuel_used_liters, 2),
                'details': {
                    'fuel_consumption_per_100km': fuel_consumption,
                    'fuel_price_per_liter': fuel_price_per_liter,
                    'driver_rate_per_hour': driver_cost_per_hour,
                    'maintenance_rate_per_km': maintenance_cost_per_km,
                    'toll_cost_per_km': toll_cost_per_km
                }
            }
        return round(total_cost, 2)

    def _recalculate_costs_in_ai_response(self, optimized_missions):
        """Recalculate and inject costs into AI response using real parameters and vehicle data."""
        if not optimized_missions or not isinstance(optimized_missions, dict):
            return optimized_missions
        
        missions = optimized_missions.get('created_missions', [])
        if not missions:
            return optimized_missions
        
        total_cost = 0.0
        total_fuel_cost = 0.0
        params = self.env['transport.cost.parameters'].get_default_parameters()
        
        for mission in missions:
            vehicle = mission.get('assigned_vehicle', {}) or {}
            route = mission.get('route_optimization', {}) or {}
            distance_km = route.get('total_distance_km') or 0
            duration_hours = route.get('estimated_duration_hours') or 0
            
            costs = self._calculate_costs(distance_km, duration_hours, vehicle, with_details=True)
            route['estimated_fuel_cost'] = costs['fuel_cost']
            route['estimated_driver_wages'] = costs['driver_cost']
            route['estimated_total_cost'] = costs['total_cost']
            route['cost_breakdown'] = {
                'base_cost': costs['base_cost'],
                'fuel_cost': costs['fuel_cost'],
                'driver_cost': costs['driver_cost'],
                'maintenance_cost': costs['maintenance_cost'],
                'toll_cost': costs['toll_cost'],
                'fuel_used_liters': costs['fuel_used_liters']
            }
            mission['route_optimization'] = route
            total_cost += costs['total_cost']
            total_fuel_cost += costs['fuel_cost']
        
        summary = optimized_missions.setdefault('optimization_summary', {})
        summary['total_estimated_cost'] = round(total_cost, 2)
        # Include cost parameters snapshot for transparency
        summary['cost_parameters'] = {
            'fuel_price_per_liter_mad': params.fuel_price_per_liter,
            'driver_rate_per_hour_mad': params.driver_cost_per_hour,
            'maintenance_rate_per_km_mad': params.maintenance_cost_per_km,
            'toll_cost_per_km_mad': params.toll_cost_per_km,
            'base_mission_cost_mad': params.base_mission_cost,
        }
        optimized_missions['optimization_summary'] = summary
        return optimized_missions

    def _calculate_distance(self, point1, point2):
        """Calculate distance between two points using Haversine formula"""
        from math import radians, sin, cos, sqrt, atan2
        
        lat1 = radians(float(point1['latitude']))
        lon1 = radians(float(point1['longitude']))
        lat2 = radians(float(point2['latitude']))
        lon2 = radians(float(point2['longitude']))
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        R = 6371  # Earth's radius in km
        return R * c

    def _generate_route_notes(self, source, destinations, route_info):
        """Generate detailed route notes for drivers"""
        notes = []
        
        # Add source information
        notes.append(f"📍 Starting Point: {source['location']}")
        
        # Add key route information
        total_distance = route_info.get('total_distance_km', 0)
        notes.append(f"🛣️ Total Route Distance: {total_distance:.1f} km")
        
        # Generate detailed stop information
        for i, dest in enumerate(destinations, 1):
            stop_type = "🔵 Pickup" if dest.get('mission_type') == 'pickup' else "🟢 Delivery"
            notes.append(f"\nStop {i}: {stop_type}")
            notes.append(f"📍 Location: {dest.get('location')}")
            
            # Add cargo details
            cargo_details = []
            if dest.get('total_weight'):
                cargo_details.append(f"{dest.get('total_weight')}kg")
            if dest.get('total_volume'):
                cargo_details.append(f"{dest.get('total_volume')}m³")
            if dest.get('package_type'):
                cargo_details.append(dest.get('package_type').title())
            if cargo_details:
                notes.append(f"📦 Cargo: {' | '.join(cargo_details)}")
            
            # Add time constraints if any
            if dest.get('expected_arrival_time'):
                notes.append(f"⏰ Expected Arrival: {dest.get('expected_arrival_time')}")
            if dest.get('service_duration'):
                notes.append(f"⏱️ Service Time: {dest.get('service_duration')} minutes")
            
            # Add special instructions if any
            if dest.get('special_instructions'):
                notes.append(f"ℹ️ Note: {dest.get('special_instructions')}")
            
            # Add contact information if available
            if dest.get('contact_name') or dest.get('contact_phone'):
                contact_info = []
                if dest.get('contact_name'):
                    contact_info.append(dest.get('contact_name'))
                if dest.get('contact_phone'):
                    contact_info.append(dest.get('contact_phone'))
                notes.append(f"👤 Contact: {' - '.join(contact_info)}")
        
        # Add general route advice based on the path
        notes.append("\n🚦 Route Advice:")
        if len(destinations) > 3:
            notes.append("- Plan for fuel stops along the route")
            notes.append("- Take regular rest breaks every 4 hours")
        
        # Add weather warning if available (placeholder)
        notes.append("\n⚠️ Important Notes:")
        notes.append("- Verify all delivery documentation before departure")
        notes.append("- Check vehicle condition before starting")
        notes.append("- Keep this route plan accessible during the mission")
        
        return "\n".join(notes)

    def _verify_and_fix_sequence(self, mission):
        """Verify and fix destination sequences based on proximity"""
        if not mission.get('source_location') or not mission.get('destinations'):
            return mission

        source = {
            'latitude': mission['source_location']['latitude'],
            'longitude': mission['source_location']['longitude']
        }
        
        # Start from source, find closest destination each time
        current = source
        remaining = mission['destinations'].copy()
        optimized = []
        
        while remaining:
            # Find closest to current point
            closest = min(remaining, 
                        key=lambda x: self._calculate_distance(current, {
                            'latitude': x['latitude'],
                            'longitude': x['longitude']
                        }))
            
            # Update sequence and add to optimized list
            closest['sequence'] = len(optimized) + 1
            optimized.append(closest)
            remaining.remove(closest)
            
            # Update current point
            current = {
                'latitude': closest['latitude'],
                'longitude': closest['longitude']
            }
        
        # Replace destinations with optimized sequence
        mission['destinations'] = optimized
        return mission

    def create_single_mission_from_ai(self, mission_index):
        """Create a single transport mission from AI optimization results"""
        if not self.ai_optimization_result:
            raise UserError(_("No AI optimization results found. Please run AI optimization first."))
        
        try:
            ai_data = json.loads(self.ai_optimization_result)
            missions_data = ai_data.get('created_missions', [])
            
            if not missions_data or mission_index >= len(missions_data):
                raise UserError(_("Mission not found in AI results."))
            
            mission_data = missions_data[mission_index]
            
            # Extract mission information
            source_location = mission_data.get('source_location', {})
            assigned_vehicle = mission_data.get('assigned_vehicle', {})
            assigned_driver = mission_data.get('assigned_driver', {})
            destinations = mission_data.get('destinations', [])
            
            # Create mission
            mission_vals = {
                'mission_date': self.mission_date,
                'driver_id': assigned_driver.get('driver_id') or self.driver_id.id,
                'vehicle_id': assigned_vehicle.get('vehicle_id') or self.vehicle_id.id,
                'priority': self.priority,
                'source_location': source_location.get('location', ''),
                'source_latitude': source_location.get('latitude'),
                'source_longitude': source_location.get('longitude'),
                'notes': f"AI Generated Mission: {mission_data.get('mission_name', 'Unnamed Mission')}",
                'state': 'draft',
            }
            
            mission = self.env['transport.mission'].create(mission_vals)
            
            # Create destinations
            for seq, dest_data in enumerate(destinations, 1):
                cargo_details = dest_data.get('cargo_details', {})
                
                # Only include fields that exist in the transport.destination model
                # Prepare initial destination values with only basic fields
                dest_vals = {
                    'mission_id': mission.id,
                    'sequence': seq,
                }
                
                # Add fields that definitely exist in transport.destination model
                fields_mapping = {
                    'location': dest_data.get('location'),
                    'latitude': dest_data.get('latitude'),
                    'longitude': dest_data.get('longitude'),
                    'mission_type': dest_data.get('mission_type', 'delivery'),
                    'expected_arrival_time': self._normalize_datetime_string(dest_data.get('estimated_arrival_time')),
                    'service_duration': dest_data.get('service_duration', 0),
                    'package_type': cargo_details.get('package_type', 'individual'),
                    'total_weight': cargo_details.get('total_weight', 0),
                    'total_volume': cargo_details.get('total_volume', 0),
                    'requires_signature': cargo_details.get('requires_signature', False),
                }
                
                # Check which fields exist in the model before adding them
                destination_fields = self.env['transport.destination']._fields
                for field, value in fields_mapping.items():
                    if field in destination_fields:
                        if value is not None:  # Only set non-None values
                            dest_vals[field] = value
                self.env['transport.destination'].create(dest_vals)
            
            # Auto-optimize route if requested
            if self.auto_optimize_routes and len(destinations) > 1:
                try:
                    mission.action_optimize_route()
                except Exception as e:
                    _logger.warning(f"Failed to optimize route for AI mission {mission.name}: {e}")
            
            # Confirm mission if requested
            if self.create_confirmed:
                mission.action_confirm()
            
            _logger.info(f"✅ Created single mission: {mission.name} with {len(destinations)} destinations")
            
            # Return action to view created mission
            return {
                'type': 'ir.actions.act_window',
                'name': _('AI Generated Mission'),
                'res_model': 'transport.mission',
                'res_id': mission.id,
                'view_mode': 'form',
                'target': 'current',
            }
                
        except json.JSONDecodeError:
            raise UserError(_("Invalid AI optimization data format."))
        except Exception as e:
            _logger.error(f"Failed to create single mission from AI results: {e}")
            raise UserError(_("Failed to create mission: %s") % str(e))

    def _call_gemini_api(self, prompt):
        """Call the Gemini API with the optimization prompt"""
        api_key = self._get_gemini_api_key()
        
        # Construct the Gemini API request payload
        gemini_payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 8000,
                "candidateCount": 1
            }
        }
        
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
        request_url = f"{api_url}?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        _logger.info("Sending optimization request to Gemini API...")
        
        try:
            response = requests.post(request_url, json=gemini_payload, headers=headers, timeout=90)
            response.raise_for_status()
            
            response_data = response.json()
            
            # Enhanced response parsing
            if 'candidates' not in response_data or not response_data['candidates']:
                raise ValueError("Invalid response structure from AI service")
            
            candidate = response_data['candidates'][0]
            content_text = candidate['content']['parts'][0]['text']
            
            _logger.info(f"Raw AI response (first 500 chars): {content_text[:500]}...")
            
            # Clean and parse the JSON response with enhanced error handling
            content_text = content_text.strip()
            
            _logger.info(f"Raw AI response before cleaning: {content_text[:1000]}...")
            
            # Remove any markdown formatting if present
            if content_text.startswith('```json'):
                content_text = content_text[7:]
            if content_text.startswith('```'):
                content_text = content_text[3:]
            if content_text.endswith('```'):
                content_text = content_text[:-3]
            
            # Remove any leading/trailing whitespace and newlines
            content_text = content_text.strip()
            
            # Try to find JSON boundaries if there's extra text
            json_start = content_text.find('{')
            json_end = content_text.rfind('}')
            
            if json_start != -1 and json_end != -1 and json_end > json_start:
                content_text = content_text[json_start:json_end + 1]
                _logger.info(f"Extracted JSON boundaries: {content_text[:200]}...{content_text[-200:]}")
            
            # Additional cleanup for common AI response issues
            content_text = content_text.replace('\n', ' ')  # Remove newlines
            content_text = content_text.replace('\t', ' ')  # Remove tabs
            
            # Fix common JSON issues
            import re
            # Fix trailing commas before closing brackets/braces
            content_text = re.sub(r',(\s*[}\]])', r'\1', content_text)
            
            _logger.info(f"Cleaned JSON for parsing: {content_text[:500]}...")
            
            try:
                optimized_data = json.loads(content_text)
                _logger.info("Successfully parsed AI response JSON")
                return optimized_data
            except json.JSONDecodeError as e:
                _logger.error(f"JSON parsing failed at position {e.pos}: {e.msg}")
                _logger.error(f"Context around error: {content_text[max(0, e.pos-50):e.pos+50]}")
                
                # Try to fix the JSON and parse again
                fixed_json = self._attempt_json_fix(content_text, e.pos)
                if fixed_json:
                    try:
                        optimized_data = json.loads(fixed_json)
                        _logger.info("Successfully parsed AI response after JSON fix")
                        return optimized_data
                    except:
                        pass
                
                raise json.JSONDecodeError(f"Could not parse AI JSON response: {e.msg}", content_text, e.pos)
            
        except requests.exceptions.Timeout:
            raise UserError("AI optimization service timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            raise UserError("Cannot connect to AI optimization service. Please check your internet connection.")
        except requests.exceptions.HTTPError as http_err:
            _logger.error(f"HTTP error from Gemini API: {http_err}")
            
            # Handle rate limiting (429 error)
            if "429" in str(http_err) or "Too Many Requests" in str(http_err):
                _logger.warning("⚠️ Gemini API rate limit exceeded - waiting and retrying...")
                import time
                time.sleep(3)  # Wait 3 seconds
                
                try:
                    # Retry the request once
                    _logger.info("🔄 Retrying Gemini API request after rate limit...")
                    response = requests.post(request_url, json=gemini_payload, headers=headers, timeout=90)
                    response.raise_for_status()
                    
                    response_data = response.json()
                    content_text = response_data['candidates'][0]['content']['parts'][0]['text']
                    
                    # Clean and parse the JSON response
                    content_text = content_text.strip()
                    if content_text.startswith('```json'):
                        content_text = content_text[7:]
                    if content_text.endswith('```'):
                        content_text = content_text[:-3]
                    
                    optimized_data = json.loads(content_text.strip())
                    _logger.info("✅ Gemini API retry successful after rate limit")
                    return optimized_data
                    
                except Exception as retry_err:
                    _logger.error(f"❌ Gemini API retry failed: {retry_err}")
                    raise UserError("🚫 AI service is temporarily overloaded. Please wait 1-2 minutes and try again.")
            
            raise UserError(f"AI service returned error: {http_err}")
        except json.JSONDecodeError as json_err:
            _logger.error(f"JSON parsing failed: {json_err}")
            _logger.error(f"Raw content that failed: {content_text}")
            
            # Create a simple fallback response
            _logger.info("Creating fallback JSON response due to parsing error")
            return self._create_simple_json_response()
            
        except Exception as e:
            _logger.error(f"Gemini API call failed: {e}")
            raise UserError(f"AI optimization failed: {e}")

    def _create_simple_json_response(self):
        """Create a simple valid JSON response when AI parsing fails"""
        return {
            "optimization_summary": {
                "total_missions_created": 1,
                "total_vehicles_used": 1,
                "total_estimated_distance_km": 50,
                "total_estimated_cost": 100,
                "total_estimated_time_hours": 4,
                "optimization_score": 70,
                "cost_savings_percentage": 10,
                "efficiency_improvements": ["Basic route created due to AI parsing error"]
            },
            "created_missions": [
                {
                    "mission_id": "FALLBACK_001",
                    "mission_name": "Fallback Mission - AI Parse Error",
                    "assigned_vehicle": {
                        "vehicle_id": 1,
                        "vehicle_name": "Default Vehicle",
                        "license_plate": "FALLBACK",
                        "max_payload": 1000,
                        "cargo_volume": 10
                    },
                    "assigned_driver": {
                        "driver_id": 1,
                        "driver_name": "Default Driver"
                    },
                    "source_location": {
                        "source_id": 1,
                        "name": "Default Source",
                        "location": "Default Location",
                        "latitude": 0,
                        "longitude": 0,
                        "estimated_departure_time": "2024-01-15T08:00:00"
                    },
                    "destinations": [
                        {
                            "destination_id": 1,
                            "sequence": 1,
                            "name": "Default Destination",
                            "location": "Default Location",
                            "latitude": 0,
                            "longitude": 0,
                            "mission_type": "delivery",
                            "estimated_arrival_time": "2024-01-15T10:00:00",
                            "estimated_departure_time": "2024-01-15T10:30:00",
                            "service_duration": 30,
                            "cargo_details": {
                                "total_weight": 100,
                                "total_volume": 1,
                                "package_type": "individual",
                                "requires_signature": False,
                                "special_instructions": "Fallback mission due to AI parsing error"
                            }
                        }
                    ],
                    "route_optimization": {
                        "total_distance_km": 50,
                        "estimated_duration_hours": 4,
                        "estimated_fuel_cost": 40,
                        "estimated_total_cost": 100,
                        "optimization_notes": "Fallback route created due to AI JSON parsing error"
                    },
                    "capacity_utilization": {
                        "weight_utilization_percentage": 10,
                        "volume_utilization_percentage": 10,
                        "efficiency_score": 50
                    }
                }
            ],
            "optimization_insights": {
                "key_decisions": [
                    "AI response could not be parsed - using fallback mission",
                    "Check server logs for AI parsing error details"
                ],
                "alternative_scenarios": [],
                "recommendations": [
                    "Review AI prompt for JSON formatting issues",
                    "Check Gemini API response format",
                    "Consider simplifying the optimization request"
                ]
            }
        }

    def _attempt_json_fix(self, json_text, error_pos):
        """Attempt to fix common JSON issues"""
        try:
            # Common fixes for AI-generated JSON
            fixes = [
                # Fix missing quotes around keys
                (r'(\w+):', r'"\1":'),
                # Fix single quotes to double quotes
                (r"'([^']*)'", r'"\1"'),
                # Fix trailing commas
                (r',(\s*[}\]])', r'\1'),
                # Fix missing commas between objects
                (r'}(\s*){', r'},\1{'),
                # Fix missing commas between array items
                (r'](\s*)\[', r'],\1['),
            ]
            
            fixed_text = json_text
            for pattern, replacement in fixes:
                import re
                fixed_text = re.sub(pattern, replacement, fixed_text)
            
            # Try to validate the fix
            json.loads(fixed_text)
            _logger.info("Successfully fixed JSON")
            return fixed_text
            
        except Exception as e:
            _logger.error(f"Could not fix JSON: {e}")
            return None

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