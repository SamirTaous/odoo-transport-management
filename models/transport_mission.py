# In: models/transport_mission.py
from odoo import models, fields, api, _

class TransportMission(models.Model):
    _name = 'transport.mission'
    _description = 'Transport Mission'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'mission_date desc, priority desc, name desc' # Updated default order

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    mission_date = fields.Date(string='Date', required=True, tracking=True, default=fields.Date.context_today)
    source_location = fields.Char(string='Source Location', tracking=True)
    destination_ids = fields.One2many('transport.destination', 'mission_id', string='Destinations')
    driver_id = fields.Many2one('res.partner', string='Driver', tracking=True, domain=[('is_company', '=', False)])
    vehicle_id = fields.Many2one('transport.vehicle', string='Vehicle', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], default='draft', string='Status', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    notes = fields.Text(string='Internal Notes', tracking=True)

    # --- NEW & IMPROVED FIELDS ---
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'High')
    ], string='Priority', default='0')
    
    destination_progress = fields.Float(
        string="Destination Progress", 
        compute='_compute_destination_progress',
        store=True,
        help="Progress of completed destinations for this mission."
    )

    @api.depends('destination_ids.is_completed')
    def _compute_destination_progress(self):
        for mission in self:
            total_destinations = len(mission.destination_ids)
            if not total_destinations:
                mission.destination_progress = 0.0
            else:
                completed_count = len(mission.destination_ids.filtered(lambda d: d.is_completed))
                mission.destination_progress = (completed_count / total_destinations) * 100

    # Odoo sequence creation remains the same
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.mission.sequence') or _('New')
        return super().create(vals_list)

    # State transition methods remain the same
    def action_confirm(self):
        self.write({'state': 'confirmed'})
    def action_start_mission(self):
        self.write({'state': 'in_progress'})
    def action_done(self):
        self.write({'state': 'done'})
    def action_cancel(self):
        self.write({'state': 'cancelled'})
    def action_reset_to_draft(self):
        self.write({'state': 'draft'})