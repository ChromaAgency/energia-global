/** @odoo-module */

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { Dialog } from "@web/core/dialog/dialog";

async function loadThreeDependencies() {
    // To bundle Three.js with Odoo assets, place the UMD/ESM builds under
    // energia_global/static/lib/three/ and add them to web.assets_backend in
    // __manifest__.py BEFORE this file.
    if (window.THREE?.GLTFLoader && window.THREE?.OrbitControls) {
        return window.THREE;
    }
    await loadJS("/energia_global/static/lib/three/three.min.js");
    await loadJS("/energia_global/static/lib/three/OrbitControls.js");
    await loadJS("/energia_global/static/lib/three/GLTFLoader.js");
    if (!window.THREE?.GLTFLoader || !window.THREE?.OrbitControls) {
        throw new Error("Three.js no esta disponible en assets.");
    }
    return window.THREE;
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
            const THREE = await loadThreeDependencies();
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

            const loader = new THREE.GLTFLoader();
            await new Promise((resolve, reject) => {
                loader.load(
                    modelUrl,
                    (gltf) => {
                        this.scene.add(gltf.scene);
                        resolve();
                    },
                    undefined,
                    (error) => reject(error || new Error("No se pudo cargar el modelo 3D."))
                );
            });
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
        const byteString = atob(this.props.base64Data);
        const arrayBuffer = new Uint8Array(byteString.length);
        for (let i = 0; i < byteString.length; i++) {
            arrayBuffer[i] = byteString.charCodeAt(i);
        }
        const blob = new Blob([arrayBuffer], { type: "model/gltf-binary" });
        this._objectUrl = URL.createObjectURL(blob);
        return this._objectUrl;
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
}
