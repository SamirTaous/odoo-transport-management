# In: models/transport_destination.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class TransportDestination(models.Model):
    _name = 'transport.destination'
    _description = 'Transport Mission Destination'
    _order = 'sequence, id'

    mission_id = fields.Many2one('transport.mission', string='Mission', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # The 'location' field is now the human-readable address, often set by the map
    location = fields.Char(string='Destination Address', required=True)
    is_completed = fields.Boolean(string="Completed", default=False)

    # Coordinates
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    
    # Time constraints - simplified
    expected_arrival_time = fields.Datetime(string='Expected Arrival Time')
    service_duration = fields.Float(string='Service Duration (minutes)', default=15.0, help="Time needed to complete service at this destination")
    
    # Delivery requirements - simplified
    requires_signature = fields.Boolean(string='Requires Signature', default=False)
    
    # Package type
    package_type = fields.Selection([
        ('pallet', 'Pallet'),
        ('individual', 'Individual Packages')
    ], string='Package Type', default='individual', required=True)
    
    # Pallet information (when package_type = 'pallet')
    pallet_width = fields.Float(string='Pallet Width (cm)', digits=(8, 2))
    pallet_height = fields.Float(string='Pallet Height (cm)', digits=(8, 2))
    pallet_weight = fields.Float(string='Pallet Weight (kg)', digits=(8, 2))
    
    # Individual packages information (when package_type = 'individual')
    package_ids = fields.One2many('transport.package', 'destination_id', string='Packages')
    
    # Computed totals
    total_volume = fields.Float(string='Total Volume (m³)', compute='_compute_totals', store=True, digits=(8, 3))
    total_weight = fields.Float(string='Total Weight (kg)', compute='_compute_totals', store=True, digits=(8, 2))
    
    @api.depends('package_type', 'pallet_width', 'pallet_height', 'pallet_weight', 'package_ids.volume', 'package_ids.weight')
    def _compute_totals(self):
        for destination in self:
            if destination.package_type == 'pallet':
                # Calculate pallet volume: width * height * depth (assuming standard depth)
                if destination.pallet_width and destination.pallet_height:
                    # Convert cm to m and assume 120cm depth for standard pallet
                    volume = (destination.pallet_width / 100) * (destination.pallet_height / 100) * 1.2
                    destination.total_volume = volume
                else:
                    destination.total_volume = 0.0
                destination.total_weight = destination.pallet_weight or 0.0
            else:
                # Sum individual packages
                destination.total_volume = sum(destination.package_ids.mapped('volume'))
                destination.total_weight = sum(destination.package_ids.mapped('weight'))
    
    @api.constrains('pallet_width', 'pallet_height', 'pallet_weight', 'service_duration')
    def _check_positive_values(self):
        for destination in self:
            if destination.pallet_width and destination.pallet_width < 0:
                raise ValidationError("Pallet width cannot be negative.")
            if destination.pallet_height and destination.pallet_height < 0:
                raise ValidationError("Pallet height cannot be negative.")
            if destination.pallet_weight and destination.pallet_weight < 0:
                raise ValidationError("Pallet weight cannot be negative.")
            if destination.service_duration < 0:
                raise ValidationError("Service duration cannot be negative.")


class TransportPackage(models.Model):
    _name = 'transport.package'
    _description = 'Individual Package'
    _order = 'sequence, id'

    destination_id = fields.Many2one('transport.destination', string='Destination', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    name = fields.Char(string='Package Description', required=True)
    length = fields.Float(string='Length (cm)', digits=(8, 2), required=True)
    width = fields.Float(string='Width (cm)', digits=(8, 2), required=True)
    height = fields.Float(string='Height (cm)', digits=(8, 2), required=True)
    weight = fields.Float(string='Weight (kg)', digits=(8, 2), required=True)
    
    # Computed volume
    volume = fields.Float(string='Volume (m³)', compute='_compute_volume', store=True, digits=(8, 3))
    
    @api.depends('length', 'width', 'height')
    def _compute_volume(self):
        for package in self:
            if package.length and package.width and package.height:
                # Convert cm³ to m³
                volume_cm3 = package.length * package.width * package.height
                package.volume = volume_cm3 / 1000000  # Convert to m³
            else:
                package.volume = 0.0
    
    @api.constrains('length', 'width', 'height', 'weight')
    def _check_positive_dimensions(self):
        for package in self:
            if package.length <= 0:
                raise ValidationError("Package length must be positive.")
            if package.width <= 0:
                raise ValidationError("Package width must be positive.")
            if package.height <= 0:
                raise ValidationError("Package height must be positive.")
            if package.weight <= 0:
                raise ValidationError("Package weight must be positive.")