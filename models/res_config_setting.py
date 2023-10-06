# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies.

from odoo import api, fields, tools, models, _

class ResCompany(models.Model):
    _inherit = 'res.company'

    approval_based_on = fields.Selection(
        [
            ('untaxed_amount','Untaxed amount'),
            ('total','Total')
        ],default='untaxed_amount',readonly=False)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    approval_based_on = fields.Selection(
        # [
        #     ('untaxed_amount','Untaxed amount'),
        #     ('total','Total')
        # ],
        related='company_id.approval_based_on',default='untaxed_amount',readonly=False)