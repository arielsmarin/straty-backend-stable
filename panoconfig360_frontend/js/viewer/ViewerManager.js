import { CreateCameraController, CAMERA_POIS } from "./CameraController.js";
import { TilePattern } from "../utils/TilePattern.js";
import { enablePOVCapture } from "../utils/POVCapture.js";

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

    // listeners
    this._resizeBound = null;
    this._resizeScheduled = false;
    this._uiElement = null;
  }


  _setTileLoading(isLoading) {
    if (!this._container) return;
    this._container.classList.toggle("tile-loading", Boolean(isLoading));
  }

  _scheduleHideTileLoading(maxMs = 1800) {
    if (this._tileLoadingTimeout) {
      clearTimeout(this._tileLoadingTimeout);
    }

    this._tileLoadingTimeout = setTimeout(() => {
      this._setTileLoading(false);
      this._tileLoadingTimeout = null;
    }, maxMs);
  }

  initialize() {
    const container = document.getElementById(this._containerId);
    if (!container)
      throw new Error(`Container não encontrado: ${this._containerId}`);

    this._container = container;
    this._uiElement = document.querySelector(".ui-container") || null;

    if (typeof Marzipano === "undefined") {
      throw new Error("Marzipano não carregado");
    }

    this._viewer = new Marzipano.Viewer(container, {
      controls: { mouseViewMode: "drag" },
    });

    this._renderCompleteHandler = () => this._setTileLoading(false);
    this._viewer.addEventListener("renderComplete", this._renderCompleteHandler);

    // garante cálculo correto após layout flex
    requestAnimationFrame(() => {
      this._viewer?.updateSize();
    });

    const savedPoi = localStorage.getItem("pano-camera-poi") || "island";
    const initialPoi = CAMERA_POIS[savedPoi] ||
      CAMERA_POIS.island || { yaw: 0, pitch: 0 };

    const savedState = JSON.parse(
      localStorage.getItem("pano-camera-state") || "null",
    );

    this._view = new Marzipano.RectilinearView({
      yaw: savedState?.yaw ?? initialPoi.yaw,
      pitch: savedState?.pitch ?? initialPoi.pitch,
      fov: savedState?.fov ?? this._viewerConfig.defaultFov ?? Math.PI / 2,
    });

    this._geometry = new Marzipano.CubeGeometry([
      { tileSize: 512, size: 512, fallbackOnly: true },
      { tileSize: 512, size: 1024 },
      { tileSize: 512, size: 2048 },
    ]);

    this._cameraController = CreateCameraController(this._view);

    // resize seguro — apenas recalcula tamanho do viewer
    if (!this._resizeBound) {
      this._resizeBound = () => {
        if (this._resizeScheduled) return;
        this._resizeScheduled = true;

        requestAnimationFrame(() => {
          this._resizeScheduled = false;
          this._viewer?.updateSize();
        });
      };

      window.addEventListener("resize", this._resizeBound);
    }

    return this._viewer;
  }

  async loadScene(tiles) {
    if (!this._viewer) throw new Error("Viewer não inicializado");

    const token = Symbol("scene");
    this._activeToken = token;
    this._setTileLoading(true);
    this._scheduleHideTileLoading();

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

    // primeira cena: sem fade
    if (!this._currentScene) {
      newScene.switchTo({ transitionDuration: 0 });
      this._currentScene = newScene;
      this._currentBuild = tiles.build;

      requestAnimationFrame(() => {
        this._viewer?.updateSize();
      });

      if (this._viewerConfig.devPOVCapture && !this._disablePOVCapture) {
        requestAnimationFrame(() => {
          this._disablePOVCapture = enablePOVCapture(
            this._view,
            this._container,
          );
          console.log("[POI Capture] ativado");
        });
      }

      return;
    }

    // crossfade suave
    newScene.switchTo({ transitionDuration: 300 });

    requestAnimationFrame(() => {
      this._viewer?.updateSize();
    });

    const oldScene = this._currentScene;
    this._currentScene = newScene;
    this._currentBuild = tiles.build;

    setTimeout(() => {
      try {
        oldScene.destroy();
      } catch {}
    }, 350);
  }

  focusOn(poiKey) {
    this._cameraController?.focusOn(poiKey);
  }

  updateSize() {
    this._viewer?.updateSize();
  }

  destroy() {
    if (this._resizeBound) {
      window.removeEventListener("resize", this._resizeBound);
      this._resizeBound = null;
    }

    if (this._viewer && this._renderCompleteHandler) {
      this._viewer.removeEventListener("renderComplete", this._renderCompleteHandler);
      this._renderCompleteHandler = null;
    }

    if (this._tileLoadingTimeout) {
      clearTimeout(this._tileLoadingTimeout);
      this._tileLoadingTimeout = null;
    }

    this._viewer?.destroy();
    this._viewer = null;
  }
}
