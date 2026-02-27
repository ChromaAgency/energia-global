/** @odoo-module */

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
const MODEL_EXTENSIONS = new Set(["glb", "gltf", "obj", "fbx"]);

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
        this.state = useState({ loading: true, error: null });
        this._objectUrl = null;
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
            console.log({window})
            console.log({THREE})
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

            // if (!THREE.OrbitControls) {
            //     throw new Error("OrbitControls no esta disponible en assets.");
            // }
            // this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
            // this.controls.enableDamping = true;

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
            // this.controls?.update();
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
                    undefined,
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

    _fitToView(THREE, object) {
        const box = new THREE.Box3().setFromObject(object);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        const distance = maxDim * 1.8;
        this.camera.position.set(center.x + distance, center.y + distance, center.z + distance);
        this.controls.target.copy(center);
        this.controls.update();
    }

    _cleanup() {
        if (this._animationId) {
            cancelAnimationFrame(this._animationId);
        }
        this.controls?.dispose();
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
