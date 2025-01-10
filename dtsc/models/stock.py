from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
from odoo import _
import logging
import math
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import math
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = "stock.quant"
    
    lastmodifydate = fields.Datetime("最後修改時間",compute="_compute_lastmodifydate")
    zksl_cai = fields.Float("在庫數量(才)",compute="_compute_zksl_cai")
    average_price = fields.Float("平均采購價格" , compute="_compute_average_price")
    total_value = fields.Float("成本" , compute="_compute_average_price")
    categ_id = fields.Many2one("product.category",string="產品分類",related="product_id.product_tmpl_id.categ_id",store=True)
    
    @api.depends('inventory_quantity')
    def _compute_inventory_diff_quantity(self):
        for quant in self:
            if quant.inventory_quantity:
                quant.inventory_diff_quantity = quant.inventory_quantity - quant.quantity
            else:
                quant.inventory_diff_quantity = 0
    
    @api.depends('quantity')
    def _compute_average_price(self):
        for record in self:
            if record.lot_id:#如果是有批次的產品
                purchase_line = self.env['purchase.order.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done']),
                    ('order_id',"=",record.lot_id.purchase_order_id.id)
                    ], order='date_order desc',limit=1)
                    
                if purchase_line:
                    record.average_price = purchase_line.price_unit
                    record.total_value = record.quantity * record.average_price
                else:#如果找不到相同序號的 ，則找最近一個相同產品的
                    lot_purchase_lines_other = self.env['purchase.order.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc', limit=1)
                    record.average_price = lot_purchase_lines_other.price_unit
                    record.total_value = record.quantity * record.average_price
                    
            else:#無批次產品
                total_value = 0.0
                average_price = 0.0
                total_qty_needed = record.quantity
                purchase_lines = self.env['purchase.order.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ], order='date_order desc')

                qty_consumed = 0
                for line in purchase_lines:
                    if total_qty_needed <= 0:
                        break
                    purchase_qty = line.product_qty
                    purchase_price = line.price_unit

                    if purchase_qty >= total_qty_needed:
                        total_value += total_qty_needed * purchase_price
                        qty_consumed += total_qty_needed
                        total_qty_needed = 0
                    else:
                        total_value += purchase_qty * purchase_price
                        qty_consumed += purchase_qty
                        total_qty_needed -= purchase_qty

                average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
            
                record.average_price = average_price
                record.total_value = total_value

    
    @api.depends('quantity')
    def _compute_zksl_cai(self):
        for record in self:
            if record.lot_id:
                uom_obj = self.env["uom.uom"]
                uom_record = uom_obj.browse(record.product_uom_id.id)
                now_category_id = uom_record.category_id.id
                other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                record.zksl_cai = round(record.quantity * other_uom.factor,1)
            else:
                record.zksl_cai = 0
    
    def _domain_product_id(self):
        if not self._is_inventory_mode():
            return
        domain = [('type', '=', 'product'), ('product_tmpl_id.purchase_ok', '=', True)]
        if self.env.context.get('product_tmpl_ids') or self.env.context.get('product_tmpl_id'):
            products = self.env.context.get('product_tmpl_ids', []) + [self.env.context.get('product_tmpl_id', 0)]
            domain = expression.AND([domain, [('product_tmpl_id', 'in', products)]])
        return domain
        
    @api.depends('quantity', 'product_id.stock_move_ids', 'lot_id')
    def _compute_lastmodifydate(self):
        for record in self:
            domain = [('product_id', '=', record.product_id.id)]
            if record.lot_id:
                domain.append(('lot_id', '=', record.lot_id.id))

            move_lines = self.env['stock.move.line'].search(
                domain, order='date desc', limit=1)
            if move_lines:
                record.lastmodifydate = move_lines.date
            else: 
                record.lastmodifydate = None

class Productproduct(models.Model):
    _inherit = "product.product"
    
    sec_uom_id = fields.Many2one("uom.uom")
    
class StockMove(models.Model):
    _inherit = "stock.move"
    
    reference = fields.Char(compute='_compute_reference_new', string="Reference", store=True)
    
    @api.depends('picking_id', 'name')
    def _compute_reference_new(self):
        for move in self:
            if move.reference:
                move.reference = move.reference
            else:
                move.reference = move.picking_id.name if move.picking_id else move.name
        
        
class Mpr(models.Model):
    _name = "dtsc.mpr"
    _order = "name desc"
    name = fields.Char("單號")
    from_name = fields.Char("銷售單號")
    state = fields.Selection([
        ("draft","待扣料"),
        ("succ","扣料完成"),   
    ],default='draft' ,string="狀態")
    mprline_ids = fields.One2many("dtsc.mprline" , "mpr_id")
    picking_id = fields.Many2one("stock.picking")
    stock_move_id = fields.Many2one("stock.move")
    stock_move_line_id = fields.Many2many("stock.move.line")
    stock_location_id = fields.Many2one("stock.location", string="同步所有倉庫項次",domain=[('usage', '=', 'internal')] ,default = 8 )
    
    @api.onchange('stock_location_id')
    def _onchange_stock_location_id(self): 
        for record in self:
            for mprline in record.mprline_ids:
                mprline.write({
                    'stock_location_id': record.stock_location_id.id  # 更新 mprline 的 stock_location_id
                })
    
    
    def back_btn(self):
        self.ensure_one()
        if not self.picking_id or self.picking_id.state != 'done':
            raise UserError('无有效的完成拣货操作，无法回退。')

        # 创建逆向拣货记录
        reverse_picking_vals = {
            'picking_type_id': self.picking_id.picking_type_id.id,
            # 'location_id': self.picking_id.location_dest_id.id,
            # 'location_dest_id': self.picking_id.location_id.id,
            'origin': '退回 ' + self.name.replace("W","B"),
        }
        reverse_picking = self.env['stock.picking'].create(reverse_picking_vals)
        
        
        for move in self.picking_id.move_ids:
        
            reverse_move_vals = {
                'name': move.name,
                'reference': "退回" + self.name.replace("W","B"),
                'origin' : self.name.replace("W","B"),
                'product_id': move.product_id.id,
                'product_uom_qty': move.product_uom_qty,
                'quantity_done': move.quantity_done,
                'product_uom': move.product_uom.id,
                'picking_id': reverse_picking.id,
                'location_id': move.location_dest_id.id,
                'location_dest_id': move.location_id.id,
            }
            reverse_move = self.env['stock.move'].create(reverse_move_vals)
            # print(line.id)  
            # 处理序列号
            for move_line in move.move_line_ids:
                print("========================")
                if move_line.lot_id:
                    # print(move_line.product_id.name)
                    # print(move_line.lot_id.name)
                    # print(move_line.lot_id.id)
                    reverse_move_line_vals = {
                        'reference' : "退回"+self.name.replace("W","B"), 
                        'origin' : self.name.replace("W","B"),
                        'move_id': reverse_move.id,
                        'product_id': move_line.product_id.id,
                        'product_uom_id': move_line.product_uom_id.id,
                        'picking_id': reverse_picking.id,
                        'reserved_uom_qty': move_line.qty_done,
                        'qty_done': move_line.qty_done,
                        'lot_id': move_line.lot_id.id,  # 指定序列号
                        'location_id': move_line.location_dest_id.id,
                        'location_dest_id': move_line.location_id.id,
                    }
                    moveline  = self.env['stock.move.line'].create(reverse_move_line_vals)
                    move_line_objs = self.env['stock.move.line'].search([("product_id" , "=" ,move_line.product_id.id ),("lot_id" ,"=" , False ),('picking_id',"=", reverse_picking.id)])
                    move_line_objs.unlink()
            
        # for line in reverse_move.move_line_ids:
             # print(line.id)    
        # 确认并完成逆向拣货
        reverse_picking.action_confirm()
        reverse_picking.action_assign()
        reverse_picking.button_validate()
        
        
        self.write({'state': 'draft'})
    
    def floor_to_one_decimal_place(self,number):
        return math.floor(number * 10) / 10
        
        
    def confirm_btn(self):
        for record in self.mprline_ids:
            if record.product_product_id.product_tmpl_id.tracking == "serial": #如果這個產品設定的是有唯一序列號的 則需要選擇序號
                if not record.product_lot:
                    raise UserError('%s 還未選擇正確的序號！' %record.product_product_id.name)
                  
            if record.final_use < 0:
                raise UserError('%s 扣料必須大於0！' %record.product_product_id.name)
            elif record.final_use == 0:
                record.final_use = record.now_use
                
        # now_stock_location_id = self.stock_location_id.id       
        picking = self.env['stock.picking'].create({
            # 'name':self.name.replace("W","B/W/"),
            'picking_type_id' : 1,
            # 'location_id': now_stock_location_id,  #库存
            'location_dest_id': 15, #Production 用于生产
            'origin' : self.name.replace("W","B"),
        })
        
        self.write({'picking_id': picking.id})
        uom_obj = self.env["uom.uom"]
        
        for record in self.mprline_ids:
            uomid = record.uom_id.id
            
            if "卷" in record.uom_id.name:
                uom_record = uom_obj.browse(record.uom_id.id)
                now_category_id = uom_record.category_id.id
                other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                uomid = other_uom.id
            
            final_use = record.final_use
            # if record.product_lot: 
                # quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,now_stock_location_id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
                # if quant:
                    # uom_record = uom_obj.browse(record.uom_id.id)
                    # now_category_id = uom_record.category_id.id
                    # other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                    # if other_uom.name == "才":
                        # if quant.quantity * other_uom.factor < record.final_use:
                            # raise UserError('%s 實際扣料大於庫存！' %record.product_product_id.name)
                            # final_use = self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)
                                        
                    # if record.is_all == True:
                        # uomid = record.uom_id.id
                        # final_use = quant.quantity
            
            move = self.env['stock.move'].create({
                'name' : self.name.replace("W","B/W/"),
                'reference' : "工单扣料"+self.name.replace("W","B"), 
                'product_id': record.product_product_id.id,
                'product_uom_qty' : final_use,
                'product_uom' : uomid,
                "picking_id" : picking.id,
                "quantity_done" : final_use,
                'origin' : self.name.replace("W","B"),
                'location_id': record.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产                
            })
            self.write({'stock_move_id': move.id})
            
            if record.product_lot:    
                # move_line_obj = self.env['stock.move.line'].browse(move.id)
                move_line = self.env['stock.move.line'].create({
                    'reference' : "工单扣料"+self.name.replace("W","B"), 
                    'origin' : self.name.replace("W","B"),
                    "move_id": move.id, 
                    "picking_id" : picking.id,
                    'product_id': record.product_product_id.id,
                    'qty_done': final_use ,
                    'product_uom_id' : uomid,                
                    'location_id': record.stock_location_id.id,  #库存
                    'location_dest_id': 15, #Production 用于生产 
                    'lot_name' : record.product_lot.name,
                    'lot_id': record.product_lot.id,
                    'state': "draft",
                })                
                self.stock_move_line_id = [(4, move_line.id)]
                move_line_objs = self.env['stock.move.line'].search(["|",("lot_id" ,"=" , False ),("lot_name" ,"=" , False ),("product_id" , "=" ,record.product_product_id.id ),('picking_id',"=", picking.id)])
                move_line_objs.unlink()
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate() 
        
        self.write({"state":"succ"})
    
class MprLine(models.Model):
    _name = "dtsc.mprline"
    
    mpr_id = fields.Many2one("dtsc.mpr")
    # final_use_readonly = fields.Boolean(compute='_compute_final_use_readonly', default=False, store=False)
    purchase_product_id = fields.Many2one("dtsc.checkout",readonly=True)
    product_product_id = fields.Many2one("product.product" , "物料名稱")
    product_lot = fields.Many2one("stock.lot" , "產品序號")
    product_id_formake=fields.Many2one('product.template',readonly=True) 
    product_id = fields.Many2one("product.template" , "製作物" ,readonly = True)
    attr_name = fields.Char("屬性名",readonly=True)
    uom_id = fields.Many2one('uom.uom',string="單位")
    now_use = fields.Float("預計消耗" ,readonly=True)
    final_use = fields.Float("實際消耗")
    lot_stock_num = fields.Char(string = "單序號庫存" ,compute = '_compute_lot_stock_num')
    now_stock = fields.Char(string='總庫存',compute = '_compute_now_stock' ,readonly=True)
    barcode_input = fields.Char("條碼輸入")
    comment = fields.Char("備註")
    is_all = fields.Boolean("扣除餘料")
    stock_location_id = fields.Many2one("stock.location", string="倉庫",domain=[('usage', '=', 'internal')] ,default = 8 )

    
    ####权限
    is_in_by_mg = fields.Boolean(compute='_compute_is_in_by_mg')
    
    def floor_to_one_decimal_place(self,number):
        return math.floor(number * 10) / 10
    
    @api.onchange("is_all")
    def change_is_all(self): 
        uom_obj = self.env["uom.uom"]    
        for record in self:
            if self.is_all == True:
                if record.product_lot.id:
                
                    quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,8)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
                
                    if quant:
                        uom_record = uom_obj.browse(record.uom_id.id)
                        now_category_id = uom_record.category_id.id
                        other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                        if other_uom.name == "才":
                            record.final_use = self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)
                        else:
                            record.final_use = quant.quantity
                    else:
                        raise UserError('該序號產品沒有庫存。')
                else:
                    raise UserError('非序號產品無法扣除餘料。')
    
    @api.depends("product_product_id")
    def _compute_is_in_by_mg(self):
        group_dtsc_mg = self.env.ref('dtsc.group_dtsc_mg', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_mg = group_dtsc_mg and user in group_dtsc_mg.users
        
    is_in_by_sc = fields.Boolean(compute='_compute_is_in_by_sc')

    @api.depends("product_product_id")
    def _compute_is_in_by_sc(self):
        group_dtsc_sc = self.env.ref('dtsc.group_dtsc_sc', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_sc = group_dtsc_sc and user in group_dtsc_sc.users
        
    is_in_by_ck = fields.Boolean(compute='_compute_is_in_by_ck')

    @api.depends("product_product_id")
    def _compute_is_in_by_ck(self):
        group_dtsc_ck = self.env.ref('dtsc.group_dtsc_ck', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_ck = group_dtsc_ck and user in group_dtsc_ck.users
    ####权限
    
    @api.model
    def create(self, vals):
        mpr_record = self.env['dtsc.mpr'].browse(vals.get('mpr_id'))
        if mpr_record.state == 'succ':
            raise UserError('不允許在此狀態下添加記錄。')
        return super(MprLine, self).create(vals)

    def write(self, vals):
        if self.mpr_id.state == 'succ':
            raise UserError('不允許在此狀態下修改記錄。')
        return super(MprLine, self).write(vals)

    def unlink(self):
        if any(line.mpr_id.state == 'succ' for line in self):
            raise UserError('不允許在此狀態下刪除記錄。')
        return super(MprLine, self).unlink()

    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        if self.barcode_input:
            parts = self.barcode_input.split('-')
            if len(parts) > 2:
                # 假设 a 是 product_product_id 的外部 ID
                product = self.env['product.product'].search([('default_code', '=', parts[0])])
                if product:
                    self.product_product_id = product.id
                # 假设 b 是 product_lot 的名称
                # lot = self.env['stock.lot'].search([('name', '=', parts[1]+"-"+parts[2])])
                lot = self.env['stock.lot'].search([('barcode', '=', self.barcode_input)])
                if lot:
                    self.product_lot = lot.id

    
    @api.onchange("product_product_id")
    def change_uom(self):
        for record in self:
            if self.product_product_id:
                self.uom_id = self.product_product_id.uom_id.id
    
    
    @api.depends('product_id','product_product_id',"product_lot")
    def _compute_lot_stock_num(self):
        uom_obj = self.env["uom.uom"]
        for record in self:
            if record.product_lot.id:
            
                quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,8)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
            
                if quant:
                    uom_record = uom_obj.browse(record.uom_id.id)
                    now_category_id = uom_record.category_id.id
                    other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                    if other_uom.name == "才":
                        # record.lot_stock_num = str(round(quant.quantity,1)) + "(" + str(round(quant.quantity * other_uom.factor,1)) +" 才)"
                        record.lot_stock_num = str(round(quant.quantity,3)) + "(" + str(self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)) +" 才)"
                    else:
                        record.lot_stock_num = quant.quantity
                else:
                    record.lot_stock_num = "無"
            else:
                record.lot_stock_num = "無"
                
    @api.depends('product_id','product_product_id','stock_location_id')
    def _compute_now_stock(self):
        for record in self:
            # print(record.mpr_id.stock_location_id.id)
            # print(record.product_product_id.id)
            quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("location_id" ,"=" ,record.stock_location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
            if quant:
                record.now_stock = quant.quantity
            else:
                record.now_stock = "0"
         

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    description = fields.Text(string="採購描述" , related="move_id.purchase_line_id.name")
    
    @api.onchange('qty_done', 'product_uom_id')
    def _onchange_qty_done(self):
        """ When the user is encoding a move line for a tracked product, we apply some logic to
        help him. This onchange will warn him if he set `qty_done` to a non-supported value.
        """
        res = {}
        # if self.qty_done and self.product_id.tracking == 'serial':
            # qty_done = self.product_uom_id._compute_quantity(self.qty_done, self.product_id.uom_id)
            # if float_compare(qty_done, 1.0, precision_rounding=self.product_id.uom_id.rounding) != 0:
                # message = _('You can only process 1.0 %s of products with unique serial number.', self.product_id.uom_id.name)
                # res['warning'] = {'title': _('Warning'), 'message': message}
        return res
    # remark = fields.Text(string="備註")
    # def _get_inventory_move_values(self, qty, location_id, location_dest_id, out=False):
 
        # self.ensure_one()
        # if self.remark:
            # if fields.Float.is_zero(qty, 0, precision_rounding=self.product_uom_id.rounding):
                # name = "數量確認 (" + self.remark+")"
            # else:
                # name = "數量更新 (" + self.remark +")"
        
        # self.write({"remark":""})
        # return {
            # 'name': self.env.context.get('inventory_name') or name,
            # 'product_id': self.product_id.id,
            # 'product_uom': self.product_uom_id.id,
            # 'product_uom_qty': qty,
            # 'company_id': self.company_id.id or self.env.company.id,
            # 'state': 'confirmed',
            # 'location_id': location_id.id,
            # 'location_dest_id': location_dest_id.id,
            # 'is_inventory': True,
            # 'move_line_ids': [(0, 0, {
                # 'product_id': self.product_id.id,
                # 'product_uom_id': self.product_uom_id.id,
                # 'qty_done': qty,
                # 'location_id': location_id.id,
                # 'location_dest_id': location_dest_id.id,
                # 'company_id': self.company_id.id or self.env.company.id,
                # 'lot_id': self.lot_id.id,
                # 'package_id': out and self.package_id.id or False,
                # 'result_package_id': (not out) and self.package_id.id or False,
                # 'owner_id': self.owner_id.id,
            # })]
        # }

        
# class StockQuantInherit(models.Model):
    # _inherit = 'stock.quant'

    # purchase_price = fields.Float('採購價格')
        
class ReportStockQuant(models.AbstractModel):
    _name = 'report.dtsc.report_inventory'
    
    
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">",0)])
        product_quant_map = {}
        '''
        for quant in quants:
            # 对每个quant, 找到对应的stock.move.line和stock.move
            move_lines = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('location_id', '=', 4)
            ], limit=1)

            if move_lines:
                move = move_lines.move_id
                if move:
                    # 对于每个产品，累计其数量和总价格
                    if quant.product_id not in product_quant_map:
                        #product_quant_map[quant.product_id] = {'total_price': 0.0, 'total_qty': 0.0}
                        product_quant_map[quant.product_id] = {
                            'total_qty': 0.0,
                            'uom': quant.product_uom_id.name  
                        }
                    
                    product_quant_map[quant.product_id]['total_qty'] += quant.quantity
        '''
        for quant in quants:
            # 使用 (product_id, location_id) 作为键
            key = (quant.product_id, quant.location_id)
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'total_qty': 0.0,
                    'uom': quant.product_uom_id.name,
                    'location': quant.location_id.name,  # 增加仓库位置
                }
            product_quant_map[key]['total_qty'] += quant.quantity
        
        # 准备传递给报告的数据
        report_data = []
        for (product, location), data in product_quant_map.items():
            report_data.append({
                'product_id': product,
                'quantity': round(data['total_qty'],2),
                'uom': data['uom'],
                'location': data['location'],  # 在报告中显示仓库位置
            })
       # 返回传递给报告的数据
        # print(report_data)
        # 按照仓库名称排序
        sorted_report_data = sorted(report_data, key=lambda x: x['location'])
        return {
            'doc_ids': docids,
            'docs': quants,
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }

    
        
class ReportStockQuantAmount(models.AbstractModel):
    _name = 'report.dtsc.report_inventory_amount'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">",0)])
        product_quant_map = {}        
        report_data = []
        
        for quant in quants:
            # 使用 (product_id, location_id) 作为键
            key = (quant.product_id, quant.location_id)
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'total_qty': 0.0,
                    'uom': quant.product_uom_id.name,
                    'location': quant.location_id.name,  # 增加仓库位置
                    'lots': [],
                    'lot_qty': [],
                }
            product_quant_map[key]['total_qty'] += quant.quantity
            if quant.lot_id:
                product_quant_map[key]['lots'].append(quant.lot_id)
                product_quant_map[key]['lot_qty'].append(quant.quantity)
                
        
        # 准备传递给报告的数据
        for (product, location), data in product_quant_map.items():
            total_qty_needed = data['total_qty']  # 该仓库中该产品的总库存数量
            total_value = 0.0  # 总价值
            qty_consumed = 0  # 已处理的数量
            average_price = 0
            
            
            if data["lots"]:
                # continue
                for index, lot in enumerate(data["lots"]):
                    purchase_line = self.env['purchase.order.line'].search([
                    ('product_id', '=', product.id),
                    ('order_id.state', 'in', ['purchase', 'done']),
                    ('order_id',"=",lot.purchase_order_id.id)
                    ], order='date_order desc',limit=1)

                    if purchase_line:
                        average_price = purchase_line.price_unit
                        lot_qty = data['lot_qty'][index]  # 获取该批次的数量
                        total_value += lot_qty * average_price  # 计算总价值
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        lot_purchase_lines_other = self.env['purchase.order.line'].search([
                        ('product_id', '=', product.id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                        ], order='date_order desc', limit=1)
                        
                        if lot_purchase_lines_other:
                            average_price = lot_purchase_lines_other.price_unit
                            lot_qty = data['lot_qty'][index]  # 获取该批次的数量
                            total_value += lot_qty * average_price  # 计算总价值
                            
                report_data.append({
                    'product_id': product,
                    'quantity': round(data['total_qty'], 2),
                    'uom': data['uom'],
                    'location': data['location'],
                    'average_price': round(average_price, 2),  # 加权平均价格
                    'total_value': round(total_value, 2),  # 总价值
                    'is_lot':1, 
                })    
                
            else:
                # 获取该产品的所有采购记录，按时间从最近到最早排序
                purchase_lines = self.env['purchase.order.line'].search([
                    ('product_id', '=', product.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ], order='date_order desc')
                
                
                
                # 根据采购记录计算加权平均价格
                a = 0
                if total_qty_needed <= 0:
                    #如果數量為0 則找最近一筆的單價顯示
                    if purchase_lines:
                        a = purchase_lines[0].price_unit
                    average_price = a  # 如果没有采购记录，则保持为0
                else:    
                    for line in purchase_lines:
                        
                        print(product.name)
                        print(line.product_qty)
                        print(line.price_unit   )
                        if total_qty_needed <= 0:
                            # if line.price_unit:
                                # a = line.price_unit
                            break

                        purchase_qty = line.product_qty  # 采购的数量
                        purchase_price = line.price_unit  # 采购的单价

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty

                    # 如果没有采购记录或库存消耗完了，价格为0
                    # if total_qty_needed <= 0:
                        # average_price = a
                    # else:
                    average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0

                # 加入到报告数据中
                report_data.append({
                    'product_id': product,
                    'quantity': round(data['total_qty'], 2),
                    'uom': data['uom'],
                    'location': data['location'],
                    'average_price': round(average_price, 2),  # 加权平均价格
                    'total_value': round(total_value, 2),
                    'is_lot':0,                    # 总价值
                })

        # 按照仓库名称排序
        sorted_report_data = sorted(report_data, key=lambda x:( x['location'], -x['is_lot'], x['product_id'].name))

        return {
            'doc_ids': docids,
            'docs': quants,
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }

    '''
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        product_quant_map = {}

        for quant in quants:
            # 对每个quant, 找到对应的stock.move.line和stock.move
            move_lines = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('location_id', '=', 4)
            ], limit=1)

            if move_lines:
                move = move_lines.move_id
                if move:
                    # 获取价格从采购订单行
                    purchase_line = move.purchase_line_id
                    price_unit = purchase_line.price_unit if purchase_line else move.price_unit  # 如果没有采购行则使用move的price_unit

                    # 对于每个产品，累计其数量和总价格
                    if quant.product_id not in product_quant_map:
                        product_quant_map[quant.product_id] = {
                            'total_price': 0.0,
                            'total_qty': 0.0,
                            'uom': quant.product_uom_id.name  
                        }
                    
                    product_quant_map[quant.product_id]['total_price'] += round(price_unit * quant.quantity, 1)
                    product_quant_map[quant.product_id]['total_qty'] += quant.quantity
        
        # 计算平均价格
        for product_id, data in product_quant_map.items():
            print(f"Product: {product_id.display_name}, Total Quantity: {data['total_qty']}, Total Price: {data['total_price']}")
            if data['total_qty'] > 0:
                data['avg_price'] = round(data['total_price'] / data['total_qty'], 1)
            else:
                data['avg_price'] = 0.0
        
        # 准备传递给报告的数据
        report_data = []
        for product, data in product_quant_map.items():
            report_data.append({
                'product_id': product,
                'quantity': data['total_qty'],
                'average_price': data['avg_price'],
                'total_price': data['total_price'],
                'uom': data['uom']
            })

        return {
            'doc_ids': docids,
            'doc_model': 'stock.quant',
            'data': report_data,  # 传递合并后的数据给报告
        }
        '''
class StockQuantInherit(models.Model):
    _inherit = 'stock.quant'

    purchase_price = fields.Float('採購價格')
    
    #重写方法 不判断序号大于1的扣料情况
    @api.constrains('quantity')
    def check_quantity(self):
        sn_quants = self.filtered(lambda q: q.product_id.tracking == 'serial' and q.location_id.usage != 'inventory' and q.lot_id)
        if not sn_quants:
            return
        # domain = expression.OR([
            # [('product_id', '=', q.product_id.id), ('location_id', '=', q.location_id.id), ('lot_id', '=', q.lot_id.id)]
            # for q in sn_quants
        # ])
        # groups = self.read_group(
            # domain,
            # ['quantity'],
            # ['product_id', 'location_id', 'lot_id'],
            # orderby='id',
            # lazy=False,
        # )
        # for group in groups:
            # product = self.env['product.product'].browse(group['product_id'][0])
            # lot = self.env['stock.lot'].browse(group['lot_id'][0])
            # uom = product.uom_id
            # if float_compare(abs(group['quantity']), 1, precision_rounding=uom.rounding) > 0:
                # raise ValidationError(_('The serial number has already been assigned: \n Product: %s, Serial Number: %s') % (product.display_name, lot.name))
        
class ReportStockQuantBase(models.AbstractModel):
    _name = 'report.dtsc.report_inventory_base'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">",0)])
        product_quant_map = {}
        
        key = 0
        report_data = []
        for quant in quants:
            # 使用 (product_id, location_id) 作为键
            key = key + 1
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'total_qty': 0.0,
                    'uom': quant.product_uom_id.name,
                    'location': quant.location_id.name,  # 增加仓库位置
                }
            total_value = 0.0
            average_price = 0.0
            b=0
            if quant.lot_id:#如果是捲料 則直接找捲料單價
                b=1
                lot_purchase_lines = self.env['purchase.order.line'].search([
                    ('product_id', '=', quant.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done']),
                    ('order_id',"=",quant.lot_id.purchase_order_id.id)
                ], order='date_order desc', limit=1)

                # 如果找到了对应的采购单行，使用该批次的单价
                if lot_purchase_lines:
                    average_price = lot_purchase_lines.price_unit
                    total_value = quant.quantity * average_price
                else:#如果找不到相同序號的 ，則找最近一個相同產品的
                    lot_purchase_lines_other = self.env['purchase.order.line'].search([
                    ('product_id', '=', quant.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc', limit=1)
                    average_price = lot_purchase_lines_other.price_unit
                    total_value = quant.quantity * average_price
                    
            else:#否則計算加權平均價格
                # 否则使用加权平均价格计算
                total_qty_needed = quant.quantity
                purchase_lines = self.env['purchase.order.line'].search([
                    ('product_id', '=', quant.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ], order='date_order desc')

                qty_consumed = 0
                for line in purchase_lines:
                    if total_qty_needed <= 0:
                        break
                    purchase_qty = line.product_qty
                    purchase_price = line.price_unit

                    if purchase_qty >= total_qty_needed:
                        total_value += total_qty_needed * purchase_price
                        qty_consumed += total_qty_needed
                        total_qty_needed = 0
                    else:
                        total_value += purchase_qty * purchase_price
                        qty_consumed += purchase_qty
                        total_qty_needed -= purchase_qty

                average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0

            
            report_data.append({
                'product_id': quant.product_id,
                'lot_id':quant.lot_id.name,
                'quantity': round(quant.quantity, 2),
                'uom': quant.product_uom_id.name,
                'is_lot':b,
                'location': quant.location_id.name,
                'average_price': round(average_price, 2),  # 加权平均价格
                'total_value': round(total_value, 2),  # 总价值
            })
            
        
        
        # 按照仓库名称排序
        sorted_report_data = sorted(report_data, key=lambda x: (x['location'], -x['is_lot']  , x['product_id'].name))

        return {
            'doc_ids': docids,
            'docs': quants,
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }
        
    '''
    @api.model
    def _get_report_values(self, docids, data=None):
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        for quant in quants:
            # 根据lot_id和location_id找到对应的stock.move.line
            move_lines = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('location_id', '=', 4)  # 根据您的描述，这里使用location_id=4
            ], limit=1)  # 假设我们只关心找到的第一条记录
            
            if move_lines:
                move = move_lines.move_id  # 从stock.move.line获取stock.move
                if move:
                    # 现在我们有了move对象，可以获取price_unit
                    quant.purchase_price = move.price_unit
                else:
                    quant.purchase_price = 0
            else:
                quant.purchase_price = 0
        
        return {
            'doc_ids': docids,
            'doc_model': 'stock.quant',
            'docs': quants,
            'data': data,
        }   
    '''