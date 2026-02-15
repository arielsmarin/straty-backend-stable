import { CreateCameraController, CAMERA_POIS } from "./CameraController.js";
import { TilePattern } from "../utils/TilePattern.js";
import { enablePoiCapture } from "../utils/poiCapture.js";

export class ViewerManager {
  constructor(containerId, viewerConfig = {}) {
    this._containerId = containerId;
    this._viewerConfig = viewerConfig;
    this._viewer = null;
    this._view = null;
    this._geometry = null;
    this._cameraController = null;
    this._currentScene = null;
    this._currentBuild = null;
  }

  initialize() {
    const container = document.getElementById(this._containerId);
    if (!container)
      throw new Error(`Container não encontrado: ${this._containerId}`);

    if (typeof Marzipano === "undefined") {
      throw new Error("Marzipano não carregado");
    }

    this._viewer = new Marzipano.Viewer(container, {
      controls: { mouseViewMode: "drag" },
    });

    const savedPoi = localStorage.getItem("pano-camera-poi") || "island";
    const initialPoi = CAMERA_POIS[savedPoi] ||
      CAMERA_POIS.island || { yaw: 0, pitch: 0 };

    this._view = new Marzipano.RectilinearView({
      yaw: initialPoi.yaw,
      pitch: initialPoi.pitch,
      fov: this._viewerConfig.defaultFov || Math.PI / 2,
    });

    // const { tileSize = 512, cubeSize = 1024 } = this._viewerConfig;

    this._geometry = new Marzipano.CubeGeometry([
      { tileSize: 512, size: 512, fallbackOnly: true },
      { tileSize: 512, size: 1024 },
      { tileSize: 512, size: 2048 },
    ]);

    this._cameraController = CreateCameraController(this._view);

    return this._viewer;
  }

  async loadScene(tiles) {
    if (!this._viewer) throw new Error("Viewer não inicializado");

    const token = Symbol("scene");
    this._activeToken = token;

    const pattern = TilePattern.getMarzipanoPattern(tiles);
    const source = Marzipano.ImageUrlSource.fromString(pattern);

    const newScene = this._viewer.createScene({
      source,
      geometry: this._geometry,
      view: this._view,
      pinFirstLevel: true,
    });

    // se outra troca começou → aborta
    if (this._activeToken !== token) return;

    // 🔴 primeira cena: sem fade
    if (!this._currentScene) {
      newScene.switchTo({ transitionDuration: 0 });
      this._currentScene = newScene;
      this._currentBuild = tiles.build;

      // ✅ ATIVA CAPTURE NO MOMENTO CORRETO
      if (this._viewerConfig.devPoiCapture && !this._disablePoiCapture) {
        const container = document.getElementById(this._containerId);
        this._disablePoiCapture = enablePoiCapture(this._view, container);
        console.log("[POI Capture] ativado");
      }

      return;
    }

    // 🟢 crossfade suave
    newScene.switchTo({
      transitionDuration: 300, // ajuste fino de UX
    });

    const oldScene = this._currentScene;
    this._currentScene = newScene;
    this._currentBuild = tiles.build;

    // destruir antiga depois do fade
    setTimeout(() => {
      try {
        oldScene.destroy();
      } catch {}
    }, 350);
  }

  focusOn(poiKey) {
    this._cameraController?.focusOn(poiKey);
  }

  destroy() {
    this._viewer?.destroy();
    this._viewer = null;
  }
}
