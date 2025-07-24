# In: models/transport_mission.py

# --- Imports are correct ---
import requests
import json
import logging
from . import ai_analyst_service

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from math import radians, sin, cos, sqrt, atan2

# --- Logger is correct ---
_logger = logging.getLogger(__name__)

# --- Helper function is correct ---
def _haversine_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    r = 6371
    return c * r

class TransportMission(models.Model):
    _name = 'transport.mission'
    _description = 'Transport Mission'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'mission_date desc, priority desc, name desc'

    # --- All fields are correct ---
    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    mission_date = fields.Date(string='Date', required=True, tracking=True, default=fields.Date.context_today)
    source_location = fields.Char(string='Source Location', tracking=True)
    source_latitude = fields.Float(string='Source Latitude', digits=(10, 7))
    source_longitude = fields.Float(string='Source Longitude', digits=(10, 7))
    destination_ids = fields.One2many('transport.destination', 'mission_id', string='Destinations')
    driver_id = fields.Many2one('res.partner', string='Driver', tracking=True, domain=[('is_company', '=', False)])
    vehicle_id = fields.Many2one('transport.vehicle', string='Vehicle', tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('in_progress', 'In Progress'), ('done', 'Done'), ('cancelled', 'Cancelled')], default='draft', string='Status', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    notes = fields.Text(string='Internal Notes', tracking=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'High')], string='Priority', default='0')
    destination_progress = fields.Float(string="Destination Progress", compute='_compute_destination_progress', store=True, help="Progress of completed destinations for this mission.")
    total_distance_km = fields.Float(string="Total Distance (km)", compute='_compute_total_distance', store=True, help="Estimated total travel distance for the mission.")

    # --- All standard methods are correct ---
    @api.depends('source_latitude', 'source_longitude', 'destination_ids.latitude', 'destination_ids.longitude', 'destination_ids.sequence')
    def _compute_total_distance(self):
        for mission in self:
            distance = 0.0
            if mission.source_latitude and mission.source_longitude:
                points = [(mission.source_latitude, mission.source_longitude)]
                sorted_destinations = mission.destination_ids.sorted('sequence')
                for dest in sorted_destinations:
                    if dest.latitude and dest.longitude:
                        points.append((dest.latitude, dest.longitude))
                if len(points) > 1:
                    for i in range(len(points) - 1):
                        p1, p2 = points[i], points[i+1]
                        distance += _haversine_distance(p1[0], p1[1], p2[0], p2[1])
            mission.total_distance_km = distance
            
    @api.depends('destination_ids.is_completed')
    def _compute_destination_progress(self):
        for mission in self:
            total_destinations = len(mission.destination_ids)
            if not total_destinations:
                mission.destination_progress = 0.0
            else:
                completed_count = len(mission.destination_ids.filtered(lambda d: d.is_completed))
                mission.destination_progress = (completed_count / total_destinations) * 100

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.mission.sequence') or _('New')
        return super().create(vals_list)

    def action_confirm(self): self.write({'state': 'confirmed'})
    def action_start_mission(self): self.write({'state': 'in_progress'})
    def action_done(self): self.write({'state': 'done'})
    def action_cancel(self): self.write({'state': 'cancelled'})
    def action_reset_to_draft(self): self.write({'state': 'draft'})

    # --- THIS IS THE FINAL, CORRECTED OPTIMIZATION ACTION ---
    def action_optimize_route(self):
        self.ensure_one()

        if len(self.destination_ids) < 2:
            raise UserError("Optimization requires at least two destinations.")

        destinations_payload = [
            {'id': dest.id, 'lat': dest.latitude, 'lon': dest.longitude}
            for dest in self.destination_ids
        ]
        mission_payload = {
            'mission_id': self.name or f'mission_{self.id}',
            'source': {'lat': self.source_latitude, 'lon': self.source_longitude},
            'destinations': destinations_payload,
        }

        try:
            analyst = ai_analyst_service.AiAnalystService(self.env)
            optimized_data = analyst.optimize_route(mission_payload)
            
            optimized_ids = optimized_data.get('optimized_sequence')
            if not optimized_ids:
                raise UserError("AI response did not contain a valid 'optimized_sequence'.")

            with self.env.cr.savepoint():
                for new_sequence, dest_id in enumerate(optimized_ids, start=1):
                    self.env['transport.destination'].browse(dest_id).write({'sequence': new_sequence})
            
            if optimized_data.get('route_summary'):
                self.write({
                    'total_distance_km': optimized_data['route_summary'].get('total_distance_km', self.total_distance_km)
                })
            
            # --- THIS IS THE NEW, CORRECT WAY TO SHOW A SUCCESS MESSAGE ---
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Success"),
                    'message': _("The route has been optimized successfully."),
                    'type': 'success',
                    'sticky': False,
                }
            }
            # -----------------------------------------------------------------
            
        except UserError as e:
            raise e
        except Exception as e:
            _logger.error(f"An unexpected error occurred during route optimization for mission {self.id}: {e}")
            raise UserError(f"An unexpected error occurred: {e}")