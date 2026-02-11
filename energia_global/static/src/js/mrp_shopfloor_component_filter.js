/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

patch(MrpDisplay.prototype, {
    setup(){
        super.setup();
        console.log(this)
    }
})
patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        const fieldsStructure = super.fieldsStructure
        if (
            fieldsStructure["stock.move"] &&
            !fieldsStructure["stock.move"].includes("related_workcenter_ids")
        ) {
            fieldsStructure["stock.move"].push("related_workcenter_ids");
        }
        if (
            fieldsStructure["stock.move"] &&
            !fieldsStructure["stock.move"].includes("alternative_product_id")
        ) {
            fieldsStructure["stock.move"].push("alternative_product_id");
        }
        if (
            fieldsStructure["mrp.production"] &&
            !fieldsStructure["mrp.production"].includes("origin")
        ) {
            fieldsStructure["mrp.production"].push("origin");
        }
        if (
            fieldsStructure["mrp.production"] &&
            !fieldsStructure["mrp.production"].includes("customer_name")
        ) {
            fieldsStructure["mrp.production"].push("customer_name");
        }
        return fieldsStructure;
    },
});

patch(MrpDisplayRecord.prototype, {
    _filterMovesByWorkcenter(moves) {
        const workcenterId = this.props.record.data.workcenter_id?.id;
        return moves.filter((move) => {
            const relatedWorkcenters = move.data.related_workcenter_ids?.resIds || [];
            if (!relatedWorkcenters.length) {
                return false;
            }
            if (!workcenterId) {
                return true;
            }
            return relatedWorkcenters.includes(workcenterId);
        });
    },

    get moves() {
        console.log("this.prod",this.props.production)
        const productionMoves = this.props.production.data.move_raw_ids.records.filter(
            (move) => !move.data.scrapped && move.data.check_id && !move.data.check_id.count
        );
        return this._filterMovesByWorkcenter(productionMoves);
    },
});
