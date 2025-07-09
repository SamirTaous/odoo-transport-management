from odoo import models, fields, api

class TransportVehicle(models.Model):
    _name = 'transport.vehicle'
    _description = 'Transport Vehicle'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    image = fields.Image(string="Image")
    model_id = fields.Many2one('fleet.vehicle.model', string='Model', required=True)
    license_plate = fields.Char(string='License Plate', required=True)
    driver_id = fields.Many2one('res.partner', string='Assigned Driver', domain=[('is_company', '=', False)])
    fuel_capacity = fields.Float(string='Fuel Capacity (Liters)')
    mission_ids = fields.One2many('transport.mission', 'vehicle_id', string='Missions')
    mission_count = fields.Integer(string="Mission Count", compute='_compute_mission_count')
    
    # --- ADD THIS FIELD ---
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        default=lambda self: self.env.company
    )
    
    @api.depends('mission_ids')
    def _compute_mission_count(self):
        for vehicle in self:
            vehicle.mission_count = len(vehicle.mission_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.vehicle.sequence') or 'New'
        return super().create(vals_list)
        
    def action_view_missions(self):
        return {
            'name': 'Missions',
            'type': 'ir.actions.act_window',
            'res_model': 'transport.mission',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', self.mission_ids.ids)],
            'context': {'default_vehicle_id': self.id}
        }