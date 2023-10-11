# -*- coding: utf-8 -*-
from odoo import api, fields, tools, models, _
from odoo.exceptions import UserError, ValidationError


class SaleApprovalConfig(models.Model):
    _name = 'sh.sale.approval.config'
    _description = 'Sale Approval Configuration'

    name = fields.Char()
    min_amount = fields.Float(string="Minimum Amount", required=True)
    company_ids = fields.Many2many(
        'res.company', string="Allowed Companies", default=lambda self: self.env.company)
    is_boolean = fields.Boolean(string="SalesPerson Always in CC")
    sale_approval_line = fields.One2many(
        'sh.sale.approval.line', 'sale_approval_config_id')

    is_freight = fields.Boolean(string = "Freight Required" , default=False)
    is_min_price = fields.Boolean(string = "Min Price Required" , default=False)
    sales_team = fields.Many2one('crm.team', 'Sales Team')

    @api.constrains('sale_approval_line')
    def approval_line_level(self):
        if self.sale_approval_line:
            levels = self.sale_approval_line.mapped('level')
            if len(levels) != len(set(levels)):
                raise ValidationError('Levels must be different!!!')
