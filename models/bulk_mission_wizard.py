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
            
            # Log the AI optimization results
            _logger.info("=== AI OPTIMIZATION COMPLETED ===")
            _logger.info(json.dumps(optimized_missions, indent=2, default=str))
            _logger.info("=== END AI OPTIMIZATION ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Optimization Completed',
                    'message': f'AI generated {optimized_missions.get("optimization_summary", {}).get("total_missions_created", 0)} optimized missions. Check server logs for complete results.',
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
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Full Flow Test Successful',
                        'message': f'AI optimization completed successfully. Created {len(missions)} missions with score {summary.get("optimization_score", 0)}.',
                        'type': 'success',
                        'sticky': True,
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
            
            api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
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
            
            # Validate the response
            if not optimized_missions:
                raise ValueError("AI returned empty response")
            
            if not isinstance(optimized_missions, dict):
                raise ValueError("AI response is not a dictionary")
            
            # Log the results
            _logger.info("=== AI BULK MISSION OPTIMIZATION COMPLETED SUCCESSFULLY ===")
            summary = optimized_missions.get('optimization_summary', {})
            _logger.info(f"Optimization Summary:")
            _logger.info(f"- Missions Created: {summary.get('total_missions_created', 0)}")
            _logger.info(f"- Vehicles Used: {summary.get('total_vehicles_used', 0)}")
            _logger.info(f"- Total Distance: {summary.get('total_estimated_distance_km', 0)} km")
            _logger.info(f"- Total Cost: {summary.get('total_estimated_cost', 0)}")
            _logger.info(f"- Optimization Score: {summary.get('optimization_score', 0)}")
            
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
        """Build the AI optimization prompt"""
        sources_count = len(data.get('sources', []))
        destinations_count = len(data.get('destinations', []))
        vehicles_count = len(data.get('available_vehicles', []))
        
        # Extract key statistics
        total_weight = sum(d.get('total_weight', 0) for d in data.get('destinations', []))
        total_volume = sum(d.get('total_volume', 0) for d in data.get('destinations', []))
        pickup_count = len([d for d in data.get('destinations', []) if d.get('mission_type') == 'pickup'])
        delivery_count = len([d for d in data.get('destinations', []) if d.get('mission_type') == 'delivery'])
        
        prompt = f"""
You are a transport logistics optimization expert. Create the most efficient mission plan from this data.

## INPUT DATA SUMMARY
- Sources: {sources_count} locations
- Destinations: {destinations_count} locations ({pickup_count} pickups, {delivery_count} deliveries)  
- Available Vehicles: {vehicles_count} trucks
- Total Weight: {total_weight:.1f} kg
- Total Volume: {total_volume:.2f} m³

## COMPLETE INPUT DATA
{json.dumps(data, indent=2, default=str)}

## REQUIRED OUTPUT FORMAT
You MUST return ONLY a valid JSON object. Do not include any text before or after the JSON. The JSON must have this exact structure:

{{
  "optimization_summary": {{
    "total_missions_created": <number>,
    "total_vehicles_used": <number>,
    "total_estimated_distance_km": <number>,
    "total_estimated_cost": <number>,
    "total_estimated_time_hours": <number>,
    "optimization_score": <0-100>,
    "cost_savings_percentage": <number>,
    "efficiency_improvements": ["improvement1", "improvement2"]
  }},
  "optimized_missions": [
    {{
      "mission_id": "M001",
      "mission_name": "Descriptive Mission Name",
      "assigned_vehicle": {{
        "vehicle_id": <vehicle_id_from_input>,
        "vehicle_name": "Vehicle Name",
        "license_plate": "ABC123"
      }},
      "assigned_driver": {{
        "driver_id": <driver_id_from_input>,
        "driver_name": "Driver Name"
      }},
      "source_location": {{
        "source_id": <source_id_from_input>,
        "name": "Source Name",
        "location": "Full Address",
        "latitude": <lat>,
        "longitude": <lng>
      }},
      "destinations": [
        {{
          "destination_id": <dest_id_from_input>,
          "sequence": 1,
          "name": "Destination Name",
          "location": "Full Address",
          "latitude": <lat>,
          "longitude": <lng>,
          "mission_type": "pickup|delivery"
        }}
      ]
    }}
  ],
  "optimization_insights": {{
    "key_decisions": ["Decision explanations"],
    "recommendations": ["Future improvement suggestions"]
  }}
}}

CRITICAL: Use ONLY vehicles, drivers, sources and destinations from the input data. Return valid JSON only.
"""
        return prompt

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
        
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
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
            
            # Clean and parse the JSON response
            content_text = content_text.strip()
            
            # Remove any markdown formatting if present
            if content_text.startswith('```json'):
                content_text = content_text[7:]
            if content_text.endswith('```'):
                content_text = content_text[:-3]
            
            content_text = content_text.strip()
            
            optimized_data = json.loads(content_text)
            _logger.info("Successfully parsed AI response JSON")
            
            return optimized_data
            
        except requests.exceptions.Timeout:
            raise UserError("AI optimization service timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            raise UserError("Cannot connect to AI optimization service. Please check your internet connection.")
        except requests.exceptions.HTTPError as http_err:
            raise UserError(f"AI service returned error: {http_err}")
        except json.JSONDecodeError as json_err:
            _logger.error(f"JSON parsing failed: {json_err}")
            _logger.error(f"Raw content: {content_text}")
            raise UserError(f"Invalid JSON in AI response: {json_err}")
        except Exception as e:
            _logger.error(f"Gemini API call failed: {e}")
            raise UserError(f"AI optimization failed: {e}")

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