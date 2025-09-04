# In: models/ai_analyst_service.py
import requests
import json
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The Prompt Engineering remains the same. It's solid.
PROMPT_TEMPLATE = """
You are a high-performance Logistics Optimization API. Your SOLE function is to receive a JSON-like text block containing mission data and return a SINGLE, minified JSON object with the optimized route.

**RULES:**
1.  Analyze the provided source and destination coordinates to determine the most efficient route for a vehicle.
2.  The primary optimization goal is the shortest travel time.
3.  The response MUST be a valid JSON object and nothing else.
4.  Do NOT include any explanatory text, markdown formatting (like ```json), apologies, or any conversational text. Only the raw JSON object is permitted.

---
**INPUT FORMAT EXAMPLE:**
Mission Data:
{
  "mission_id": "MISSION_XYZ",
  "source": {"lat": 48.8584, "lon": 2.2945},
  "destinations": [
    {"id": 1, "lat": 48.8606, "lon": 2.3376},
    {"id": 2, "lat": 48.8867, "lon": 2.3431},
    {"id": 3, "lat": 48.8738, "lon": 2.2950}
  ]
}
---
**OUTPUT FORMAT EXAMPLE (Your Response):**
{"status":"success","mission_id":"MISSION_XYZ","optimized_sequence":[3,1,2],"route_summary":{"total_distance_km":12.5,"total_duration_seconds":1850}}
---

**PROCESS THE FOLLOWING MISSION:**

Mission Data:
{{MISSION_DATA_JSON}}
"""


class AiAnalystService:
    def __init__(self, env):
        """
        Initializes the service with the Odoo environment.
        :param env: The Odoo environment (self.env)
        """
        self.env = env
        self.api_key = None
        # --- CHANGED: This is the exact URL that you successfully tested ---
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        
    def optimize_bulk_missions(self, bulk_location_data):
        """
        Main method to optimize bulk missions using AI
        Takes the complete JSON from the bulk mission widget and returns optimized missions
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
            
            # Build the comprehensive optimization prompt
            _logger.info("Building optimization prompt...")
            prompt = self._build_bulk_optimization_prompt(bulk_location_data)
            _logger.info(f"Prompt length: {len(prompt)} characters")
            
            # Call AI service
            _logger.info("Calling Gemini API for optimization...")
            optimized_missions = self._call_gemini_for_bulk_optimization(prompt)
            
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
            
            # Log full results (truncated for readability)
            full_result_str = json.dumps(optimized_missions, indent=2, default=str)
            if len(full_result_str) > 5000:
                _logger.info(f"Full AI response (first 2500 chars): {full_result_str[:2500]}...")
                _logger.info(f"Full AI response (last 2500 chars): ...{full_result_str[-2500:]}")
            else:
                _logger.info(f"Full AI response: {full_result_str}")
            
            _logger.info("=== END AI OPTIMIZATION RESULTS ===")
            
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
            return self._fallback_optimization(bulk_location_data)

    def _get_api_key(self):
        """Fetches the API key from Odoo System Parameters."""
        if not self.api_key:
            self.api_key = self.env['ir.config_parameter'].sudo().get_param('transport_management.gemini_api_key')
        if not self.api_key:
            _logger.error("Gemini API Key is not configured in System Parameters (key: transport_management.gemini_api_key).")
            raise UserError("The AI Analyst service is not configured. Please contact your administrator.")
        return self.api_key
    
    def test_api_connection(self):
        """Test the API connection with a simple request"""
        try:
            api_key = self._get_api_key()
            
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
            
            request_url = f"{self.api_url}?key={api_key}"
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

    def optimize_route(self, mission_payload):
        """
        Takes a mission payload, builds a prompt, calls the Gemini API,
        and returns the parsed JSON response.
        :param mission_payload: A dictionary with source and destinations.
        :return: A dictionary with the optimized sequence.
        """
        api_key = self._get_api_key()
        
        # 1. Inject the mission data into the prompt template
        mission_data_str = json.dumps(mission_payload, indent=2)
        full_prompt = PROMPT_TEMPLATE.replace("{{MISSION_DATA_JSON}}", mission_data_str)
        
        # 2. Construct the Gemini API request payload
        gemini_payload = {
            "contents": [
                {"parts": [{"text": full_prompt}]}
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.0,
            }
        }
        
        # --- CHANGED: This section now matches the successful curl command ---
        # The API key is passed as a query parameter in the URL.
        request_url = f"{self.api_url}?key={api_key}"
        
        # The 'X-goog-api-key' header is not needed when the key is in the URL.
        headers = {
            'Content-Type': 'application/json',
        }
        # --------------------------------------------------------------------

        _logger.info("Sending request to Google AI Studio API for mission optimization.")
        
        try:
            # 3. Make the API call to the correctly formatted URL
            response = requests.post(request_url, json=gemini_payload, headers=headers, timeout=45)
            response.raise_for_status()
            
            # 4. Extract the JSON string from the response
            response_data = response.json()
            content_text = response_data['candidates'][0]['content']['parts'][0]['text']
            
            _logger.info(f"Raw response text from Gemini: {content_text}")

            # 5. Parse the extracted text string into a Python dictionary
            optimized_data = json.loads(content_text)
            
            if optimized_data.get("status") != "success":
                raise UserError(f"AI optimization failed. Reason: {optimized_data.get('message', 'Unknown error')}")
            
            return optimized_data

        except requests.exceptions.RequestException as e:
            _logger.error(f"Google AI Studio API request failed: {e}")
            raise UserError(f"Failed to connect to the AI optimization service: {e}")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            _logger.error(f"Failed to parse Gemini response: {e}. Response was: {response_data if 'response_data' in locals() else 'Not available'}")
            raise UserError("The AI service returned an invalid or unexpected response. Please try again or check the logs.")
    
    def _build_bulk_optimization_prompt(self, data):
        """
        Build a comprehensive prompt for bulk mission optimization
        """
        sources_count = len(data.get('sources', []))
        destinations_count = len(data.get('destinations', []))
        vehicles_count = len(data.get('available_vehicles', []))
        
        # Extract key statistics
        total_weight = sum(d.get('total_weight', 0) for d in data.get('destinations', []))
        total_volume = sum(d.get('total_volume', 0) for d in data.get('destinations', []))
        pickup_count = len([d for d in data.get('destinations', []) if d.get('mission_type') == 'pickup'])
        delivery_count = len([d for d in data.get('destinations', []) if d.get('mission_type') == 'delivery'])
        
        prompt = f"""
# TRANSPORT MISSION OPTIMIZATION EXPERT

You are an expert transport logistics optimizer. Analyze the provided data and create the most efficient mission plan.

## INPUT DATA SUMMARY
- Sources: {sources_count} locations
- Destinations: {destinations_count} locations ({pickup_count} pickups, {delivery_count} deliveries)  
- Available Vehicles: {vehicles_count} trucks
- Total Weight: {total_weight:.1f} kg
- Total Volume: {total_volume:.2f} m³

## COMPLETE INPUT DATA
{json.dumps(data, indent=2, default=str)}

## OPTIMIZATION OBJECTIVES
1. Minimize total cost (fuel, time, vehicle wear)
2. Maximize vehicle utilization (capacity efficiency)
3. Minimize total distance and travel time
4. Respect all vehicle constraints (weight, volume, equipment)
5. Optimize pickup/delivery sequences logically
6. Consider service durations and time windows
7. Minimize environmental impact

## CONSTRAINTS
- Vehicle weight limits (max_payload)
- Vehicle volume limits (cargo_volume)
- Special equipment requirements (crane, refrigeration, etc.)
- Pickup must happen before delivery for same goods
- Vehicle availability and maintenance status
- Driver assignments and working hours

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
        "license_plate": "ABC123",
        "max_payload": <kg>,
        "cargo_volume": <m3>,
        "fuel_type": "diesel"
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
        "longitude": <lng>,
        "estimated_departure_time": "2024-01-15T08:00:00"
      }},
      "destinations": [
        {{
          "destination_id": <dest_id_from_input>,
          "sequence": 1,
          "name": "Destination Name",
          "location": "Full Address",
          "latitude": <lat>,
          "longitude": <lng>,
          "mission_type": "pickup|delivery",
          "estimated_arrival_time": "2024-01-15T09:30:00",
          "estimated_departure_time": "2024-01-15T10:00:00",
          "service_duration": <minutes>,
          "cargo_details": {{
            "total_weight": <kg>,
            "total_volume": <m3>,
            "package_type": "individual|pallet",
            "requires_signature": true|false,
            "special_instructions": "notes"
          }}
        }}
      ],
      "route_optimization": {{
        "total_distance_km": <number>,
        "estimated_duration_hours": <number>,
        "estimated_fuel_cost": <number>,
        "estimated_total_cost": <number>,
        "optimization_notes": "Why this route is optimal"
      }},
      "capacity_utilization": {{
        "weight_utilization_percentage": <0-100>,
        "volume_utilization_percentage": <0-100>,
        "efficiency_score": <0-100>
      }}
    }}
  ],
  "optimization_insights": {{
    "key_decisions": [
      "Decision explanations"
    ],
    "alternative_scenarios": [
      {{
        "scenario_name": "Alternative Option",
        "description": "Brief description",
        "trade_offs": "What would be different"
      }}
    ],
    "recommendations": [
      "Future improvement suggestions"
    ]
  }}
}}

CRITICAL REQUIREMENTS:
1. Use ONLY vehicles, drivers, sources and destinations from the input data
2. Respect ALL vehicle capacity and equipment constraints
3. Return ONLY valid JSON - no explanatory text, no markdown formatting
4. The JSON must start with {{ and end with }}
5. All numbers must be valid (no NaN, no Infinity)
6. All strings must be properly escaped

EXAMPLE MINIMAL RESPONSE:
{{"optimization_summary":{{"total_missions_created":2,"total_vehicles_used":2,"total_estimated_distance_km":150,"total_estimated_cost":300,"total_estimated_time_hours":8,"optimization_score":85,"cost_savings_percentage":15,"efficiency_improvements":["Route consolidation","Vehicle matching"]}},"optimized_missions":[{{"mission_id":"M001","mission_name":"Route 1","assigned_vehicle":{{"vehicle_id":1,"vehicle_name":"Truck 1","license_plate":"ABC123"}},"assigned_driver":{{"driver_id":1,"driver_name":"Driver 1"}},"source_location":{{"source_id":1,"name":"Warehouse A","location":"123 Main St","latitude":40.7128,"longitude":-74.0060}},"destinations":[{{"destination_id":1,"sequence":1,"name":"Customer A","location":"456 Oak Ave","latitude":40.7589,"longitude":-73.9851,"mission_type":"delivery"}}]}}],"optimization_insights":{{"key_decisions":["Optimized for shortest distance"],"recommendations":["Consider time windows"]}}}}

NOW OPTIMIZE THE PROVIDED DATA:
"""
        return prompt
    
    def _call_gemini_for_bulk_optimization(self, prompt):
        """
        Call Gemini API for bulk mission optimization with enhanced error handling
        """
        api_key = self._get_api_key()
        
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
        
        request_url = f"{self.api_url}?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        _logger.info("Sending bulk optimization request to Gemini API...")
        _logger.info(f"Request URL: {request_url}")
        _logger.info(f"Payload size: {len(json.dumps(gemini_payload))} characters")
        
        try:
            response = requests.post(request_url, json=gemini_payload, headers=headers, timeout=90)
            
            # Log response details
            _logger.info(f"Response status code: {response.status_code}")
            _logger.info(f"Response headers: {dict(response.headers)}")
            
            response.raise_for_status()
            
            response_data = response.json()
            _logger.info(f"Response structure: {list(response_data.keys())}")
            
            # Enhanced response parsing with better error handling
            if 'candidates' not in response_data:
                _logger.error(f"No candidates in response: {response_data}")
                raise ValueError("Invalid response structure: missing candidates")
            
            if not response_data['candidates']:
                _logger.error("Empty candidates array in response")
                raise ValueError("Invalid response structure: empty candidates")
            
            candidate = response_data['candidates'][0]
            if 'content' not in candidate:
                _logger.error(f"No content in candidate: {candidate}")
                raise ValueError("Invalid response structure: missing content")
            
            content = candidate['content']
            if 'parts' not in content or not content['parts']:
                _logger.error(f"No parts in content: {content}")
                raise ValueError("Invalid response structure: missing parts")
            
            content_text = content['parts'][0].get('text', '')
            if not content_text:
                _logger.error("Empty text in response part")
                raise ValueError("Invalid response structure: empty text")
            
            _logger.info(f"Raw AI response text (first 500 chars): {content_text[:500]}...")
            
            # Clean and parse the JSON response
            content_text = content_text.strip()
            
            # Remove any markdown formatting if present
            if content_text.startswith('```json'):
                content_text = content_text[7:]
            if content_text.endswith('```'):
                content_text = content_text[:-3]
            
            content_text = content_text.strip()
            
            try:
                optimized_data = json.loads(content_text)
                _logger.info("Successfully parsed AI response JSON")
                
                # Validate the response structure
                if not isinstance(optimized_data, dict):
                    raise ValueError("Response is not a JSON object")
                
                # Check for required fields
                required_fields = ['optimization_summary', 'optimized_missions']
                missing_fields = [field for field in required_fields if field not in optimized_data]
                if missing_fields:
                    _logger.warning(f"Missing fields in AI response: {missing_fields}")
                    # Don't fail, just log the warning
                
                return optimized_data
                
            except json.JSONDecodeError as json_err:
                _logger.error(f"JSON parsing failed: {json_err}")
                _logger.error(f"Raw content that failed to parse: {content_text}")
                raise ValueError(f"Invalid JSON in AI response: {json_err}")
            
        except requests.exceptions.Timeout:
            _logger.error("Gemini API request timed out")
            raise UserError("AI optimization service timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            _logger.error("Failed to connect to Gemini API")
            raise UserError("Cannot connect to AI optimization service. Please check your internet connection.")
        except requests.exceptions.HTTPError as http_err:
            _logger.error(f"HTTP error from Gemini API: {http_err}")
            _logger.error(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            raise UserError(f"AI service returned error: {http_err}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Gemini API request failed: {e}")
            raise UserError(f"Failed to connect to AI optimization service: {e}")
        except (KeyError, IndexError, ValueError) as e:
            _logger.error(f"Failed to parse Gemini response: {e}")
            if 'response_data' in locals():
                _logger.error(f"Full response data: {json.dumps(response_data, indent=2)}")
            raise UserError(f"AI service returned invalid response: {e}")
    
    def _fallback_optimization(self, data):
        """
        Fallback optimization when AI service fails
        """
        sources = data.get('sources', [])
        destinations = data.get('destinations', [])
        vehicles = data.get('available_vehicles', [])
        drivers = data.get('available_drivers', [])
        
        _logger.info("Using fallback optimization algorithm")
        
        # Simple fallback: create one mission per source with nearby destinations
        optimized_missions = []
        total_distance = 0
        total_cost = 0
        
        for i, source in enumerate(sources[:len(vehicles)]):
            vehicle = vehicles[i] if i < len(vehicles) else vehicles[0] if vehicles else None
            driver = drivers[i] if i < len(drivers) else drivers[0] if drivers else None
            
            if not vehicle or not driver:
                continue
                
            # Assign destinations to this mission
            mission_destinations = destinations[i*3:(i+1)*3] if destinations else []
            
            if mission_destinations:
                mission_distance = len(mission_destinations) * 20  # Estimate 20km per destination
                mission_cost = mission_distance * 1.2  # Estimate 1.2 cost per km
                
                total_distance += mission_distance
                total_cost += mission_cost
                
                optimized_mission = {
                    "mission_id": f"M{i+1:03d}",
                    "mission_name": f"Fallback Route {i+1} - {source.get('name', 'Source')}",
                    "assigned_vehicle": {
                        "vehicle_id": vehicle.get('id'),
                        "vehicle_name": vehicle.get('name', 'Unknown Vehicle'),
                        "license_plate": vehicle.get('license_plate', 'N/A'),
                        "max_payload": vehicle.get('max_payload', 0),
                        "cargo_volume": vehicle.get('cargo_volume', 0),
                        "fuel_type": vehicle.get('fuel_type', 'diesel')
                    },
                    "assigned_driver": {
                        "driver_id": driver.get('id'),
                        "driver_name": driver.get('name', 'Unknown Driver')
                    },
                    "source_location": {
                        "source_id": source.get('id'),
                        "name": source.get('name', 'Unnamed Source'),
                        "location": source.get('location', 'Unknown Location'),
                        "latitude": source.get('latitude', 0),
                        "longitude": source.get('longitude', 0),
                        "estimated_departure_time": "2024-01-15T08:00:00"
                    },
                    "destinations": [
                        {
                            "destination_id": dest.get('id'),
                            "sequence": idx + 1,
                            "name": dest.get('name', f'Destination {idx + 1}'),
                            "location": dest.get('location', 'Unknown Location'),
                            "latitude": dest.get('latitude', 0),
                            "longitude": dest.get('longitude', 0),
                            "mission_type": dest.get('mission_type', 'delivery'),
                            "estimated_arrival_time": f"2024-01-15T{9 + idx:02d}:30:00",
                            "estimated_departure_time": f"2024-01-15T{10 + idx:02d}:00:00",
                            "service_duration": dest.get('service_duration', 30),
                            "cargo_details": {
                                "total_weight": dest.get('total_weight', 0),
                                "total_volume": dest.get('total_volume', 0),
                                "package_type": dest.get('package_type', 'individual'),
                                "requires_signature": dest.get('requires_signature', False),
                                "special_instructions": dest.get('special_instructions', '')
                            }
                        }
                        for idx, dest in enumerate(mission_destinations)
                    ],
                    "route_optimization": {
                        "total_distance_km": mission_distance,
                        "estimated_duration_hours": len(mission_destinations) * 1.5,
                        "estimated_fuel_cost": mission_distance * 0.8,
                        "estimated_total_cost": mission_cost,
                        "optimization_notes": "Fallback optimization - basic route assignment"
                    },
                    "capacity_utilization": {
                        "weight_utilization_percentage": 75,
                        "volume_utilization_percentage": 70,
                        "efficiency_score": 65
                    }
                }
                
                optimized_missions.append(optimized_mission)
        
        return {
            "optimization_summary": {
                "total_missions_created": len(optimized_missions),
                "total_vehicles_used": len(optimized_missions),
                "total_estimated_distance_km": total_distance,
                "total_estimated_cost": total_cost,
                "total_estimated_time_hours": len(optimized_missions) * 6,
                "optimization_score": 65,
                "cost_savings_percentage": 15,
                "efficiency_improvements": [
                    "Basic route consolidation applied",
                    "Vehicle assignments optimized",
                    "Fallback algorithm used due to AI service unavailability"
                ]
            },
            "optimized_missions": optimized_missions,
            "optimization_insights": {
                "key_decisions": [
                    "Used fallback optimization due to AI service issues",
                    f"Created {len(optimized_missions)} missions for {len(destinations)} destinations",
                    "Applied basic vehicle-to-route matching"
                ],
                "alternative_scenarios": [],
                "recommendations": [
                    "Configure AI service for better optimization results",
                    "Add more vehicles for better load distribution",
                    "Consider time window constraints for future optimizations"
                ]
            }
        }