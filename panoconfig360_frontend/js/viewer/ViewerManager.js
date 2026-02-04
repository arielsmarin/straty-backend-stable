/**
 * ViewerManager.js
 * Gerenciamento do Marzipano viewer
 */

import { CreateCameraController, CAMERA_POIS } from "./CameraController.js";
import { TILE_PATTERN } from "../utils/TilePattern.js";

export class ViewerManager {
  constructor(containerId, viewerConfig = {}) {
    this._containerId = containerId;
    this._viewerConfig = viewerConfig;
    this._viewer = null;
    this._view = null;
    this._scene = null;
    this._cameraController = null;
    this._currentBuild = null;
    this._currentClientId = null;
    this._currentSceneId = null;
    this._savedViewParams = null;
  }

  get viewer() {
    return this._viewer;
  }

  get view() {
    return this._view;
  }

  /**
   * Inicializa o Marzipano viewer
   */
  initialize() {
    const container = document.getElementById(this._containerId);
    if (!container) {
      throw new Error(`Container não encontrado: ${this._containerId}`);
    }

    if (typeof Marzipano === "undefined") {
      throw new Error(
        "Marzipano não está carregado. Verifique o script no HTML.",
      );
    }

    // Habilita zoom com scroll
    this._viewer = new Marzipano.Viewer(container, {
      controls: {
        mouseViewMode: "drag",
        scrollZoom: true,
      },
    });

    console.log("[ViewerManager] Viewer inicializado");
    return this._viewer;
  }

  /**
   * Salva os parâmetros da view atual
   */
  saveViewParams() {
    if (this._view) {
      this._savedViewParams = {
        yaw: this._view.yaw(),
        pitch: this._view.pitch(),
        fov: this._view.fov(),
      };
    }
  }

  /**
   * Restaura os parâmetros da view salvos
   */
  restoreViewParams() {
    if (this._savedViewParams && this._view) {
      this._view.setYaw(this._savedViewParams.yaw);
      this._view.setPitch(this._savedViewParams.pitch);
      this._view.setFov(this._savedViewParams.fov);
    }
  }

  /**
   * Carrega uma cena com os tiles
   */
  async loadScene(clientId, sceneId, buildString, preserveView = false) {
    if (!this._viewer) {
      throw new Error("Viewer não inicializado");
    }

    // Salva view atual se necessário
    if (preserveView && this._view) {
      this.saveViewParams();
    }

    const { tileSize = 512, cubeSize = 1024 } = this._viewerConfig;

    // URL pattern para os tiles
    const tileUrl = TILE_PATTERN.getMarzipanoPattern(
      clientId,
      sceneId,
      buildString,
    );

    console.log(`[ViewerManager] Carregando tiles: ${tileUrl}`);

    // Fonte de tiles
    const source = Marzipano.ImageUrlSource.fromString(tileUrl);

    // Geometria - IMPORTANTE: precisa ter pelo menos um nível não-fallback
    const geometry = new Marzipano.CubeGeometry([
      { tileSize: tileSize, size: cubeSize },
    ]);

    // Limiter com zoom habilitado
    const limiter = Marzipano.RectilinearView.limit.traditional(
      cubeSize,
      (120 * Math.PI) / 180, // maxFov - mais zoom out
      (30 * Math.PI) / 45, // minFov - mais zoom in (adicionado)
    );

    // View - usa parâmetros salvos ou padrão
    let initialViewParams;
    if (preserveView && this._savedViewParams) {
      initialViewParams = this._savedViewParams;
    } else {
      initialViewParams = {
        yaw: 0,
        pitch: 0,
        fov: this._viewerConfig.defaultFov || Math.PI / 2,
      };
    }

    this._view = new Marzipano.RectilinearView(initialViewParams, limiter);

    // Cria cena
    this._scene = this._viewer.createScene({
      source: source,
      geometry: geometry,
      view: this._view,
      pinFirstLevel: true,
    });

    // Exibe cena
    this._scene.switchTo();
    this._currentBuild = buildString;
    this._currentClientId = clientId;
    this._currentSceneId = sceneId;

    // Inicializa controle de câmera
    this._cameraController = CreateCameraController(this._view);

    console.log(`[ViewerManager] Cena carregada: ${buildString}`);
    return this._scene;
  }

  /**
   * Atualiza a cena com novos tiles (mantém câmera)
   */
  async updateScene(clientId, sceneId, buildString) {
    // Se é a mesma build e mesma cena, ignora
    if (
      this._currentBuild === buildString &&
      this._currentClientId === clientId &&
      this._currentSceneId === sceneId
    ) {
      console.log("[ViewerManager] Build já carregada, ignorando");
      return;
    }

    // Determina se deve preservar a view (mesma cena, apenas material diferente)
    const sameScene =
      this._currentClientId === clientId && this._currentSceneId === sceneId;

    // Carrega nova cena preservando view se for mesma cena
    await this.loadScene(clientId, sceneId, buildString, sameScene);

    console.log(`[ViewerManager] Cena atualizada: ${buildString}`);
  }

  /**
   * Foca a câmera em um ponto de interesse
   */
  focusOn(poiKey) {
    if (this._cameraController) {
      this._cameraController.focusOn(poiKey);
    }
  }

  /**
   * Retorna POIs disponíveis
   */
  getAvailablePOIs() {
    return Object.keys(CAMERA_POIS);
  }

  /**
   * Destrói o viewer
   */
  destroy() {
    if (this._viewer) {
      this._viewer.destroy();
      this._viewer = null;
      this._view = null;
      this._scene = null;
      this._cameraController = null;
    }
  }
}
