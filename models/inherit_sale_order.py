from odoo import api, fields, tools, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import json

from odoo.addons.ym_beta_updates.models.sale_order_inherit import get_customer_master_id_from_pan,get_beta_customer_id_and_status

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    approval_level_id = fields.Many2one(
        'sh.sale.approval.config', string="Approval Level", compute="compute_approval_level")
    approval_remarks = fields.Char(string="Approval Remark")
    state = fields.Selection(
        selection_add=[('waiting_for_approval', 'Waiting for Approval'), ('reject', 'Reject'), ('sale',)])
    level = fields.Integer(string="Next Approval Level", readonly=True)
    user_ids = fields.Many2many('res.users', string="Users", readonly=True)
    group_ids = fields.Many2many('res.groups', string="Groups", readonly=True)
    is_boolean = fields.Boolean(
        string="Boolean", compute="compute_is_boolean", search='_search_is_boolean')
    approval_info_line = fields.One2many(
        'sh.approval.info', 'sale_order_id', readonly=True)
    rejection_date = fields.Datetime(string="Reject Date", readonly=True)
    reject_by = fields.Many2one('res.users', string="Reject By", readonly=True)
    reject_reason = fields.Char(string="Reject Reason", readonly=True)
    is_sale_order_approval_required = fields.Boolean(string='IS SALE ORDER APPROVAL REQUIRED', default=True)

    def compute_is_boolean(self):

        if self.env.user.id in self.user_ids.ids or any(item in self.env.user.groups_id.ids for item in self.group_ids.ids):
            self.is_boolean = True
        else:
            self.is_boolean = False

    def _search_is_boolean(self, operator, value):
        results = []

        if value:
            so_ids = self.env['sale.order'].search([])
            if so_ids:
                for so in so_ids:
                    if self.env.user.id in so.user_ids.ids or any(item in self.env.user.groups_id.ids for item in so.group_ids.ids):
                        results.append(so.id)
        return [('id', 'in', results)]

    def action_confirm(self):
        self.check_customer_status()
        template_id = self.env.ref(
            "sh_sale_dynamic_approval.email_template_sh_sale_order")

        if self.approval_level_id.sale_approval_line:
            self.write({
                'state': 'waiting_for_approval'
            })
            lines = self.approval_level_id.sale_approval_line

            self.approval_info_line = False
            for line in lines:
                dictt = []
                if line.approve_by == 'group':
                    dictt.append((0, 0, {
                        'level': line.level,
                        'user_ids': False,
                        'group_ids': [(6, 0, line.group_ids.ids)],
                    }))

                if line.approve_by == 'user' and self.job_order is False:
                    dictt.append((0, 0, {
                        'level': line.level,
                        'user_ids': [(6, 0, line.user_ids.ids)],
                        'group_ids': False,
                    }))

                self.update({
                    'approval_info_line': dictt
                })

            if lines[0].approve_by == 'group':
                self.write({
                    'level': lines[0].level,
                    'group_ids': [(6, 0, lines[0].group_ids.ids)],
                    'user_ids': False
                })

                users = self.env['res.users'].search(
                    [('groups_id', 'in', lines[0].group_ids.ids)])

                if template_id and users:
                    for user in users:
                        template_id.sudo().send_mail(self.id, force_send=True, email_values={
                            'email_from': self.env.user.email, 'email_to': user.email})

                notifications = []
                if users:
                    for user in users:
                        notifications.append(
                            (user.partner_id, 'sh_notification_info', 
                            {'title': _('Notitification'),
                             'message': 'You have approval notification for sale order %s' % (self.name)
                            }))
                    self.env['bus.bus']._sendmany(notifications)

            if lines[0].approve_by == 'user' and self.job_order is False:
                self.write({
                    'level': lines[0].level,
                    'user_ids': [(6, 0, lines[0].user_ids.ids)],
                    'group_ids': False
                })

                if template_id and lines[0].user_ids:
                    for user in lines[0].user_ids:
                        template_id.sudo().send_mail(self.id, force_send=True, email_values={
                            'email_from': self.env.user.email, 'email_to': user.email})

                notifications = []
                if lines[0].user_ids:
                    for user in lines[0].user_ids:
                        notifications.append(
                            (user.partner_id, 'sh_notification_info', 
                            {'title': _('Notitification'),
                             'message': 'You have approval notification for sale order %s' % (self.name)
                            }))
                    self.env['bus.bus']._sendmany(notifications)

        else:
            super(SaleOrder, self).action_confirm()

    def check_customer_status(self):
        if self.customer_branch.parent_id.vat:
            try:
                connection = self._get_connection()
                connection.autocommit = False
                cursor = connection.cursor()
                cursor.execute(get_customer_master_id_from_pan(), [self.customer_branch.parent_id.vat])
                result = cursor.fetchall()
                if result:
                    customer_master_id_at_beta, status = result[0]

                    if status != 'UNBLOCK':
                        raise UserError("This customer is in {} status".format(status))

            except Exception as e:
                raise UserError(str(e))

    @api.depends('amount_untaxed' ,'freight_amount')
    def compute_approval_level(self):
        is_freight_approval_required = False
        is_order_amount_approval_required = False
        is_order_line_amount_approval_required = False
        self.is_sale_order_approval_required = False

        if self.order_line:

            if (self.freight_amount < 0.90 * self.computed_freight_amount):
                is_freight_approval_required = True

            pricelist_id = self.pricelist_id.id
            for order_line in self.order_line:
                product_id = order_line.product_id.id
                product_data = self.env['product.pricelist.item'].sudo().search(
                    [('pricelist_id', '=', pricelist_id), ('product_id', '=', product_id)], limit=1)

                unit_price = product_data.fixed_price if product_data else self.env['product.product'].search(
                    [('id', '=', product_id)], limit=1).list_price

                current_price = order_line.price_unit
                if current_price < unit_price:
                    if (self.price_type == 'daily' and current_price < unit_price / 30) or (self.price_type == 'monthly'):
                        is_order_line_amount_approval_required = True
            
            tax_totals_json = json.loads(self.tax_totals_json)
            if tax_totals_json.get('amount_untaxed')-self.freight_amount < self.partner_id.min_order_approval_amount:
                is_order_amount_approval_required = True

        sale_approvals = None

        if is_freight_approval_required or is_order_amount_approval_required or is_order_line_amount_approval_required:
            sale_approvals = self.env['sh.sale.approval.config'].search([
                ('is_freight', '=', is_freight_approval_required),
                ('is_min_price', '=', is_order_line_amount_approval_required),
                ('is_total_untaxed', '=', is_order_amount_approval_required),
                ('sales_team', '=', self.team_id.name)
            ])
            self.is_sale_order_approval_required = True


        # if sale_approvals is None:
        #     sale_approvals = self.env['sh.sale.approval.config'].search([
        #         ('is_freight', '=', is_freight_approval_required),
        #         ('is_min_price', '=', is_order_line_amount_approval_required),
        #         ('is_total_untaxed', '=', is_order_amount_approval_required),
        #         ('sales_team', '=', self.team_id.name)
        #     ])
        # if sale_approvals is not None and sale_approvals.id == False:
        #     sale_approvals = self.env['sh.sale.approval.config'].search([
        #         ('is_freight', '=', is_freight_approval_required),
        #         ('is_min_price', '=', is_order_line_amount_approval_required),
        #         ('is_total_untaxed', '=', is_order_amount_approval_required),
        #         ('sales_team', '=', 'APPROVAL TEAM')
        #     ])
        #     self.is_sale_order_approval_required = True



        if sale_approvals:
            self.update({
                'approval_level_id': sale_approvals[0].id
            })
        else:
            self.approval_level_id = False






    # @api.depends('amount_untaxed', 'amount_total')
    # def compute_approval_level(self):
    #
    #     if self.company_id.approval_based_on:
    #         if self.company_id.approval_based_on == 'untaxed_amount':
    #
    #             sale_approvals = self.env['sh.sale.approval.config'].search(
    #                 [('min_amount', '>', self.amount_untaxed), ('company_ids.id', 'in', [self.env.company.id])])
    #
    #             listt = []
    #             for sale_approval in sale_approvals:
    #                 listt.append(sale_approval.min_amount)
    #
    #             if listt:
    #                 sale_approval = sale_approvals.filtered(
    #                     lambda x: x.min_amount == max(listt))
    #
    #                 self.update({
    #                     'approval_level_id': sale_approval[0].id
    #                 })
    #             else:
    #                 self.approval_level_id = False
    #
    #         if self.company_id.approval_based_on == 'total':
    #
    #             sale_approvals = self.env['sh.sale.approval.config'].search(
    #                 [('min_amount', '>', self.amount_total)])
    #
    #             listt = []
    #             for sale_approval in sale_approvals:
    #                 listt.append(sale_approval.min_amount)
    #
    #             if listt:
    #                 sale_approval = sale_approvals.filtered(
    #                     lambda x: x.min_amount == max(listt))
    #
    #                 self.update({
    #                     'approval_level_id': sale_approval[0].id
    #                 })
    #
    #             else:
    #                 self.approval_level_id = False
    #
    #     else:
    #         self.approval_level_id = False

    def action_approve_order(self):
        if self.approval_remarks is False:
            raise UserError(_("Please Fill Approval Remarks"))
        template_id = self.env.ref(
            "sh_sale_dynamic_approval.email_template_sh_sale_order")

        info = self.approval_info_line.filtered(
            lambda x: x.level == self.level)

        if info:
            info.status = True
            info.approval_date = datetime.now()
            info.approved_by = self.env.user

        line_id = self.env['sh.sale.approval.line'].search(
            [('sale_approval_config_id', '=', self.approval_level_id.id), ('level', '=', self.level)])

        next_line = self.env['sh.sale.approval.line'].search(
            [('sale_approval_config_id', '=', self.approval_level_id.id), ('id', '>', line_id.id)], limit=1)

        if next_line:
            if next_line.approve_by == 'group':
                self.write({
                    'level': next_line.level,
                    'group_ids': [(6, 0, next_line.group_ids.ids)],
                    'user_ids': False
                })
                users = self.env['res.users'].search(
                    [('groups_id', 'in', next_line.group_ids.ids)])
                if template_id and users and self.approval_level_id.is_boolean:
                    for user in users:
                        template_id.sudo().send_mail(self.id, force_send=True, email_values={
                            'email_from': self.env.user.email, 'email_to': user.email, 'email_cc': self.user_id.email})

                if template_id and users and not self.approval_level_id.is_boolean:
                    for user in users:
                        template_id.sudo().send_mail(self.id, force_send=True, email_values={
                            'email_from': self.env.user.email, 'email_to': user.email})

                notifications = []
                if users:
                    for user in users:
                        notifications.append(
                            (user.partner_id, 'sh_notification_info', 
                            {'title': _('Notitification'),
                             'message': 'You have approval notification for sale order %s' % (self.name)
                            }))
                    self.env['bus.bus']._sendmany(notifications)

            if next_line.approve_by == 'user':
                self.write({
                    'level': next_line.level,
                    'user_ids': [(6, 0, next_line.user_ids.ids)],
                    'group_ids': False
                })
                if template_id and next_line.user_ids and self.approval_level_id.is_boolean:
                    for user in next_line.user_ids:
                        template_id.sudo().send_mail(self.id, force_send=True, email_values={
                            'email_from': self.env.user.email, 'email_to': user.email, 'email_cc': self.user_id.email})

                if template_id and next_line.user_ids and not self.approval_level_id.is_boolean:
                    for user in next_line.user_ids:
                        template_id.sudo().send_mail(self.id, force_send=True, email_values={
                            'email_from': self.env.user.email, 'email_to': user.email})

                notifications = []
                if next_line.user_ids:
                    for user in next_line.user_ids:
                        notifications.append(
                            (user.partner_id, 'sh_notification_info', 
                            {'title': _('Notitification'),
                             'message': 'You have approval notification for sale order %s' % (self.name)
                            }))
                    self.env['bus.bus']._sendmany(notifications)

        else:
            template_id = self.env.ref(
                "sh_sale_dynamic_approval.email_template_confirm_sh_sale_order")
            if template_id:
                template_id.sudo().send_mail(self.id, force_send=True, email_values={
                    'email_from': self.env.user.email, 'email_to': self.user_id.email})

            notifications = []
            if self.user_id:
                notifications.append(
                            (self.user_id.partner_id, 'sh_notification_info', 
                            {'title': _('Notitification'),
                             'message': 'Dear SalesPerson your order %s is confirmed' % (self.name)
                            }))
                self.env['bus.bus']._sendmany(notifications)

            self.write({
                'level': False,
                'group_ids': False,
                'user_ids': False
            })
            sale_order = self.env['sale.order'].browse(self.id)
            if self.is_sale_order_approval_required:
                self.is_sale_order_approval_required = False
                sale_order.action_confirm()
            super(SaleOrder, self).action_confirm()

    def action_reset_to_draft(self):
        self.write({
            'state': 'draft'
        })
