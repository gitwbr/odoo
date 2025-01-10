/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FilterMenu } from "@web/search/filter_menu/filter_menu";
import { CustomFilterItem } from "@web/search/filter_menu/custom_filter_item";
import { useService } from "@web/core/utils/hooks";

export class CustomFilterItemOverride extends CustomFilterItem {
    setup() {
        super.setup();
        this.rpc = require('web.rpc');

        const viewId = this.env.searchModel?.config?.viewId || this.env.config?.viewId;
        if (!viewId) {
            console.error("viewId is undefined");
            return;
        }
        console.log("View ID (Numeric):", viewId);

        // 通过 RPC 获取外部 ID
        this.rpc.query({
            model: 'ir.model.data',
            method: 'search_read',
            args: [
                [['model', '=', 'ir.ui.view'], ['res_id', '=', viewId]],
                ['module', 'name']
            ],
        }).then((result) => {
            if (result.length > 0) {
                const externalId = `${result[0].module}.${result[0].name}`;
                console.log("External ID:", externalId);

                if (externalId === 'dtsc.report_checkout_treee' ||
                    externalId === 'dtsc.report_checkout_sales' ||
                    externalId === 'dtsc.report_checkoutline_machine' ||
                    externalId === 'dtsc.report_checkoutline_product') {

                    console.log('Applying filter for estimated_date_only field');
                    this.fields = this.fields.filter(field => field.name === 'estimated_date_only');
                    console.log("Filtered fields: ", this.fields);

                    // 只设置字段，不添加初始条件，让系统自动处理“介于”操作符
                    // 强制刷新组件以应用新的 fields
                    this.render();
                }

                if (externalId === 'dtsc.report_makeout_product') {
                    console.log('Applying filter for delivery_date field');
                    this.fields = this.fields.filter(field => field.name === 'delivery_date');
                    console.log("Filtered fields: ", this.fields);

                    // 只设置字段，不添加初始条件，让系统自动处理“介于”操作符
                    // 强制刷新组件以应用新的 fields
                    this.render();
                }
            } else {
                console.log("External ID not found for this view.");
            }
        }).catch((error) => {
            console.error("Error accessing viewId or searchModel:", error);
        });
    }
}

export class FilterMenuOverride extends FilterMenu {
    setup() {
        super.setup();
        console.log("FilterMenuOverride loaded");
    }
}

FilterMenuOverride.components.CustomFilterItem = CustomFilterItemOverride;
registry.category("components").add("FilterMenu", FilterMenuOverride);
