from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    customer_name = fields.Char(string='客戶名稱')
    
    customclass_id = fields.Many2one("dtsc.customclass" , string='客戶分類',required=True)
    
    # kaidan = fields.Many2one(
        # 'dtsc.userlistbefore',
        # string="开单人员",
        # required=True,
        # help="为大图订单指定开单人员"
    # )

    checkout_id = fields.Many2one(
        'dtsc.checkout',
        string="关联大图订单",
        readonly=True,
        help="与当前商机关联的大图订单"
    )

    checkout_count = fields.Integer(
        string="大图订单数量",
        compute="_compute_checkout_count",
        store=False,
        help="计算与当前商机关联的大图订单数量"
    )

    @api.depends('checkout_id')
    def _compute_checkout_count(self):
        for lead in self:
            lead.checkout_count = self.env['dtsc.checkout'].search_count([('crm_lead_id', '=', lead.id)])
            
    def action_open_checkout(self):
        self.ensure_one()
        # 从上下文中获取 customer_name
        customer_name = self.env.context.get('customer_name')

        if not customer_name:
            raise ValueError("未提供客户名称")

        # 创建大图订单
        checkout = self.env['dtsc.checkout'].with_context(from_crm=True).create({
            # 'customer_id': customer_name,
            'customer_temp_name': customer_name,
            # 'kaidan': self.kaidan.id,
            # 'delivery_carrier': "",
            'crm_lead_id': self.id,
            'customer_class_id': self.customclass_id.id,
        })

        # 关联创建的订单
        self.checkout_id = checkout.id

        return {
            'type': 'ir.actions.act_window',
            'name': '新增大图订单',
            'res_model': 'dtsc.checkout',
            'view_mode': 'form',
            'res_id': checkout.id,
            'target': 'current',
        }

        
    def action_view_related_checkout(self):
        """
        从CRM进入时，显示与当前商机关联的所有订单状态。
        """
        self.ensure_one()
        action = self.env.ref('dtsc.action_window').read()[0]
        # 强制显示所有状态，包括 "待确认"
        action['domain'] = [('crm_lead_id', '=', self.id)]
        return action






class CheckoutInherit(models.Model):
    _inherit = 'dtsc.checkout'

    customer_temp_name = fields.Char(
        string="客户名称", 
        help="临时存储客户名称，从CRM中带过来，确认时检查或创建客户"
    )

    crm_lead_id = fields.Many2one(
        'crm.lead',
        string="关联商机",
        help="与此订单关联的商机"
    )

    checkout_order_state = fields.Selection(selection_add=[
        ('waiting_confirmation', '待確認')
    ], ondelete={'waiting_confirmation': 'set default'})

    # def create(self, vals):
        # """
        # 如果从 CRM 创建订单，设置状态为“待确认”。
        # """
        # #_logger.info("Creating Checkout - Incoming Vals: %s", vals)  # 打印传入的 vals
        # #_logger.info("Context in create: %s", self.env.context)  # 打印上下文信息

        # if self.env.context.get('from_crm', False):  # 检查上下文
            # vals['checkout_order_state'] = 'waiting_confirmation'
            # #_logger.info("Setting checkout_order_state to 'waiting_confirmation'")  # 打印设置状态的确认
        # _logger.info("Incoming Vals: %s", vals)  # 打印创建记录时的值
        # result = super(CheckoutInherit, self).create(vals)
        # #_logger.info("Created Checkout - Result: %s", result)  # 打印创建完成的记录
        # return result
    @api.model
    def create(self, vals):
        """
        如果从 CRM 创建订单，设置状态为“待确认”。
        """
        _logger.info("Creating Checkout - Incoming Vals: %s", vals)  # 打印传入的 vals

        # 检查上下文，确定是否来自 CRM
        if self.env.context.get('from_crm', False):  
            vals['checkout_order_state'] = 'waiting_confirmation'
            _logger.info("Setting checkout_order_state to 'waiting_confirmation'")

        # 调用父类的 create 方法
        result = super(CheckoutInherit, self).create(vals)

        _logger.info("Created Checkout - Result: %s", result)
        return result
    
    
    # def action_confirm_to_draft(self):
        # """
        # 将状态从“待確認”变更为“草稿”。
        # """
        # for record in self:
            # if record.checkout_order_state == 'waiting_confirmation':
                # record.checkout_order_state = 'draft'
   
            
    def action_confirm_to_draft(self):
        """
        确认按钮逻辑：
        - 检查 customer_temp_name 是否填写。
        - 如果存在相同客户，则绑定到 customer_id。
        - 如果不存在，则创建新客户并绑定到 customer_id。
        - 将 customer_class_id 赋值给客户的 customclass_id 字段。
        """
        for record in self:
            if not record.customer_temp_name:
                raise ValueError(_("客户名称不能为空"))

            # 在客户列表中查找是否存在匹配的客户
            customer = self.env['res.partner'].search([('name', '=', record.customer_temp_name)], limit=1)
            
            if customer:
                # 如果找到，绑定到 customer_id
                record.customer_id = customer.id

                # 如果客户分类字段存在，更新客户的 customclass_id
                if record.customer_class_id:
                    customer.customclass_id = record.customer_class_id.id
            else:
                # 如果没找到，创建新客户并设置 customclass_id
                customer = self.env['res.partner'].create({
                    'name': record.customer_temp_name,
                    'customer_rank': 1,  # 确保标记为客户
                    'customclass_id': record.customer_class_id.id if record.customer_class_id else False,
                })
                record.customer_id = customer.id

            # 清空临时字段并修改状态为草稿
            record.customer_temp_name = False
            record.checkout_order_state = 'draft'
