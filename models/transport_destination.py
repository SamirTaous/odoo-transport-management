# In: models/transport_destination.py
from odoo import models, fields

class TransportDestination(models.Model):
    _name = 'transport.destination'
    _description = 'Transport Mission Destination'
    _order = 'sequence, id'

    mission_id = fields.Many2one('transport.mission', string='Mission', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    location = fields.Char(string='Destination Point', required=True)
    is_completed = fields.Boolean(string="Completed", default=False)