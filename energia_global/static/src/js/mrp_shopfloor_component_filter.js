/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { StockMove } from "@mrp_workorder/mrp_display/mrp_record_line/stock_move";

const PIECE_STATE_REFRESH_EVENT = "energia_global:piece_state_refresh";

patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        const fieldsStructure = super.fieldsStructure;
        const ensureField = (model, fieldName) => {
            if (fieldsStructure[model] && !fieldsStructure[model].includes(fieldName)) {
                fieldsStructure[model].push(fieldName);
            }
        };
        ensureField("stock.move", "related_workcenter_ids");
        ensureField("stock.move", "related_operation_ids");
        ensureField("stock.move", "alternative_product_id");
        ensureField("stock.move", "cnc_number");
        ensureField("stock.move", "weld_group");
        ensureField("stock.move", "is_unlocked");
        ensureField("mrp.production", "origin");
        ensureField("mrp.production", "customer_name");
        ensureField("mrp.production", "workorder_ids");
        ensureField("mrp.workorder", "workcenter_id");
        ensureField("mrp.workcenter", "behavior_type");
        ensureField("mrp.workcenter", "grouping_field");
        return fieldsStructure;
    },
});

patch(MrpDisplayRecord.prototype, {
    _filterMovesByWorkcenter(moves) {
        const workcenterId = this.props.record.data.workcenter_id?.id;
        const contextWorkorderId =
            this.props.record?.resModel === "mrp.workorder" ? this.props.record?.resId : false;
        return moves.filter((move) => {
            const relatedWorkcenters = move.data.related_workcenter_ids?.resIds || [];
            if (!relatedWorkcenters.length) {
                return false;
            }
            if (!workcenterId) {
                return true;
            }
            const isRelatedToCurrentWorkcenter = relatedWorkcenters.includes(workcenterId);
            if (!isRelatedToCurrentWorkcenter) {
                return false;
            }
            move.data._context_workcenter_id = workcenterId;
            move.data._context_workorder_id = contextWorkorderId;
            return true;
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
        this.uiState = useState({
            pieceState: "idle",
            isUnlocked: false,
            blockedByText: false,
        });
        onWillStart(async () => {
            await this._refreshPieceState();
        });
        this._onPieceStateRefresh = () => {
            this._refreshPieceState();
        };
        if (typeof window !== "undefined") {
            window.addEventListener(PIECE_STATE_REFRESH_EVENT, this._onPieceStateRefresh);
        }
        onWillUnmount(() => {
            if (typeof window !== "undefined") {
                window.removeEventListener(PIECE_STATE_REFRESH_EVENT, this._onPieceStateRefresh);
            }
        });
    },

    get showStartButton() {
        return (
            (this.uiState.pieceState === "idle" || this.uiState.pieceState === "paused") &&
            this.uiState.isUnlocked
        );
    },

    get showPauseStopButtons() {
        return this.uiState.pieceState === "working";
    },

    get showBlockedInfo() {
        return !this.uiState.isUnlocked && this.uiState.pieceState !== "working" && this.uiState.blockedByText;
    },

    async _refreshPieceState() {
        if (this._refreshingState) {
            return;
        }
        this._refreshingState = true;
        const moveId = this.props.record?.resId || this.props.record?.data?.id;
        try {
            if (!moveId) {
                this.uiState.pieceState = "idle";
                this.uiState.isUnlocked = false;
                this.uiState.blockedByText = false;
                return;
            }
            const workorderId = await this._resolveWorkorderId(moveId);
            if (!workorderId) {
                this.uiState.pieceState = "idle";
                this.uiState.isUnlocked = false;
                this.uiState.blockedByText = false;
                return;
            }
            const status = await this.orm.call("mrp.workorder", "get_move_timer_status", [
                workorderId,
                moveId,
            ]);
            this.uiState.pieceState = status?.piece_state || "idle";
            this.uiState.isUnlocked = Boolean(status?.is_unlocked);
            this.uiState.blockedByText = status?.blocked_by_text || false;
        } finally {
            this._refreshingState = false;
        }
    },

    _getWorkorderRecord() {
        const contextWorkorderId = this.props?.record?.data?._context_workorder_id;
        if (contextWorkorderId) {
            return contextWorkorderId;
        }
        const rootRecord = this.props?.record?.model?.root;
        if (rootRecord?.resModel === "mrp.workorder") {
            return rootRecord;
        }
        const directWorkorder = (
            this.props?.record?.data?.workorder_id ||
            this.props.workorder ||
            this.props.workorderRecord ||
            this.props.workorder_record ||
            this.props.record?.model?.root?.data?.workorder_id
        );
        if (directWorkorder) {
            return directWorkorder;
        }
        return this._getWorkorderFromProductionByCurrentWorkcenter();
    },

    _getCurrentWorkcenterId() {
        const contextWorkcenterId = this.props?.record?.data?._context_workcenter_id;
        if (contextWorkcenterId) {
            return contextWorkcenterId;
        }
        const rootRecord = this.props?.record?.model?.root;
        if (rootRecord?.resModel === "mrp.workorder") {
            const rootWorkcenter = rootRecord?.data?.workcenter_id;
            const rootWorkcenterId =
                rootWorkcenter?.resId || rootWorkcenter?.id || rootWorkcenter?.data?.id;
            if (rootWorkcenterId) {
                return rootWorkcenterId;
            }
        }
        const fromRecord = this.props?.record?.data?.workcenter_id;
        const fromWorkorder = this.props?.workorder?.data?.workcenter_id;
        const fromRoot = this.props?.record?.model?.root?.data?.workcenter_id;
        const workcenter = fromRecord || fromWorkorder || fromRoot;
        return workcenter?.resId || workcenter?.id || workcenter?.data?.id;
    },

    _getWorkorderFromProductionByCurrentWorkcenter() {
        const workcenterId = this._getCurrentWorkcenterId();
        const workorders = this.props?.production?.data?.workorder_ids?.records || [];
        if (!workcenterId || !workorders.length) {
            return null;
        }
        return (
            workorders.find((workorder) => {
                const currentWorkcenter = workorder?.data?.workcenter_id;
                const currentWorkcenterId =
                    currentWorkcenter?.resId ||
                    currentWorkcenter?.id ||
                    currentWorkcenter?.data?.id;
                return currentWorkcenterId === workcenterId;
            }) || null
        );
    },

    _getWorkorderIdFromProps() {
        const workorder = this._getWorkorderRecord();
        if (typeof workorder === "number") {
            return workorder;
        }
        if (workorder?.resModel === "mrp.workorder" && workorder?.resId) {
            return workorder.resId;
        }
        return workorder?.resId || workorder?.id || workorder?.data?.id;
    },

    async _resolveWorkorderId(moveId) {
        const workorderIdFromProps = this._getWorkorderIdFromProps();
        if (workorderIdFromProps) {
            return workorderIdFromProps;
        }
        const currentWorkcenterId = this._getCurrentWorkcenterId();
        return await this.orm.call("mrp.workorder", "resolve_workorder_for_move", [
            moveId,
            currentWorkcenterId || false,
        ]);
    },

    async _handlePieceAction(action) {
        const moveId = this.props.record?.resId || this.props.record?.data?.id;
        if (!moveId) {
            this.notification.add(_t("No se pudo identificar el componente."), {
                type: "warning",
            });
            return;
        }
        const workorderId = await this._resolveWorkorderId(moveId);
        if (!workorderId) {
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
                    _t("La pieza está bloqueada hasta completar todas las operaciones que la bloquean."),
                    { type: "warning" }
                );
                await this._refreshPieceState();
                return;
            }
        }

        const method =
            action === "start"
                ? "action_start_piece_time"
                : action === "pause"
                ? "action_pause_piece_time"
                : "action_stop_piece_time";
        await this.orm.call("mrp.workorder", method, [workorderId, moveId]);
        await this._refreshPieceState();
        if (typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent(PIECE_STATE_REFRESH_EVENT));
        }
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
