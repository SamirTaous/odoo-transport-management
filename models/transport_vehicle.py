# In: /home/samirtaous/transport_management/models/transport_vehicle.py

from odoo import models, fields, api

class TransportVehicle(models.Model):
    _name = 'transport.vehicle'
    _description = 'Transport Vehicle'
    _order = 'name'

    # This computed field creates a nice display name like "Volvo FH16 (TR-123-UCK)"
    name = fields.Char(string='Name', compute='_compute_name', store=True)
    
    license_plate = fields.Char(string='License Plate', required=True, copy=False)
    model_id = fields.Many2one('fleet.vehicle.model', string='Model')
    fuel_capacity = fields.Float(string='Fuel Capacity (Liters)')
    
    # A vehicle is often assigned a primary driver
    driver_id = fields.Many2one('res.partner', string='Assigned Driver', domain=[('is_company', '=', False)])
    
    image = fields.Image(string='Image')
    active = fields.Boolean(string='Active', default=True, help="Uncheck to archive the vehicle instead of deleting it.")

    # This ensures that each license plate is unique in the database
    _sql_constraints = [
        ('license_plate_uniq', 'unique (license_plate)', 'A vehicle with this license plate already exists!')
    ]

    # This is a compute method. It runs when its dependencies change.
    @api.depends('model_id.name', 'license_plate')
    def _compute_name(self):
        for vehicle in self:
            # Creates a name like "Scania R 450 (AB-123-CD)" if a model is set,
            # otherwise it just uses the license plate.
            if vehicle.model_id and vehicle.license_plate:
                vehicle.name = f"{vehicle.model_id.name} ({vehicle.license_plate})"
            else:
                vehicle.name = vehicle.license_plate