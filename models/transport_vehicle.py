from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta

class TransportVehicle(models.Model):
    _name = 'transport.vehicle'
    _description = 'Transport Truck'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Truck ID', required=True, copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True, tracking=True)
    image = fields.Image(string="Truck Image")
    
    # Basic Truck Information
    license_plate = fields.Char(string='License Plate', required=True, tracking=True)
    vin_number = fields.Char(string='VIN Number', help='Vehicle Identification Number')
    year = fields.Integer(string='Year', required=True)
    
    # Truck Brand and Model (Major truck manufacturers)
    brand = fields.Selection([
        ('volvo', 'Volvo'),
        ('scania', 'Scania'),
        ('mercedes', 'Mercedes-Benz'),
        ('man', 'MAN'),
        ('iveco', 'Iveco'),
        ('daf', 'DAF'),
        ('renault', 'Renault Trucks'),
        ('mack', 'Mack'),
        ('peterbilt', 'Peterbilt'),
        ('kenworth', 'Kenworth'),
        ('freightliner', 'Freightliner'),
        ('international', 'International'),
        ('isuzu', 'Isuzu'),
        ('hino', 'Hino'),
        ('fuso', 'Fuso'),
        ('other', 'Other')
    ], string='Brand', required=True, tracking=True)
    
    model_name = fields.Char(string='Model', required=True)
    
    # Ownership and Availability
    ownership_type = fields.Selection([
        ('owned', 'Company Owned'),
        ('rented', 'Rented'),
        ('subcontracted', 'Subcontracted')  # This is the term for borrowed/temporary trucks
    ], string='Ownership Type', required=True, default='owned', tracking=True)
    
    rental_start_date = fields.Date(string='Rental Start Date')
    rental_end_date = fields.Date(string='Rental End Date')
    rental_cost_per_day = fields.Monetary(string='Daily Rental Cost', currency_field='currency_id')
    subcontractor_id = fields.Many2one('res.partner', string='Subcontractor', 
                                     domain=[('is_company', '=', True)])
    
    # Driver Information
    driver_id = fields.Many2one('res.partner', string='Assigned Driver', 
                               domain=[('is_company', '=', False)], tracking=True)
    
    # Truck Specifications for Freight
    truck_type = fields.Selection([
        ('rigid', 'Rigid Truck'),
        ('articulated', 'Articulated (Tractor-Trailer)'),
        ('b_double', 'B-Double'),
        ('road_train', 'Road Train')
    ], string='Truck Type', required=True, default='rigid')
    
    # Cargo Capacity
    max_payload = fields.Float(string='Max Payload (kg)', required=True, 
                              help='Maximum weight capacity in kilograms')
    cargo_volume = fields.Float(string='Cargo Volume (m³)', required=True,
                               help='Maximum cargo volume in cubic meters')
    cargo_length = fields.Float(string='Cargo Length (m)', help='Cargo area length in meters')
    cargo_width = fields.Float(string='Cargo Width (m)', help='Cargo area width in meters')
    cargo_height = fields.Float(string='Cargo Height (m)', help='Cargo area height in meters')
    
    # Truck Dimensions
    overall_length = fields.Float(string='Overall Length (m)')
    overall_width = fields.Float(string='Overall Width (m)')
    overall_height = fields.Float(string='Overall Height (m)')
    gross_vehicle_weight = fields.Float(string='GVW (kg)', help='Gross Vehicle Weight in kg')
    
    # Engine and Performance
    engine_power = fields.Integer(string='Engine Power (HP)')
    fuel_type = fields.Selection([
        ('diesel', 'Diesel'),
        ('petrol', 'Petrol'),
        ('electric', 'Electric'),
        ('hybrid', 'Hybrid'),
        ('lng', 'LNG (Liquefied Natural Gas)'),
        ('cng', 'CNG (Compressed Natural Gas)')
    ], string='Fuel Type', default='diesel')
    fuel_capacity = fields.Float(string='Fuel Tank Capacity (L)')
    fuel_consumption = fields.Float(string='Fuel Consumption (L/100km)')
    
    # Special Equipment
    has_crane = fields.Boolean(string='Has Crane')
    has_tailgate = fields.Boolean(string='Has Tailgate Lift')
    has_refrigeration = fields.Boolean(string='Refrigerated')
    has_gps = fields.Boolean(string='GPS Tracking', default=True)
    special_equipment = fields.Text(string='Special Equipment')
    
    # Compliance and Documentation
    registration_expiry = fields.Date(string='Registration Expiry', tracking=True)
    insurance_expiry = fields.Date(string='Insurance Expiry', tracking=True)
    inspection_due = fields.Date(string='Next Inspection Due', tracking=True)
    
    # Financial
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id)
    purchase_price = fields.Monetary(string='Purchase Price', currency_field='currency_id')
    current_value = fields.Monetary(string='Current Value', currency_field='currency_id')
    
    # Relations
    mission_ids = fields.One2many('transport.mission', 'vehicle_id', string='Missions')
    mission_count = fields.Integer(string="Mission Count", compute='_compute_mission_count')
    company_id = fields.Many2one('res.company', string='Company', 
                                default=lambda self: self.env.company)
    
    # Computed Fields
    is_available = fields.Boolean(string='Available', compute='_compute_availability', store=True)
    rental_status = fields.Char(string='Rental Status', compute='_compute_rental_status')
    
    @api.depends('mission_ids')
    def _compute_mission_count(self):
        for vehicle in self:
            vehicle.mission_count = len(vehicle.mission_ids)
    
    @api.depends('ownership_type', 'rental_end_date', 'active')
    def _compute_availability(self):
        today = fields.Date.today()
        for vehicle in self:
            if not vehicle.active:
                vehicle.is_available = False
            elif vehicle.ownership_type == 'rented' and vehicle.rental_end_date:
                vehicle.is_available = vehicle.rental_end_date >= today
            else:
                vehicle.is_available = True
    
    @api.depends('ownership_type', 'rental_start_date', 'rental_end_date')
    def _compute_rental_status(self):
        today = fields.Date.today()
        for vehicle in self:
            if vehicle.ownership_type == 'owned':
                vehicle.rental_status = 'Company Owned'
            elif vehicle.ownership_type == 'subcontracted':
                vehicle.rental_status = 'Subcontracted'
            elif vehicle.ownership_type == 'rented':
                if not vehicle.rental_start_date or not vehicle.rental_end_date:
                    vehicle.rental_status = 'Rental - Dates Missing'
                elif today < vehicle.rental_start_date:
                    vehicle.rental_status = 'Rental - Future'
                elif today > vehicle.rental_end_date:
                    vehicle.rental_status = 'Rental - Expired'
                else:
                    days_left = (vehicle.rental_end_date - today).days
                    vehicle.rental_status = f'Rental - {days_left} days left'
            else:
                vehicle.rental_status = 'Unknown'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.vehicle.sequence') or 'New'
        return super().create(vals_list)
    
    @api.constrains('rental_start_date', 'rental_end_date', 'ownership_type')
    def _check_rental_dates(self):
        for vehicle in self:
            if vehicle.ownership_type == 'rented':
                if not vehicle.rental_start_date or not vehicle.rental_end_date:
                    raise ValidationError("Rental start date and end date are required for rented trucks.")
                if vehicle.rental_start_date >= vehicle.rental_end_date:
                    raise ValidationError("Rental end date must be after start date.")
    
    @api.constrains('max_payload', 'cargo_volume')
    def _check_capacity_values(self):
        for vehicle in self:
            if vehicle.max_payload <= 0:
                raise ValidationError("Maximum payload must be greater than 0.")
            if vehicle.cargo_volume <= 0:
                raise ValidationError("Cargo volume must be greater than 0.")
    
    @api.constrains('subcontractor_id', 'ownership_type')
    def _check_subcontractor(self):
        for vehicle in self:
            if vehicle.ownership_type == 'subcontracted' and not vehicle.subcontractor_id:
                raise ValidationError("Subcontractor company is required for subcontracted trucks.")
    
    @api.onchange('cargo_length', 'cargo_width', 'cargo_height')
    def _onchange_cargo_dimensions(self):
        if self.cargo_length and self.cargo_width and self.cargo_height:
            self.cargo_volume = self.cargo_length * self.cargo_width * self.cargo_height
        
    def action_view_missions(self):
        return {
            'name': 'Truck Missions',
            'type': 'ir.actions.act_window',
            'res_model': 'transport.mission',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', self.mission_ids.ids)],
            'context': {'default_vehicle_id': self.id}
        }
    
    def action_schedule_maintenance(self):
        """Action to schedule maintenance for the truck"""
        return {
            'name': 'Schedule Maintenance',
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_name': f'Maintenance for {self.name}',
                'default_equipment_id': self.id,
            }
        }
    
    def action_confirm_truck(self):
        """Confirm and activate the truck"""
        self.write({'active': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Truck Confirmed',
                'message': f'Truck {self.name} has been confirmed and activated.',
                'type': 'success',
                'sticky': False,
            }
        }