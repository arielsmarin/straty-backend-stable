/**
 * ConfigLoader.js
 * Responsável por carregar e gerenciar a configuração do cliente
 */

export class ConfigLoader {
  constructor(clientId) {
    this._clientId = clientId;
    this._config = null;
    this._scenes = null;
    this._currentSceneId = null;
  }

  /**
   * Carrega a configuração do cliente
   */
  async load() {
    try {
      // Tenta primeiro do static/config
      const response = await fetch(`/panoconfig360_cache/clients/${this._clientId}/${this._clientId}_cfg.json`);
      
      if (!response.ok) {
        throw new Error(`Config não encontrado para cliente: ${this._clientId}`);
      }
      
      this._config = await response.json();
      this._scenes = this._config.scenes;
      
      // Define cena inicial
      const sceneList = this.getSceneList();
      if (sceneList.length > 0) {
        this._currentSceneId = sceneList[0].id;
      }

      console.log("[ConfigLoader] Config carregado:", this._clientId);
      return this._config;
    } catch (error) {
      console.error("[ConfigLoader] Erro ao carregar config:", error);
      throw error;
    }
  }

  get config() {
    return this._config;
  }

  get scenes() {
    return this._scenes;
  }

  get clientId() {
    return this._clientId;
  }

  get currentSceneId() {
    return this._currentSceneId;
  }

  /**
   * Define a cena atual
   */
  setCurrentScene(sceneId) {
    if (this._scenes && this._scenes[sceneId]) {
      this._currentSceneId = sceneId;
      return true;
    }
    return false;
  }

  /**
   * Retorna a cena atual
   */
  getCurrentScene() {
    if (!this._currentSceneId || !this._scenes) return null;
    return this._scenes[this._currentSceneId];
  }

  /**
   * Retorna as layers da cena atual
   */
  getCurrentLayers() {
    const scene = this.getCurrentScene();
    return scene?.layers || [];
  }

  /**
   * Retorna uma cena específica
   */
  getScene(sceneId) {
    return this._scenes?.[sceneId] || null;
  }

  /**
   * Retorna lista de cenas ordenada por scene_index
   */
  getSceneList() {
    if (!this._scenes) return [];
    
    return Object.entries(this._scenes)
      .map(([id, scene]) => ({
        id,
        label: scene.label || id,
        sceneIndex: scene.scene_index ?? 0,
        layers: scene.layers || []
      }))
      .sort((a, b) => a.sceneIndex - b.sceneIndex);
  }

  /**
   * Retorna layers de uma cena específica
   */
  getLayers(sceneId) {
    const scene = this.getScene(sceneId);
    return scene?.layers || [];
  }

  /**
   * Retorna items de um layer específico
   */
  getLayerItems(sceneId, layerId) {
    const layers = this.getLayers(sceneId);
    const layer = layers.find(l => l.id === layerId);
    return layer?.items || [];
  }

  /**
   * Retorna configuração do viewer
   */
  getViewerConfig() {
    return this._config?.viewer || {
      tileSize: 512,
      cubeSize: 1024,
      defaultFov: Math.PI / 2
    };
  }
}