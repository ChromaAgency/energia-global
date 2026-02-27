/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";
import { ThreeJSDialog } from "./three_viewer";

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
            fieldsStructure["stock.move"] &&
            !fieldsStructure["stock.move"].includes("has_render_3d")
        ) {
            fieldsStructure["stock.move"].push("has_render_3d");
        }
        if (
            fieldsStructure["stock.move"] &&
            !fieldsStructure["stock.move"].includes("render_3d_filename")
        ) {
            fieldsStructure["stock.move"].push("render_3d_filename");
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
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
    },

    openThreeDViewer(record) {
        if (!record?.data?.has_render_3d) {
            this.notification.add("No hay plano 3D disponible.", { type: "warning" });
            return;
        }
        const resId = record.resId || record.data.id;
        const resModel = record.resModel || "stock.move";
        if (!resId) {
            this.notification.add("No se pudo identificar el componente.", { type: "danger" });
            return;
        }
        const modelUrl = `/web/content?model=${resModel}&id=${resId}&field=render_3d_file&filename_field=render_3d_filename&download=false`;
        this.dialog.add(ThreeJSDialog, {
            title: "Plano",
            modelUrl,
            filename: record.data.render_3d_filename,
        });
    },

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
