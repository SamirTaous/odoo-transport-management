from odoo import models, fields, api

class TransportCostParameters(models.Model):
    _name = 'transport.cost.parameters'
    _description = 'Transport Cost Parameters'
    _rec_name = 'name'

    name = fields.Char(string='Parameter Set Name', required=True, default='Default Cost Parameters')
    active = fields.Boolean(default=True)
    
    # General costs (per mission)
    base_mission_cost = fields.Monetary(string='Base Mission Cost', currency_field='currency_id', 
                                       help='Fixed cost per mission regardless of distance')
    
    # Distance-based costs
    cost_per_km = fields.Monetary(string='Cost per KM', currency_field='currency_id',
                                 help='Variable cost per kilometer traveled')
    
    # Time-based costs
    cost_per_hour = fields.Monetary(string='Cost per Hour', currency_field='currency_id',
                                   help='Cost per hour of mission duration')
    
    # Fuel costs
    fuel_price_per_liter = fields.Monetary(string='Fuel Price per Liter', currency_field='currency_id',
                                          help='Current fuel price per liter')
    
    # Driver costs
    driver_cost_per_hour = fields.Monetary(string='Driver Cost per Hour', currency_field='currency_id',
                                          help='Driver hourly rate including benefits')
    
    # Additional costs
    toll_cost_per_km = fields.Monetary(string='Toll Cost per KM', currency_field='currency_id',
                                      help='Average toll cost per kilometer')
    insurance_cost_per_mission = fields.Monetary(string='Insurance Cost per Mission', currency_field='currency_id',
                                                help='Insurance cost allocated per mission')
    maintenance_cost_per_km = fields.Monetary(string='Maintenance Cost per KM', currency_field='currency_id',
                                             help='Maintenance cost per kilometer')
    
    # Currency
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self._get_mad_currency())
    
    # Company
    company_id = fields.Many2one('res.company', string='Company', 
                                default=lambda self: self.env.company)
    
    def _get_mad_currency(self):
        """Get MAD currency or fallback to company currency"""
        mad_currency = self.env['res.currency'].search([('name', '=', 'MAD')], limit=1)
        return mad_currency if mad_currency else self.env.company.currency_id

    @api.model
    def get_default_parameters(self):
        """Get the default active cost parameters"""
        params = self.search([('active', '=', True)], limit=1)
        if not params:
            # Create default parameters if none exist
            params = self.create({
                'name': 'Morocco Transport Cost Parameters 2024',
                'base_mission_cost': 50.0,
                'cost_per_km': 1.2,
                'cost_per_hour': 25.0,
                'fuel_price_per_liter': 13.2,
                'driver_cost_per_hour': 15.0,
                'toll_cost_per_km': 0.3,
                'insurance_cost_per_mission': 20.0,
                'maintenance_cost_per_km': 0.4,
            })
        return params