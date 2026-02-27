/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { StockMove } from "@mrp_workorder/mrp_display/stock_move";
patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        const fieldsStructure = super.fieldsStructure;
        const ensureField = (model, fieldName) => {
            if (fieldsStructure[model] && !fieldsStructure[model].includes(fieldName)) {
                fieldsStructure[model].push(fieldName);
            }
        };
        ensureField("stock.move", "related_workcenter_ids");
        ensureField("stock.move", "alternative_product_id");
        ensureField("stock.move", "cnc_number");
        ensureField("stock.move", "weld_group");
        ensureField("stock.move", "is_unlocked");
        ensureField("mrp.production", "origin");
        ensureField("mrp.production", "customer_name");
        ensureField("mrp.workcenter", "behavior_type");
        ensureField("mrp.workcenter", "grouping_field");
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
        const productionMoves = this.props.production.data.move_raw_ids.records.filter(
            (move) => !move.data.scrapped && move.data.check_id && !move.data.check_id.count
        );
        return this._filterMovesByWorkcenter(productionMoves);
    },
});

patch(StockMove.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    },

    _getWorkorderRecord() {
        return (
            this.props.workorder ||
            this.props.workorderRecord ||
            this.props.workorder_record ||
            this.props.record?.model?.root?.data?.workorder_id
        );
    },

    _getWorkorderId() {
        const workorder = this._getWorkorderRecord();
        if (typeof workorder === "number") {
            return workorder;
        }
        return workorder?.resId || workorder?.id || workorder?.data?.id;
    },

    _getBehaviorType() {
        const workorder = this._getWorkorderRecord();
        const workcenter = workorder?.data?.workcenter_id;
        return workcenter?.data?.behavior_type || "individual";
    },

    async _handlePieceAction(action) {
        const workorderId = this._getWorkorderId();
        const moveId = this.props.record?.resId || this.props.record?.data?.id;
        if (!workorderId || !moveId) {
            this.notification.add(_t("No se pudo identificar la orden de trabajo."), {
                type: "warning",
            });
            return;
        }

        if (action === "start") {
            const unlocked = await this.orm.call("mrp.workorder", "check_move_unlocked", [
                workorderId,
                moveId,
            ]);
            if (!unlocked) {
                this.notification.add(
                    _t("La pieza está bloqueada hasta finalizar la operación anterior."),
                    { type: "warning" }
                );
                return;
            }
        }

        const behaviorType = this._getBehaviorType();
        const method =
            action === "start"
                ? "action_start_piece_time"
                : action === "pause"
                ? "action_pause_piece_time"
                : "action_stop_piece_time";
        await this.orm.call(
            "mrp.workorder",
            method,
            [workorderId, moveId],
            { kwargs: { grouped: behaviorType === "grouped" } }
        );
    },

    async onStartPiece(ev) {
        ev.stopPropagation();
        await this._handlePieceAction("start");
    },

    async onPausePiece(ev) {
        ev.stopPropagation();
        await this._handlePieceAction("pause");
    },

    async onStopPiece(ev) {
        ev.stopPropagation();
        await this._handlePieceAction("stop");
    },
});
