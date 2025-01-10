from odoo import models, fields
class ResPartner(models.Model):
    _inherit = "product.template"
    
    unit_conversion_id = fields.Many2one("dtsc.unit_conversion" , string='單位轉換計算')
    
    product_liucheng = fields.Selection([
        ('1', '一次生產完成'),
        ('2', '委外後轉內部生產'),
    ], string='生產流程')
    
    uom_id = fields.Many2one("uom.uom" , string='單位')
    uom_po_id = fields.Many2one("uom.uom" , string='采購計量單位')
    price_fudong = fields.Float(string="浮動價格")
    is_add_mode = fields.Boolean(string="是否有多選屬性")
    make_ori_product_id = fields.Many2one("product.template",string="基礎扣料物",domain=[('purchase_ok',"=",True)],ondelete='cascade')
    
    # multiple_choice_ids = fields.One2many("dtsc.maketypeRel" , "product_id" ,string="後加工明細")
    make_type_ids = fields.One2many("product.maketype.rel" , "product_id" ,string="後加工明細")

class ProductMakeTypeRel(models.Model):
    _name='product.maketype.rel'
    sequence = fields.Integer("Sequence")
    product_id = fields.Many2one("product.template","產品")
    make_type_id = fields.Many2one("dtsc.maketype" , "後加工方式",ondelete='cascade')
    
    _sql_constraints = [
        ('product_make_type_unique', 'UNIQUE(product_id, make_type_id)', '同一產品不能選擇重複的後加工方式')
    ]
    
class ProductAttribute(models.Model):
    _inherit = "product.template.attribute.line"
    
    sequence = fields.Integer(string="Sequence", default=1)