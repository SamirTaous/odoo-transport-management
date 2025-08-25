from odoo import models, fields, api

class TransportVehicleCompat(models.Model):
    """
    Compatibility model to handle existing references during migration
    This model will be removed after full migration to truck.vehicle
    """
    _name = 'transport.vehicle'
    _description = 'Transport Vehicle (Compatibility)'
    _auto = False  # Don't create a table
    
    # Delegate all operations to truck.vehicle
    def _get_truck_vehicle(self):
        return self.env['truck.vehicle']
    
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # Redirect search to truck.vehicle
        truck_model = self.env['truck.vehicle']
        return truck_model.search(args, offset=offset, limit=limit, order=order, count=count)
    
    @api.model
    def browse(self, ids):
        # Redirect browse to truck.vehicle
        return self.env['truck.vehicle'].browse(ids)
    
    @api.model
    def create(self, vals):
        # Redirect create to truck.vehicle
        return self.env['truck.vehicle'].create(vals)
    
    def write(self, vals):
        # Redirect write to truck.vehicle
        truck_records = self.env['truck.vehicle'].browse(self.ids)
        return truck_records.write(vals)
    
    def unlink(self):
        # Redirect unlink to truck.vehicle
        truck_records = self.env['truck.vehicle'].browse(self.ids)
        return truck_records.unlink()