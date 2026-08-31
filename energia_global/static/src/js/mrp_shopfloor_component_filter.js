/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { StockMove } from "@mrp_workorder/mrp_display/mrp_record_line/stock_move";

const PIECE_STATE_REFRESH_EVENT = "energia_global:piece_state_refresh";

import { ThreeJSDialog } from "./three_viewer";

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
        ensureField("stock.move", "bom_line_id");
        ensureField("stock.move", "final_product_id");
        ensureField("stock.move", "component_operation_stage_label");
        ensureField("stock.move", "component_finalization_state_label");
        ensureField("stock.move", "cnc_number");
        
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
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.cncUiState = useState({
            loading: false,
            records: [],
        });
        onWillStart(async () => {
            await this._refreshCncTracking();
        });
    },


    _getRecordKey(record) {
        return record?.resId ?? record?.data?.id ?? record?.id;
    },

    _dedupeRecords(records) {
        const seen = new Set();
        return (records || []).filter((record) => {
            const key = this._getRecordKey(record);
            if (key == null) {
                return false;
            }
            if (seen.has(key)) {
                return false;
            }
            seen.add(key);
            return true;
        });
    },

    _getRelatedWorkcenterIds(move) {
        const related = move.data.related_workcenter_ids;
        if (!related) {
            return [];
        }
        if (related.resIds?.length) {
            return related.resIds;
        }
        return (related.records || [])
            .map((workcenter) => workcenter.resId || workcenter.id || workcenter.data?.id)
            .filter(Boolean);
    },

    _filterMovesByWorkcenter(moves) {
        const workcenterId = this.props.record.data.workcenter_id?.id;
        return moves.filter((move) => {
            const relatedWorkcenters = this._getRelatedWorkcenterIds(move);
            // Only show components mapped to workcenters; unmapped ones appear
            // "Bloqueado por" the previous WO forever (no piece timer there).
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
        return this._dedupeRecords(this._filterMovesByWorkcenter(super.moves));
    },

    get checks() {
        return this._dedupeRecords(super.checks);
    },

    get byProducts() {
        return this._dedupeRecords(super.byProducts);
    },

    get isWorkorderRecord() {
        return this.props.record?.resModel === "mrp.workorder";
    },

    _extractRecordId(value) {
        if (!value) {
            return false;
        }
        if (typeof value === "number") {
            return value;
        }
        return value.resId || value.id || value.data?.id || false;
    },

    _getWorkorderId() {
        if (this.isWorkorderRecord && this.props.record?.resId) {
            return this.props.record.resId;
        }
        return this._extractRecordId(this.props.record?.data?.workorder_id);
    },

    _getProductionId() {
        const fromPropsProduction = this._extractRecordId(this.props.production);
        if (fromPropsProduction) {
            return fromPropsProduction;
        }
        return this._extractRecordId(this.props.record?.data?.production_id);
    },

    _getCurrentWorkcenterName() {
        const workcenter = this.props.record?.data?.workcenter_id;
        return (workcenter?.display_name || workcenter?.data?.display_name || "").toLowerCase();
    },

    get showCncPanel() {
        if (!this.isWorkorderRecord) {
            return false;
        }
        const workcenterName = this._getCurrentWorkcenterName();
        return workcenterName.includes("laser") || workcenterName.includes("láser") || workcenterName.includes("cnc");
    },

    async _refreshCncTracking() {
        if (!this.showCncPanel) {
            this.cncUiState.records = [];
            return;
        }
        const productionId = this._getProductionId();
        if (!productionId) {
            this.cncUiState.records = [];
            return;
        }
        this.cncUiState.loading = true;
        try {
            const cncRows = await this.orm.searchRead(
                "mrp.cnc.tracking",
                [["production_id", "=", productionId]],
                ["id", "cnc_number", "quantity", "state", "user_id", "duration", "has_render_3d", "render_3d_filename"],
                { order: "sequence asc, id asc" }
            );
            this.cncUiState.records = cncRows || [];
        } finally {
            this.cncUiState.loading = false;
        }
    },

    _getCncModelUrl(cncId) {
        return `/web/content?model=mrp.cnc.tracking&id=${cncId}&field=render_3d_file&filename_field=render_3d_filename&download=false`;
    },

    _canOpenCncPlan(record) {
        return Boolean(record?.has_render_3d || record?.render_3d_filename);
    },

    onOpenCncPlan(record, ev) {
        ev.stopPropagation();
        if (!this._canOpenCncPlan(record)) {
            this.notification.add(_t("No hay plano 3D disponible para este CNC."), {
                type: "warning",
            });
            return;
        }
        this.dialog.add(ThreeJSDialog, {
            title: _t("Plano CNC"),
            modelUrl: this._getCncModelUrl(record.id),
            filename: record.render_3d_filename,
        });
    },

    _canStartCnc(record) {
        return record.state === "idle" || record.state === "paused";
    },

    _canPauseCnc(record) {
        return record.state === "working";
    },

    _canResumeCnc(record) {
        return record.state === "paused";
    },

    _canFinishCnc(record) {
        return record.state === "working" || record.state === "paused";
    },

    _formatCncDuration(duration) {
        const numericDuration = Number(duration || 0);
        return `${numericDuration.toFixed(2)} min`;
    },

    async _runCncAction(cncId, methodName) {
        if (!cncId) {
            return;
        }
        await this.orm.call("mrp.cnc.tracking", methodName, [[cncId]]);
        await this._refreshCncTracking();
    },

    async onStartCnc(record, ev) {
        ev.stopPropagation();
        await this._runCncAction(record.id, "action_start");
    },

    async onPauseCnc(record, ev) {
        ev.stopPropagation();
        await this._runCncAction(record.id, "action_pause");
    },

    async onResumeCnc(record, ev) {
        ev.stopPropagation();
        await this._runCncAction(record.id, "action_resume");
    },

    async onFinishCnc(record, ev) {
        ev.stopPropagation();
        await this._runCncAction(record.id, "action_finish");
    },

    subRecordProps(subRecord) {
        const props = super.subRecordProps(subRecord);
        // Moves come from production.move_raw_ids, so record.model.root is the MO.
        // Pass the WO card explicitly so piece timers resolve the correct workorder.
        if (this.props.record?.resModel === "mrp.workorder") {
            props.workorder = this.props.record;
        }
        return props;
    },
});

patch(StockMove, {
    props: {
        ...StockMove.props,
        workorder: { type: Object, optional: true },
    },
});

patch(StockMove.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._workcenterBehaviorCache = {};
        this._workcenterGroupingFieldCache = {};
        this.uiState = useState({
            pieceState: "idle",
            isUnlocked: true,
            blockedByText: false,
            viewerOpenCount: 0,
        });
        onMounted(() => {
            this._refreshPieceState();
        });
        this._onPieceStateRefresh = (ev) => {
            this._handlePieceStateRefreshEvent(ev);
        };
        if (typeof window !== "undefined") {
            window.addEventListener(PIECE_STATE_REFRESH_EVENT, this._onPieceStateRefresh);
        }
        onWillUnmount(() => {
            if (this._groupRefreshTimeout) {
                clearTimeout(this._groupRefreshTimeout);
                this._groupRefreshTimeout = null;
            }
            if (typeof window !== "undefined") {
                window.removeEventListener(PIECE_STATE_REFRESH_EVENT, this._onPieceStateRefresh);
            }
        });
    },

    _getCurrentMoveId() {
        return this.props.record?.resId || this.props.record?.data?.id;
    },

    _applyPieceStateFromAction(action) {
        if (action === "start") {
            this.uiState.pieceState = "working";
            this.uiState.isUnlocked = true;
            this.uiState.blockedByText = false;
            return;
        }
        if (action === "pause") {
            this.uiState.pieceState = "paused";
            this.uiState.isUnlocked = true;
            this.uiState.blockedByText = false;
            return;
        }
        if (action === "stop") {
            this.uiState.pieceState = "done";
            this.uiState.isUnlocked = true;
            this.uiState.blockedByText = false;
        }
    },

    _handlePieceStateRefreshEvent(ev) {
        const detail = ev?.detail || {};
        if (detail?.scope !== "grouped") {
            this._refreshPieceState();
            return;
        }
        const currentMoveId = this._getCurrentMoveId();
        if (!currentMoveId) {
            return;
        }
        const currentWorkcenterId = this._getCurrentWorkcenterId();
        if (detail.workcenterId && currentWorkcenterId && detail.workcenterId !== currentWorkcenterId) {
            return;
        }
        const sameMove = detail.sourceMoveId === currentMoveId;
        const ownGroupValue = detail.groupingField ? this.props.record?.data?.[detail.groupingField] : false;
        const sameGroup = Boolean(
            !sameMove && detail.groupingField && detail.groupValue && ownGroupValue === detail.groupValue
        );
        if (!sameMove && !sameGroup) {
            return;
        }
        this._applyPieceStateFromAction(detail.action);
        if (sameMove) {
            this._refreshPieceState();
            return;
        }
        if (this._groupRefreshTimeout) {
            clearTimeout(this._groupRefreshTimeout);
        }
        this._groupRefreshTimeout = setTimeout(() => {
            this._refreshPieceState();
            this._groupRefreshTimeout = null;
        }, 900);
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
                this.uiState.blockedByText = _t("No se pudo identificar el componente.");
                return;
            }
            const workorderId = await this._resolveWorkorderId(moveId);
            if (!workorderId) {
                this.uiState.pieceState = "idle";
                this.uiState.isUnlocked = false;
                this.uiState.blockedByText = _t("No se pudo identificar la orden de trabajo.");
                return;
            }
            const status = await this.orm.call("mrp.workorder", "get_move_timer_status", [
                workorderId,
                moveId,
            ]);
            this.uiState.pieceState = status?.piece_state || "idle";
            this.uiState.isUnlocked = Boolean(status?.is_unlocked);
            this.uiState.blockedByText = status?.blocked_by_text || false;
        } catch (_error) {
            this.uiState.pieceState = "idle";
            this.uiState.isUnlocked = false;
            this.uiState.blockedByText = _t("No se pudo cargar el estado de la pieza.");
        } finally {
            this._refreshingState = false;
        }
    },

    _getWorkorderRecord() {
        if (this.props.workorder) {
            return this.props.workorder;
        }
        const rootRecord = this.props?.record?.model?.root;
        if (rootRecord?.resModel === "mrp.workorder") {
            return rootRecord;
        }
        const directWorkorder = (
            this.props?.record?.data?.workorder_id ||
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
        const workorder = this.props.workorder;
        if (workorder?.resModel === "mrp.workorder") {
            const workcenter = workorder.data?.workcenter_id;
            const workcenterId = workcenter?.resId || workcenter?.id || workcenter?.data?.id;
            if (workcenterId) {
                return workcenterId;
            }
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

    _getCurrentWorkcenterRecord() {
        const workorder = this.props.workorder;
        if (workorder?.resModel === "mrp.workorder" && workorder?.data?.workcenter_id) {
            return workorder.data.workcenter_id;
        }
        const rootRecord = this.props?.record?.model?.root;
        if (rootRecord?.resModel === "mrp.workorder" && rootRecord?.data?.workcenter_id) {
            return rootRecord.data.workcenter_id;
        }
        const fromRecord = this.props?.record?.data?.workcenter_id;
        const fromWorkorder = this.props?.workorder?.data?.workcenter_id;
        const fromRoot = this.props?.record?.model?.root?.data?.workcenter_id;
        return fromRecord || fromWorkorder || fromRoot || null;
    },

    _getWorkcenterBehaviorTypeFromData() {
        const workcenter = this._getCurrentWorkcenterRecord();
        return workcenter?.behavior_type || workcenter?.data?.behavior_type || false;
    },

    _getWorkcenterGroupingFieldFromData() {
        const workcenter = this._getCurrentWorkcenterRecord();
        return workcenter?.grouping_field || workcenter?.data?.grouping_field || false;
    },

    async _resolveGroupingField(workorderId) {
        const localGroupingField = this._getWorkcenterGroupingFieldFromData();
        if (localGroupingField) {
            return localGroupingField;
        }
        if (!workorderId) {
            return false;
        }
        if (Object.prototype.hasOwnProperty.call(this._workcenterGroupingFieldCache, workorderId)) {
            return this._workcenterGroupingFieldCache[workorderId] || false;
        }
        try {
            const [workorderData] = await this.orm.read("mrp.workorder", [workorderId], ["workcenter_id"]);
            const workcenterId = workorderData?.workcenter_id?.[0];
            if (!workcenterId) {
                this._workcenterGroupingFieldCache[workorderId] = false;
                return false;
            }
            const [workcenterData] = await this.orm.read("mrp.workcenter", [workcenterId], ["grouping_field"]);
            const groupingField = workcenterData?.grouping_field || false;
            this._workcenterGroupingFieldCache[workorderId] = groupingField;
            return groupingField;
        } catch (_error) {
            return false;
        }
    },

    _dispatchPieceStateRefresh(detail = {}) {
        if (typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent(PIECE_STATE_REFRESH_EVENT, { detail }));
        }
    },

    async _isGroupedWorkcenter(workorderId) {
        const localBehaviorType = this._getWorkcenterBehaviorTypeFromData();
        if (localBehaviorType) {
            return localBehaviorType === "grouped";
        }
        if (!workorderId) {
            return null;
        }
        if (Object.prototype.hasOwnProperty.call(this._workcenterBehaviorCache, workorderId)) {
            return this._workcenterBehaviorCache[workorderId] === "grouped";
        }
        try {
            const [workorderData] = await this.orm.read("mrp.workorder", [workorderId], ["workcenter_id"]);
            const workcenterId = workorderData?.workcenter_id?.[0];
            if (!workcenterId) {
                this._workcenterBehaviorCache[workorderId] = false;
                return null;
            }
            const [workcenterData] = await this.orm.read("mrp.workcenter", [workcenterId], ["behavior_type"]);
            const behaviorType = workcenterData?.behavior_type || false;
            this._workcenterBehaviorCache[workorderId] = behaviorType;
            return behaviorType === "grouped";
        } catch (_error) {
            return null;
        }
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
        const currentWorkcenterId = this._getCurrentWorkcenterId();
        const workorderIdFromProps = this._getWorkorderIdFromProps();
        if (workorderIdFromProps) {
            if (!currentWorkcenterId) {
                return workorderIdFromProps;
            }
            try {
                const [workorderData] = await this.orm.read(
                    "mrp.workorder",
                    [workorderIdFromProps],
                    ["workcenter_id"]
                );
                const workorderWorkcenterId = workorderData?.workcenter_id?.[0];
                if (workorderWorkcenterId === currentWorkcenterId) {
                    return workorderIdFromProps;
                }
            } catch (_error) {
                // If the lightweight validation fails, fall back to explicit resolution below.
            }
        }
        return await this.orm.call("mrp.workorder", "resolve_workorder_for_move", [
            moveId,
            currentWorkcenterId || false,
        ]);
    },

    async _handlePieceAction(action, options = {}) {
        const moveId = this.props.record?.resId || this.props.record?.data?.id;
        if (!moveId) {
            if (!options.silent) {
                this.notification.add(_t("No se pudo identificar el componente."), {
                    type: "warning",
                });
            }
            return;
        }
        const workorderId = await this._resolveWorkorderId(moveId);
        if (!workorderId) {
            if (!options.silent) {
                this.notification.add(_t("No se pudo identificar la orden de trabajo."), {
                    type: "warning",
                });
            }
            return;
        }

        if (action === "pause" && options.skipIfNotWorking && this.uiState.pieceState !== "working") {
            return;
        }

        const grouped = await this._isGroupedWorkcenter(workorderId);
        const groupedArg = grouped === true ? true : null;

        if (action === "start") {
            const unlocked = await this.orm.call("mrp.workorder", "check_move_unlocked", [
                workorderId,
                moveId,
                groupedArg,
            ]);
            if (!unlocked) {
                if (!options.silent) {
                    this.notification.add(
                        _t("La pieza está bloqueada hasta completar todas las operaciones que la bloquean."),
                        { type: "warning" }
                    );
                }
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
        await this.orm.call("mrp.workorder", method, [workorderId, moveId, groupedArg]);
        await this._refreshPieceState();
        const groupingField = groupedArg ? await this._resolveGroupingField(workorderId) : false;
        const groupValue = groupingField ? this.props.record?.data?.[groupingField] : false;
        if (groupedArg && groupingField && groupValue) {
            this._dispatchPieceStateRefresh({
                scope: "grouped",
                action,
                sourceMoveId: moveId,
                workcenterId: this._getCurrentWorkcenterId(),
                groupingField,
                groupValue,
            });
        } else {
            this._dispatchPieceStateRefresh();
        }
    },

    async _handleViewerOpened() {
        if (this.uiState.viewerOpenCount === 0) {
            await this._handlePieceAction("start", { silent: true });
        }
        this.uiState.viewerOpenCount += 1;
    },

    async _handleViewerClosed() {
        this.uiState.viewerOpenCount = Math.max(0, (this.uiState.viewerOpenCount || 0) - 1);
        if (this.uiState.viewerOpenCount > 0) {
            return;
        }
        await this._refreshPieceState();
        await this._handlePieceAction("pause", { silent: true, skipIfNotWorking: true });
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

    openThreeDViewer(e) {
        e.stopPropagation();
        const record = this.props.record;
        if (!record?.data?.has_render_3d) {
            this.notification.add(_t("No hay plano 3D disponible."), { type: "warning" });
            return;
        }
        const resId = record.resId || record.data.id;
        const resModel = record.resModel || "stock.move";
        if (!resId) {
            this.notification.add(_t("No se pudo identificar el componente."), { type: "danger" });
            return;
        }
        const modelUrl = `/web/content?model=${resModel}&id=${resId}&field=render_3d_file&filename_field=render_3d_filename&download=false`;
        this.dialog.add(ThreeJSDialog, {
            title: _t("Plano"),
            modelUrl,
            filename: record.data.render_3d_filename,
            onOpen: () => this._handleViewerOpened(),
            onClose: () => this._handleViewerClosed(),
        });
    },
});
