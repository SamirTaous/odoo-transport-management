# In: models/transport_destination.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class TransportDestination(models.Model):
    _name = 'transport.destination'
    _description = 'Transport Mission Destination'
    _order = 'sequence, id'

    mission_id = fields.Many2one('transport.mission', string='Mission', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Mission type moved from mission to destination level
    mission_type = fields.Selection([
        ('pickup', 'Pickup'),
        ('delivery', 'Delivery')
    ], string='Type', required=True, default='delivery', tracking=True)
    
    # The 'location' field is now the human-readable address, often set by the map
    location = fields.Char(string='Destination Address', required=True)
    is_completed = fields.Boolean(string="Completed", default=False)

    # Coordinates
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    
    # Time constraints - simplified
    expected_arrival_time = fields.Datetime(string='Expected Arrival Time')
    service_duration = fields.Float(string='Service Duration (minutes)', default=15.0, help="Time needed to complete service at this destination")
    
    # Computed time fields
    estimated_arrival_time = fields.Datetime(string='Estimated Arrival Time', compute='_compute_estimated_times', store=True, help="Calculated arrival time based on route and previous stops")
    estimated_departure_time = fields.Datetime(string='Estimated Departure Time', compute='_compute_estimated_times', store=True, help="Estimated departure time after service")
    
    # Delivery requirements and instructions
    requires_signature = fields.Boolean(string='Requires Signature', default=False)
    special_instructions = fields.Text(string='Special Instructions', help="Any special handling or delivery instructions")
    contact_name = fields.Char(string='Contact Name', help="Name of the contact person at destination")
    contact_phone = fields.Char(string='Contact Phone', help="Phone number of the contact person")
    priority_delivery = fields.Boolean(string='Priority Delivery', default=False, help="Mark if this delivery has high priority")
    
    # Package type
    package_type = fields.Selection([
        ('pallet', 'Pallet'),
        ('individual', 'Individual Packages')
    ], string='Package Type', default='individual', required=True)
    
    # Pallet information (when package_type = 'pallet')
    pallet_width = fields.Float(string='Pallet Width (cm)', digits=(8, 2))
    pallet_length = fields.Float(string='Pallet Length (cm)', digits=(8, 2))
    pallet_height = fields.Float(string='Pallet Height (cm)', digits=(8, 2))
    pallet_weight = fields.Float(string='Pallet Weight (kg)', digits=(8, 2))
    
    # Individual packages information (when package_type = 'individual')
    package_ids = fields.One2many('transport.package', 'destination_id', string='Packages')
    
    # Computed totals
    total_volume = fields.Float(string='Total Volume (m³)', compute='_compute_totals', store=True, digits=(8, 3))
    total_weight = fields.Float(string='Total Weight (kg)', compute='_compute_totals', store=True, digits=(8, 2))
    
    @api.depends('package_type', 'pallet_width', 'pallet_length', 'pallet_height', 'pallet_weight', 'package_ids.volume', 'package_ids.weight')
    def _compute_totals(self):
        for destination in self:
            if destination.package_type == 'pallet':
                # Calculate pallet volume: width * length * height (cm -> m³)
                if destination.pallet_width and destination.pallet_length and destination.pallet_height:
                    destination.total_volume = (
                        (destination.pallet_width / 100.0)
                        * (destination.pallet_length / 100.0)
                        * (destination.pallet_height / 100.0)
                    )
                else:
                    destination.total_volume = 0.0
                destination.total_weight = destination.pallet_weight or 0.0
            else:
                # Sum individual packages
                destination.total_volume = sum(destination.package_ids.mapped('volume'))
                destination.total_weight = sum(destination.package_ids.mapped('weight'))
    
    @api.depends('mission_id.mission_date', 'mission_id.estimated_duration_minutes', 'sequence', 'service_duration')
    def _compute_estimated_times(self):
        for destination in self:
            if not destination.mission_id or not destination.mission_id.mission_date:
                destination.estimated_arrival_time = False
                destination.estimated_departure_time = False
                continue
            
            from datetime import datetime, timedelta
            
            # Default to 8 AM on mission date
            mission_date = destination.mission_id.mission_date
            # Convert mission date to datetime (assume 8 AM start)
            if isinstance(mission_date, str):
                mission_datetime = datetime.strptime(mission_date, '%Y-%m-%d').replace(hour=8)
            else:
                mission_datetime = datetime.combine(mission_date, datetime.min.time().replace(hour=8))
            
            # Calculate cumulative time to reach this destination
            cumulative_minutes = 0
            
            # Get all previous destinations (including this one) sorted by sequence
            previous_destinations = destination.mission_id.destination_ids.filtered(
                lambda d: d.sequence <= destination.sequence
            ).sorted('sequence')
            
            # Calculate time based on route segments and service times
            if destination.mission_id.estimated_duration_minutes and len(previous_destinations) > 0:
                # Distribute travel time proportionally among destinations
                total_destinations = len(destination.mission_id.destination_ids)
                if total_destinations > 0:
                    travel_time_per_segment = destination.mission_id.estimated_duration_minutes / total_destinations
                    
                    # Add travel time for each segment up to this destination
                    cumulative_minutes += travel_time_per_segment * destination.sequence
                    
                    # Add service time for all previous destinations (not including current)
                    for prev_dest in previous_destinations:
                        if prev_dest.sequence < destination.sequence:
                            cumulative_minutes += prev_dest.service_duration or 0
            
            # Calculate estimated arrival and departure times
            destination.estimated_arrival_time = mission_datetime + timedelta(minutes=cumulative_minutes)
            destination.estimated_departure_time = destination.estimated_arrival_time + timedelta(minutes=destination.service_duration or 0)
    
    @api.constrains('expected_arrival_time')
    def _check_future_time(self):
        from datetime import datetime
        
        for destination in self:
            if destination.expected_arrival_time:
                # Use naive datetime for comparison (Odoo stores datetimes as naive UTC)
                now = datetime.utcnow()
                expected_time = destination.expected_arrival_time
                
                # Convert to naive datetime if timezone-aware
                if expected_time.tzinfo is not None:
                    expected_time = expected_time.replace(tzinfo=None)
                
                if expected_time < now:
                    raise ValidationError("Expected arrival time cannot be in the past.")
    
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