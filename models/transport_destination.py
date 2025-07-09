# In: models/transport_destination.py
from odoo import models, fields

class TransportDestination(models.Model):
    _name = 'transport.destination'
    _description = 'Transport Mission Destination'
    _order = 'sequence, id'

    mission_id = fields.Many2one('transport.mission', string='Mission', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # The 'location' field is now the human-readable address, often set by the map
    location = fields.Char(string='Destination Address', required=True)
    is_completed = fields.Boolean(string="Completed", default=False)

    # --- ADD THESE FIELDS ---
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))