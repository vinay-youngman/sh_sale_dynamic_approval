from odoo import api, fields, tools, models, _
from datetime import datetime


class RejectionReasonWizard(models.TransientModel):
    _inherit = 'sh.reject.reason.wizard'
    _description = "Reject reason wizard"

    # name = fields.Char(string="Reason", required=True)

    def action_reject_order(self):

        active_obj = self.env[self.env.context.get('active_model')].browse(
            self.env.context.get('active_id'))
        
        if self.env.context.get('active_model') == 'sale.order':

            active_obj.write({
            'reject_reason': self.name,
            'reject_by': active_obj.env.user,
            'rejection_date': datetime.now(),
            'state': 'reject',
            })

            template_id = active_obj.env.ref(
                "sh_sale_dynamic_approval.email_template_reject_sh_sale_order")
            if template_id:
                template_id.sudo().send_mail(active_obj.id, force_send=True, email_values={
                    'email_from': active_obj.env.user.email, 'email_to': active_obj.user_id.email})
            notifications = []
            if active_obj.user_id:
            
                notifications.append(
                                (active_obj.user_id.partner_id, 'sh_notification_info', 
                                {'title': _('Notitification'),
                                'message': 'Dear SalesPerson your order %s is rejected' % (active_obj.name)
                                }))
                active_obj.env['bus.bus']._sendmany(notifications)
            
        return super(RejectionReasonWizard,self).action_reject_order()
