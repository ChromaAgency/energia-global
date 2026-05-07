/** @odoo-module */

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
const MODEL_EXTENSIONS = new Set(["glb", "gltf", "obj", "fbx"]);

const MIN_LINE_RADIUS = 0.002;
const MAX_LINE_RADIUS = 20;

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function isImageFilename(filename) {
    if (!filename) {
        return false;
    }
    const parts = filename.split(".");
    if (parts.length < 2) {
        return false;
    }
    return IMAGE_EXTENSIONS.has(parts.pop().toLowerCase());
}



export class ThreeJSViewer extends Component {
    static template = "energia_global.ThreeJSViewer";

    setup() {
        this.containerRef = useRef("canvasContainer");
        this.state = useState({
            loading: true,
            error: null,
            mode: "navigate",
            statusText: "",
            unitToCm: 1,
        });
        this._objectUrl = null;
        this._raycaster = null;
        this._pointer = null;
        this._measureGroup = null;
        this._previewGroup = null;
        this._pendingPoint = null;
        this._angleVertex = null;
        this._angleArmPoint = null;
        this._modelObject = null;
        this._modelMaxDim = 1;
        this._lastValidPoint = null;
        this._onCanvasPointerDown = this._onCanvasPointerDown.bind(this);
        this._onCanvasPointerMove = this._onCanvasPointerMove.bind(this);
        this._onResize = this._onResize.bind(this);
        onMounted(() => this._initScene());
        onWillUnmount(() => this._cleanup());
    }

    async _initScene() {
        try {
            const modelUrl = this._getModelUrl();
            if (!modelUrl) {
                throw new Error("No se encontro un modelo 3D para cargar.");
            }
            const THREE = window.THREE;
            if (!THREE) {
                throw new Error("Three.js no esta disponible en assets.");
            }
            const container = this.containerRef.el;
            const { width, height } = container.getBoundingClientRect();
            this.scene = new THREE.Scene();
            this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000);
            this.camera.position.set(2, 2, 2);

            this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
            this.renderer.setSize(width, height);
            container.appendChild(this.renderer.domElement);

            const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
            dirLight.position.set(5, 5, 5);
            this.scene.add(ambientLight, dirLight);

            this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
            this.controls.enableDamping = true;
            this.controls.zoomSpeed = 1.1;

            this._raycaster = new THREE.Raycaster();
            this._pointer = new THREE.Vector2();
            this._measureGroup = new THREE.Group();
            this._previewGroup = new THREE.Group();
            this.scene.add(this._measureGroup);
            this.scene.add(this._previewGroup);

            this.renderer.domElement.addEventListener("pointerdown", this._onCanvasPointerDown);
            this.renderer.domElement.addEventListener("pointermove", this._onCanvasPointerMove);
            window.addEventListener("resize", this._onResize);

            const extension = this._getModelExtension();
            await this._loadModel(THREE, modelUrl, extension);
            this.state.loading = false;
            this._startRenderLoop();
        } catch (error) {
            this.state.loading = false;
            this.state.error = error?.message || "Error cargando el modelo 3D.";
        }
    }

    _startRenderLoop() {
        const animate = () => {
            this.controls?.update();
            this.renderer?.render(this.scene, this.camera);
            this._animationId = requestAnimationFrame(animate);
        };
        animate();
    }

    _getModelUrl() {
        if (this.props.modelUrl) {
            return this.props.modelUrl;
        }
        if (!this.props.base64Data) {
            return null;
        }
        if (this.props.base64Data.startsWith("data:")) {
            return this.props.base64Data;
        }
        const extension = this._getModelExtension();
        if (!MODEL_EXTENSIONS.has(extension)) {
            return null;
        }
        const byteString = atob(this.props.base64Data);
        const arrayBuffer = new Uint8Array(byteString.length);
        for (let i = 0; i < byteString.length; i++) {
            arrayBuffer[i] = byteString.charCodeAt(i);
        }
        const blob = new Blob([arrayBuffer], { type: this._getMimeType(extension) });
        this._objectUrl = URL.createObjectURL(blob);
        return this._objectUrl;
    }

    _getModelExtension() {
        if (!this.props.filename) {
            return "glb";
        }
        const parts = this.props.filename.split(".");
        if (parts.length < 2) {
            return "glb";
        }
        return parts.pop().toLowerCase();
    }

    _getMimeType(extension) {
        switch (extension) {
            case "gltf":
                return "model/gltf+json";
            case "obj":
                return "text/plain";
            case "fbx":
                return "application/octet-stream";
            default:
                return "model/gltf-binary";
        }
    }

    async _loadModel(THREE, modelUrl, extension) {
        if (!MODEL_EXTENSIONS.has(extension)) {
            throw new Error("Formato 3D no soportado.");
        }
        const addToScene = (object) => {
            this._prepareObject(THREE, object);
            this.scene.add(object);
            this._fitToView(THREE, object);
        };
        const loadWith = (loader, onSuccess) =>
            new Promise((resolve, reject) => {
                loader.load(
                    modelUrl,
                    (data) => {
                        onSuccess(data);
                        resolve();
                    },
                    () => {},
                    (error) => reject(error || new Error("No se pudo cargar el modelo 3D."))
                );
            });
        if (extension === "obj") {
            if (!THREE.OBJLoader) {
                throw new Error("OBJLoader no esta disponible en assets.");
            }
            const loader = new THREE.OBJLoader();
            await loadWith(loader, (object) => addToScene(object));
            return;
        }
        if (extension === "fbx") {
            if (!THREE.FBXLoader) {
                throw new Error("FBXLoader no esta disponible en assets.");
            }
            const loader = new THREE.FBXLoader();
            await loadWith(loader, (object) => addToScene(object));
            return;
        }
        if (!THREE.GLTFLoader) {
            throw new Error("GLTFLoader no esta disponible en assets.");
        }
        const loader = new THREE.GLTFLoader();
        await loadWith(loader, (gltf) => addToScene(gltf.scene));
    }

    _prepareObject(THREE, object) {
        object.traverse((node) => {
            if (node.isMesh) {
                const materials = Array.isArray(node.material) ? node.material : [node.material];
                materials.forEach((material) => {
                    if (material) {
                        material.side = THREE.DoubleSide;
                        material.needsUpdate = true;
                    }
                });
                node.frustumCulled = false;
            }
        });
        object.updateMatrixWorld(true);
    }

    _fitToView(THREE, object) {
        const box = new THREE.Box3().setFromObject(object);
        if (box.isEmpty()) {
            return;
        }
        this._modelObject = object;
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        this._modelMaxDim = maxDim;
        const distance = maxDim * 1.8;
        if (distance * 4 > this.camera.far) {
            this.camera.far = distance * 4;
            this.camera.updateProjectionMatrix();
        }
        this.camera.position.set(center.x + distance, center.y + distance, center.z + distance);
        if (this.controls) {
            this.controls.target.copy(center);
            this.controls.update();
        }
    }

    _onResize() {
        if (!this.renderer || !this.camera || !this.containerRef.el) {
            return;
        }
        const { width, height } = this.containerRef.el.getBoundingClientRect();
        if (!width || !height) {
            return;
        }
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    setMode(mode) {
        if (!["navigate", "distance", "angle"].includes(mode)) {
            return;
        }
        this.state.mode = mode;
        this._pendingPoint = null;
        this._angleVertex = null;
        this._angleArmPoint = null;
        this._clearPreview();
        if (mode === "navigate") {
            this.state.statusText = "";
        } else if (mode === "distance") {
            this.state.statusText = "Seleccione punto inicial.";
        } else {
            this.state.statusText = "Seleccione vertice del angulo.";
        }
    }

    setUnitToCm(ev) {
        const nextValue = Number(ev?.target?.value);
        if (!Number.isFinite(nextValue) || nextValue <= 0) {
            return;
        }
        this.state.unitToCm = nextValue;
    }

    _disposeCurrentModel() {
        if (!this._modelObject || !this.scene) {
            return;
        }
        this.scene.remove(this._modelObject);
        this._modelObject.traverse((node) => {
            if (node.geometry) {
                node.geometry.dispose();
            }
            if (node.material) {
                if (Array.isArray(node.material)) {
                    node.material.forEach((material) => material.dispose?.());
                } else {
                    node.material.dispose?.();
                }
            }
        });
        this._modelObject = null;
    }

    resetCamera() {
        if (!this.controls || !this.camera) {
            return;
        }
        this.camera.position.set(2, 2, 2);
        this.controls.target.set(0, 0, 0);
        this.controls.update();
    }

    fitToModel() {
        const THREE = window.THREE;
        if (!THREE || !this._modelObject) {
            return;
        }
        this._fitToView(THREE, this._modelObject);
    }

    clearMeasurements() {
        this._pendingPoint = null;
        this._angleVertex = null;
        this._angleArmPoint = null;
        this.state.statusText = "";
        this._clearPreview();
        if (!this._measureGroup) {
            return;
        }
        this._clearGroup(this._measureGroup);
    }

    _clearPreview() {
        if (!this._previewGroup) {
            return;
        }
        this._clearGroup(this._previewGroup);
    }

    _clearGroup(group) {
        while (group.children.length) {
            const child = group.children.pop();
            child.geometry?.dispose?.();
            if (Array.isArray(child.material)) {
                child.material.forEach((m) => m.dispose?.());
            } else {
                child.material?.dispose?.();
            }
        }
    }

    _onCanvasPointerDown(ev) {
        if (this.state.mode === "navigate" || this.state.loading || this.state.error) {
            return;
        }
        const hit = this._getIntersection(ev);
        const point = hit?.point?.clone() || this._getFallbackPoint(ev);
        if (!point) {
            return;
        }
        this._lastValidPoint = point.clone();
        if (this.state.mode === "distance") {
            this._handleDistancePick(point);
            return;
        }
        if (this.state.mode === "angle") {
            this._handleAnglePick(point);
        }
    }

    _onCanvasPointerMove(ev) {
        if (this.state.mode === "navigate" || this.state.loading || this.state.error) {
            return;
        }
        const hit = this._getIntersection(ev);
        const point = hit?.point?.clone() || this._getFallbackPoint(ev);
        if (!point) {
            return;
        }
        this._lastValidPoint = point.clone();
        if (this.state.mode === "distance") {
            this._updateDistancePreview(point);
            return;
        }
        if (this.state.mode === "angle") {
            this._updateAnglePreview(point);
        }
    }

    _getFallbackAnchor() {
        if (this.state.mode === "distance" && this._pendingPoint) {
            return this._pendingPoint;
        }
        if (this.state.mode === "angle" && this._angleArmPoint) {
            return this._angleArmPoint;
        }
        if (this.state.mode === "angle" && this._angleVertex) {
            return this._angleVertex;
        }
        return this._lastValidPoint;
    }

    _getFallbackPoint(ev) {
        const THREE = window.THREE;
        if (!THREE || !this._raycaster || !this.renderer || !this.camera) {
            return null;
        }
        const anchor = this._getFallbackAnchor();
        if (!anchor) {
            return null;
        }
        const rect = this.renderer.domElement.getBoundingClientRect();
        const px = ev.clientX - rect.left;
        const py = ev.clientY - rect.top;
        const sx = clamp(px, 0, rect.width);
        const sy = clamp(py, 0, rect.height);
        this._pointer.x = (sx / rect.width) * 2 - 1;
        this._pointer.y = -(sy / rect.height) * 2 + 1;
        this._raycaster.setFromCamera(this._pointer, this.camera);

        const planeNormal = this.camera
            .getWorldDirection(new THREE.Vector3())
            .normalize();
        const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(
            planeNormal,
            anchor.clone()
        );
        const fallback = new THREE.Vector3();
        const ok = this._raycaster.ray.intersectPlane(plane, fallback);
        return ok ? fallback : null;
    }

    _getIntersection(ev) {
        if (!this._raycaster || !this.renderer || !this.camera || !this._modelObject) {
            return null;
        }
        const rect = this.renderer.domElement.getBoundingClientRect();
        const px = ev.clientX - rect.left;
        const py = ev.clientY - rect.top;

        // Muestreo alrededor del cursor para evitar huecos de picking en
        // triangulos finos o bordes complejos del modelo.
        const offsets = [
            [0, 0],
            [2, 0],
            [-2, 0],
            [0, 2],
            [0, -2],
            [3, 3],
            [-3, 3],
            [3, -3],
            [-3, -3],
        ];

        let bestHit = null;
        for (const [dx, dy] of offsets) {
            const sx = clamp(px + dx, 0, rect.width);
            const sy = clamp(py + dy, 0, rect.height);
            this._pointer.x = (sx / rect.width) * 2 - 1;
            this._pointer.y = -(sy / rect.height) * 2 + 1;
            this._raycaster.setFromCamera(this._pointer, this.camera);
            const hits = this._raycaster.intersectObject(this._modelObject, true);
            if (hits.length && (!bestHit || hits[0].distance < bestHit.distance)) {
                bestHit = hits[0];
            }
        }
        return bestHit;
    }

    _makeOverlayMaterial(THREE, color, opacity = 1) {
        return new THREE.MeshBasicMaterial({
            color,
            transparent: opacity < 1,
            opacity,
            depthTest: false,
            depthWrite: false,
            toneMapped: false,
            side: THREE.DoubleSide,
        });
    }

    _getAdaptiveRadius(point, kind = "line", preview = false) {
        const cameraDistance = this.camera ? this.camera.position.distanceTo(point) : 1;
        const modelDim = this._modelMaxDim || 1;
        const minFromModel = Math.max(modelDim * 0.0012, MIN_LINE_RADIUS);
        const maxFromModel = Math.max(modelDim * 0.035, 0.12);
        const factor = preview ? 0.0019 : 0.0028;
        const raw = cameraDistance * factor;
        const lineRadius = clamp(raw, minFromModel, Math.min(maxFromModel, MAX_LINE_RADIUS));
        if (kind === "marker") {
            return lineRadius * 1.9;
        }
        if (kind === "arc") {
            return lineRadius * 0.9;
        }
        return lineRadius;
    }

    _addMarker(THREE, point, color, targetGroup) {
        const radius = this._getAdaptiveRadius(point, "marker");
        const marker = new THREE.Mesh(
            new THREE.SphereGeometry(radius, 20, 20),
            this._makeOverlayMaterial(THREE, color)
        );
        marker.position.copy(point);
        marker.renderOrder = 900;
        marker.frustumCulled = false;
        targetGroup.add(marker);

        const halo = new THREE.Mesh(
            new THREE.SphereGeometry(radius * 1.8, 16, 16),
            this._makeOverlayMaterial(THREE, color, 0.22)
        );
        halo.position.copy(point);
        halo.renderOrder = 899;
        halo.frustumCulled = false;
        targetGroup.add(halo);

        const outline = new THREE.Mesh(
            new THREE.SphereGeometry(radius * 1.22, 16, 16),
            this._makeOverlayMaterial(THREE, 0x111111, 0.65)
        );
        outline.position.copy(point);
        outline.renderOrder = 898;
        outline.frustumCulled = false;
        targetGroup.add(outline);
    }

    _addLine(THREE, start, end, color, targetGroup, radius = null, preview = false) {
        const direction = end.clone().sub(start);
        const length = direction.length();
        if (length < 1e-6) {
            return;
        }
        const mid = start.clone().add(end).multiplyScalar(0.5);
        const lineRadius = radius || this._getAdaptiveRadius(mid, "line", preview);

        const outline = new THREE.Mesh(
            new THREE.CylinderGeometry(lineRadius * 1.65, lineRadius * 1.65, length, 14),
            this._makeOverlayMaterial(THREE, 0x111111, preview ? 0.22 : 0.52)
        );
        outline.position.copy(mid);
        outline.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
        outline.renderOrder = 889;
        outline.frustumCulled = false;
        targetGroup.add(outline);

        const segment = new THREE.Mesh(
            new THREE.CylinderGeometry(lineRadius, lineRadius, length, 14),
            this._makeOverlayMaterial(THREE, color)
        );
        segment.position.copy(mid);
        segment.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
        segment.renderOrder = 890;
        segment.frustumCulled = false;
        targetGroup.add(segment);
    }

    _drawAngleArc(THREE, vertex, armA, armB, targetGroup, color) {
        const vecA = armA.clone().sub(vertex);
        const vecB = armB.clone().sub(vertex);
        const lenA = vecA.length();
        const lenB = vecB.length();
        if (lenA < 1e-6 || lenB < 1e-6) {
            return null;
        }
        vecA.normalize();
        vecB.normalize();
        const dot = clamp(vecA.dot(vecB), -1, 1);
        const angle = Math.acos(dot);
        if (angle < 1e-4) {
            return { angleDeg: 0 };
        }

        let axis = new THREE.Vector3().crossVectors(vecA, vecB);
        if (axis.lengthSq() < 1e-10) {
            axis = new THREE.Vector3().crossVectors(vecA, this.camera.getWorldDirection(new THREE.Vector3()));
        }
        if (axis.lengthSq() < 1e-10) {
            axis = new THREE.Vector3(0, 0, 1);
        }
        axis.normalize();

        const radius = Math.min(lenA, lenB) * 0.35;
        const segments = 48;
        const points = [];
        for (let i = 0; i <= segments; i++) {
            const t = angle * (i / segments);
            const dir = vecA.clone().applyAxisAngle(axis, t).multiplyScalar(radius);
            points.push(vertex.clone().add(dir));
        }
        const curve = new THREE.CatmullRomCurve3(points);
        const arcRadius = this._getAdaptiveRadius(vertex, "arc");
        const outline = new THREE.Mesh(
            new THREE.TubeGeometry(curve, 64, arcRadius * 1.7, 10, false),
            this._makeOverlayMaterial(THREE, 0x111111, 0.5)
        );
        outline.renderOrder = 890;
        outline.frustumCulled = false;
        targetGroup.add(outline);

        const arc = new THREE.Mesh(
            new THREE.TubeGeometry(curve, 64, arcRadius, 10, false),
            this._makeOverlayMaterial(THREE, color)
        );
        arc.renderOrder = 891;
        arc.frustumCulled = false;
        targetGroup.add(arc);
        return { angleDeg: (angle * 180) / Math.PI };
    }

    _handleDistancePick(point) {
        const THREE = window.THREE;
        if (!THREE) {
            return;
        }
        this._addMarker(THREE, point, 0x2de39a, this._measureGroup);
        if (!this._pendingPoint) {
            this._pendingPoint = point;
            this.state.statusText = "Seleccione un segundo punto.";
            return;
        }
        this._addLine(THREE, this._pendingPoint, point, 0x2de39a, this._measureGroup);

        const distanceCm = this._pendingPoint.distanceTo(point) * this.state.unitToCm;
        this.state.statusText = `Distancia: ${distanceCm.toFixed(2)} cm`;
        this._pendingPoint = null;
        this._clearPreview();
    }

    _updateDistancePreview(point) {
        if (!this._pendingPoint) {
            return;
        }
        const THREE = window.THREE;
        if (!THREE) {
            return;
        }
        this._clearPreview();
        this._addLine(
            THREE,
            this._pendingPoint,
            point,
            0x89ffd0,
            this._previewGroup,
            null,
            true
        );
        const distanceCm = this._pendingPoint.distanceTo(point) * this.state.unitToCm;
        this.state.statusText = `Distancia preliminar: ${distanceCm.toFixed(2)} cm`;
    }

    _handleAnglePick(point) {
        const THREE = window.THREE;
        if (!THREE) {
            return;
        }
        if (!this._angleVertex) {
            this._angleVertex = point;
            this._addMarker(THREE, point, 0xffd64d, this._measureGroup);
            this.state.statusText = "Seleccione el primer brazo del angulo.";
            return;
        }
        if (!this._angleArmPoint) {
            this._angleArmPoint = point;
            this._addMarker(THREE, point, 0xffd64d, this._measureGroup);
            this._addLine(THREE, this._angleVertex, this._angleArmPoint, 0xffd64d, this._measureGroup);
            this.state.statusText = "Seleccione el segundo brazo del angulo.";
            return;
        }

        this._addMarker(THREE, point, 0xffd64d, this._measureGroup);
        this._addLine(THREE, this._angleVertex, point, 0xffd64d, this._measureGroup);
        const arcInfo = this._drawAngleArc(
            THREE,
            this._angleVertex,
            this._angleArmPoint,
            point,
            this._measureGroup,
            0xfff199
        );
        const angleDeg = arcInfo?.angleDeg || 0;
        const reflexDeg = 360 - angleDeg;
        this.state.statusText = `Angulo interno: ${angleDeg.toFixed(2)} deg | externo: ${reflexDeg.toFixed(2)} deg`;
        this._angleVertex = null;
        this._angleArmPoint = null;
        this._clearPreview();
    }

    _updateAnglePreview(point) {
        const THREE = window.THREE;
        if (!THREE || !this._angleVertex) {
            return;
        }
        this._clearPreview();

        if (!this._angleArmPoint) {
            this._addLine(
                THREE,
                this._angleVertex,
                point,
                0xffec99,
                this._previewGroup,
                null,
                true
            );
            return;
        }

        this._addLine(
            THREE,
            this._angleVertex,
            this._angleArmPoint,
            0xffd64d,
            this._previewGroup,
            null,
            true
        );
        this._addLine(
            THREE,
            this._angleVertex,
            point,
            0xffec99,
            this._previewGroup,
            null,
            true
        );
        const arcInfo = this._drawAngleArc(
            THREE,
            this._angleVertex,
            this._angleArmPoint,
            point,
            this._previewGroup,
            0xfff199
        );
        if (arcInfo) {
            this.state.statusText = `Angulo preliminar: ${arcInfo.angleDeg.toFixed(2)} deg`;
        }
    }

    _cleanup() {
        if (this._animationId) {
            cancelAnimationFrame(this._animationId);
        }
        this.renderer?.domElement?.removeEventListener("pointerdown", this._onCanvasPointerDown);
        this.renderer?.domElement?.removeEventListener("pointermove", this._onCanvasPointerMove);
        window.removeEventListener("resize", this._onResize);
        this.controls?.dispose();
        this.clearMeasurements();
        this._disposeCurrentModel();
        if (this.scene) {
            this.scene.traverse((node) => {
                if (node.geometry) {
                    node.geometry.dispose();
                }
                if (node.material) {
                    if (Array.isArray(node.material)) {
                        node.material.forEach((material) => material.dispose());
                    } else {
                        node.material.dispose();
                    }
                }
            });
        }
        if (this.renderer) {
            this.renderer.dispose();
            this.renderer.domElement?.remove();
        }
        if (this._objectUrl) {
            URL.revokeObjectURL(this._objectUrl);
        }
    }
}

export class ThreeJSDialog extends Component {
    static template = "energia_global.ThreeJSDialog";
    static components = { Dialog, ThreeJSViewer };

    setup() {
        this.state = useState({
            view: this._getDefaultView(),
            imageError: null,
        });
        onMounted(() => {
            this.props.onOpen?.();
        });
        onWillUnmount(() => {
            this.props.onClose?.();
        });
    }

    get has3d() {
        if (this.props.modelUrl && this.props.imageUrl) {
            return true;
        }
        if (this._isBase64Image()) {
            return false;
        }
        if (this.props.base64Data) {
            return true;
        }
        if (this.props.modelUrl && !isImageFilename(this.props.filename)) {
            return true;
        }
        return false;
    }

    get hasImage() {
        return Boolean(this.imageUrl);
    }

    get imageUrl() {
        if (this.props.imageUrl) {
            return this.props.imageUrl;
        }
        if (this._isBase64Image()) {
            return this.props.base64Data;
        }
        if (isImageFilename(this.props.filename)) {
            return this.props.modelUrl || null;
        }
        return null;
    }

    setView(view) {
        if ((view === "3d" && this.has3d) || (view === "image" && this.hasImage)) {
            this.state.view = view;
            this.state.imageError = null;
        }
    }

    onImageError() {
        this.state.imageError = "No se pudo cargar la imagen del plano.";
    }

    _isBase64Image() {
        return Boolean(this.props.base64Data && this.props.base64Data.startsWith("data:image/"));
    }

    _getDefaultView() {
        if (this.has3d) {
            return "3d";
        }
        if (this.hasImage) {
            return "image";
        }
        return "3d";
    }
}
