# In: /opt/odoo-16/custom_addons/transport_management/models/transport_destination.py

from odoo import models, fields

class TransportDestination(models.Model):
    _name = 'transport.destination'
    _description = 'Transport Destination'
    _order = 'sequence, id'

    mission_id = fields.Many2one('transport.mission', string='Mission', required=True, ondelete='cascade')
    location = fields.Char(string='Destination Point', required=True)
    sequence = fields.Integer(string='Order', default=10)