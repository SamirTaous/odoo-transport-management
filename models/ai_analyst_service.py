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

    def _get_api_key(self):
        """Fetches the API key from Odoo System Parameters."""
        if not self.api_key:
            self.api_key = self.env['ir.config_parameter'].sudo().get_param('transport_management.gemini_api_key')
        if not self.api_key:
            _logger.error("Gemini API Key is not configured in System Parameters (key: transport_management.gemini_api_key).")
            raise UserError("The AI Analyst service is not configured. Please contact your administrator.")
        return self.api_key

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