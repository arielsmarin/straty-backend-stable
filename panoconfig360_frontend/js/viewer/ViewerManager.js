import { CreateCameraController, CAMERA_POIS } from "./CameraController.js";
import { enablePOVCapture } from "../utils/POVCapture.js";
import { TileFadeOverlay } from "./TileFadeOverlay.js";

export class ViewerManager {
  static LOD_FADE_INITIAL_SATURATION = 0.15;
  // 1×1 gray JPEG placeholder used for tiles not yet generated on the backend.
  // Returning this data-URI instead of a real URL avoids 404 network requests
  // while Marzipano still receives a valid image it can decode.
  static PLACEHOLDER_TILE_URL =
    "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%221%22%20height%3D%221%22%3E%3Crect%20fill%3D%22%2523808080%22%20width%3D%221%22%20height%3D%221%22%2F%3E%3C%2Fsvg%3E";

  constructor(containerId, viewerConfig = {}) {
    this._containerId = containerId;
    this._viewerConfig = viewerConfig;
    this._viewer = null;
    this._view = null;
    this._geometry = null;
    this._geometryLevels = null;
    this._cameraController = null;
    this._currentScene = null;
    this._currentBuild = null;

    // listeners
    this._resizeBound = null;
    this._resizeScheduled = false;
    this._uiElement = null;
    // Progressive tile loading: tracks revision number for each tile to enable cache-busting
    // When a tile is updated (e.g., higher LOD available), its revision is incremented
    // and the URL changes from ?v=0 to ?v=1, forcing the browser to fetch the new version
    this._tileRevisionMap = new Map();
    this._tileEventPollTimer = null;
    this._tileEventCursor = 0;
    this._tileEventBuild = null;

    // Progressive LOD: tracks which LOD levels are available and current tiles info
    this._currentTiles = null;
    this._maxAvailableLod = 0;

    // Ready-tile gating: tracks tiles confirmed available by the backend (via events).
    // Tiles NOT in this set receive a placeholder data-URI so Marzipano never fires 404s.
    this._readyTiles = new Set();
    this._allTilesReady = false;

    // LOD fade transition state
    this._lodFadeAnimId = null;
    this._lodFadeSaturation = 1;
    this._lodFadeTriggered = false;

    // Per-tile fade overlay
    this._tileFadeOverlay = null;
  }

  _buildTileKey(face, level, x, y) {
    return `${face}:${level}:${x}:${y}`;
  }

  /**
   * Pre-populates _readyTiles with every tile at the given LOD.
   * Called after the backend confirms that an entire LOD level is on disk
   * (e.g. LOD 0 is fully written before the /api/render response).
   */
  _markLodTilesReady(lod) {
    const level = this._geometryLevels?.[lod];
    if (!level) return;
    const tileSize = level.tileSize || 512;
    const size = level.size || 512;
    const tilesPerSide = Math.ceil(size / tileSize);
    const faces = ["f", "b", "l", "r", "u", "d"];
    for (const face of faces) {
      for (let y = 0; y < tilesPerSide; y++) {
        for (let x = 0; x < tilesPerSide; x++) {
          this._readyTiles.add(this._buildTileKey(face, lod, x, y));
        }
      }
    }
  }

  _buildSaturationEffects(sat) {
    const lr = 0.2126, lg = 0.7152, lb = 0.0722;
    const s = Math.max(0, Math.min(1, sat));
    const a = (1 - s) * lr, b = (1 - s) * lg, c = (1 - s) * lb;
    return {
      colorOffset: [0, 0, 0, 0],
      colorMatrix: [
        a + s, b,     c,     0,
        a,     b + s, c,     0,
        a,     b,     c + s, 0,
        0,     0,     0,     1,
      ],
    };
  }

  _cancelLodFade() {
    if (this._lodFadeAnimId) {
      cancelAnimationFrame(this._lodFadeAnimId);
      this._lodFadeAnimId = null;
    }
  }

  /**
   * Returns the subset of geometry levels available up to maxLod.
   * When only LOD 0 is available, removes fallbackOnly so it renders as the primary level.
   */
  _getGeometryLevelsForLod(maxLod) {
    const levels = this._geometryLevels.slice(0, maxLod + 1);
    if (levels.length === 1 && levels[0].fallbackOnly) {
      const { fallbackOnly, ...rest } = levels[0];
      return [rest];
    }
    return levels;
  }

  /**
   * Upgrades the current scene to include higher LOD levels.
   * Called when backend events signal that new LOD tiles are ready.
   * Creates a new scene with the expanded geometry and crossfades to it.
   */
  _upgradeToLod(maxLod) {
    if (maxLod <= this._maxAvailableLod) return;
    if (!this._currentTiles || !this._currentScene || !this._viewer) return;

    this._maxAvailableLod = maxLod;
    const tiles = this._currentTiles;

    const levels = this._getGeometryLevelsForLod(maxLod);
    this._geometry = new Marzipano.CubeGeometry(levels);

    const source = this._createFastRetrySource(tiles);

    const newScene = this._viewer.createScene({
      source,
      geometry: this._geometry,
      view: this._view,
      pinFirstLevel: true,
    });

    try {
      newScene.layer().setEffects(this._buildSaturationEffects(this._lodFadeSaturation));
    } catch (_) { /* layer may not be ready */ }

    newScene.switchTo({ transitionDuration: 300 });

    const oldScene = this._currentScene;
    this._currentScene = newScene;

    setTimeout(() => {
      try { oldScene.destroy(); } catch {}
    }, 350);
  }

  _applyDesaturation(scene) {
    this._cancelLodFade();
    const sat = ViewerManager.LOD_FADE_INITIAL_SATURATION;
    this._lodFadeSaturation = sat;
    this._lodFadeTriggered = false;
    try {
      scene.layer().setEffects(this._buildSaturationEffects(sat));
    } catch (_) { /* layer may not be ready */ }
  }

  _startLodFadeIn(scene) {
    if (this._lodFadeTriggered) return;
    this._lodFadeTriggered = true;
    this._cancelLodFade();

    const duration = 800;
    const startSat = this._lodFadeSaturation;
    const startTime = performance.now();

    const step = (now) => {
      if (this._currentScene !== scene) return;

      const t = Math.min((now - startTime) / duration, 1);
      const eased = t * (2 - t); // ease-out quadratic
      const sat = startSat + (1 - startSat) * eased;
      this._lodFadeSaturation = sat;

      try {
        scene.layer().setEffects(this._buildSaturationEffects(sat));
      } catch (_) { /* layer may have been destroyed */ }

      if (t < 1) {
        this._lodFadeAnimId = requestAnimationFrame(step);
      } else {
        this._lodFadeAnimId = null;
      }
    };

    this._lodFadeAnimId = requestAnimationFrame(step);
  }

  forceTileRefresh(face, level, x, y) {
    const key = this._buildTileKey(face, level, x, y);
    const current = this._tileRevisionMap.get(key) || 0;
    this._tileRevisionMap.set(key, current + 1);
    this._viewer?.updateSize();
  }

  /**
   * Creates a Marzipano image source with progressive loading support.
   * Each tile URL includes a ?v=N parameter (revision number) for cache-busting.
   * When higher quality tiles become available, the revision is incremented,
   * forcing the browser to fetch the new version despite HTTP cache headers.
   *
   * Ready-tile gating: tiles not yet confirmed by the backend receive a tiny
   * placeholder data-URI so the browser never issues a network request that
   * would result in a 404.  Once an event marks the tile as ready the revision
   * is bumped and Marzipano re-invokes this callback, now returning the real URL.
   */
  _createFastRetrySource(tiles) {
    const baseUrl = `${tiles.baseUrl}/${tiles.tileRoot}`;
    return new Marzipano.ImageUrlSource((tile) => {
      const key = this._buildTileKey(tile.face, tile.z, tile.x, tile.y);

      // Return placeholder for tiles the backend hasn't finished writing yet
      if (!this._allTilesReady && !this._readyTiles.has(key)) {
        return { url: ViewerManager.PLACEHOLDER_TILE_URL };
      }

      const rev = this._tileRevisionMap.get(key) || 0;
      // The ?v= parameter enables cache-busting: ?v=0 (initial), ?v=1 (updated), etc.
      const url = `${baseUrl}/${tiles.build}_${tile.face}_${tile.z}_${tile.x}_${tile.y}.jpg?v=${rev}`;
      return { url };
    }, {
      retryDelay: 150,
      concurrency: 8,
    });
  }

  _stopTileEventPolling() {
    if (this._tileEventPollTimer) {
      clearTimeout(this._tileEventPollTimer);
      this._tileEventPollTimer = null;
    }
  }

  /**
   * Schedules periodic polling of tile events from the backend.
   * The backend generates tiles progressively (LOD 0/1 first, then LOD 2+ in background).
   * This function polls /api/render/events to detect when new high-quality tiles are ready
   * and triggers forceTileRefresh() to update them in the viewer.
   * 
   * Polling frequency: 150ms
   * Stops when: render is complete AND all events have been processed
   */
  _scheduleTileEventPolling(tiles) {
    this._stopTileEventPolling();
    this._tileEventCursor = 0;
    this._tileEventBuild = tiles.build;

    const poll = async () => {
      if (this._tileEventBuild !== tiles.build) return;

      try {
        const url = `/api/render/events?tile_root=${encodeURIComponent(tiles.tileRoot)}&cursor=${this._tileEventCursor}&limit=300`;
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) {
          const body = await res.json();
          const events = body?.data?.events;
          const nextCursor = body?.data?.cursor;
          const completed = body?.data?.completed;
          if (Array.isArray(events)) {
            let maxLodSeen = 0;
            for (const evt of events) {
              if (evt?.build !== tiles.build) continue;
              if (evt?.state !== "visible") continue;

              const parts = String(evt.filename || "").replace(/\.jpg$/i, "").split("_");
              if (parts.length !== 5) continue;

              const [, face, level, x, y] = parts;
              const numLevel = Number(level);
              this._readyTiles.add(this._buildTileKey(face, numLevel, Number(x), Number(y)));
              this.forceTileRefresh(face, numLevel, Number(x), Number(y));
              
              // Mark tile as loaded in the fade overlay
              if (this._tileFadeOverlay) {
                this._tileFadeOverlay.markTileLoaded(tiles.build, face, numLevel, Number(x), Number(y));
              }
              
              if (numLevel > maxLodSeen) maxLodSeen = numLevel;
            }
            // Progressive LOD: upgrade geometry when higher LODs become available
            if (maxLodSeen > this._maxAvailableLod) {
              this._upgradeToLod(maxLodSeen);
            }
            if (maxLodSeen >= 1) {
              if (this._currentScene) {
                this._startLodFadeIn(this._currentScene);
              }
            }
          }
          if (typeof nextCursor === "number") {
            this._tileEventCursor = nextCursor;
          }

          // Stop polling when render is complete and all events have been processed
          if (completed && !body?.data?.hasMore) {
            this._stopTileEventPolling();
            return;
          }
        }
      } catch (_err) {
        // polling best-effort
      }

      this._tileEventPollTimer = setTimeout(poll, 150);
    };

    poll();
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

    // Store all geometry levels for progressive loading
    this._geometryLevels = [
      { tileSize: 256, size: 512, fallbackOnly: false },
      { tileSize: 512, size: 1024 },
      { tileSize: 512, size: 2048 },
    ];
    // Initial geometry with all levels (will be overridden by loadScene with progressive subset)
    this._geometry = new Marzipano.CubeGeometry(this._geometryLevels);

    // Initialize tile fade overlay for smooth per-tile loading transitions
    this._tileFadeOverlay = new TileFadeOverlay(container, this._geometry);

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

  async loadScene(tiles, status) {
    if (!this._viewer) throw new Error("Viewer não inicializado");

    const token = Symbol("scene");
    this._activeToken = token;

    // Progressive LOD: start with only available levels
    this._currentTiles = tiles;
    this._maxAvailableLod = (status === "generated") ? 0 : 2;

    // Ready-tile gating: decide which tiles are safe to request right now
    this._readyTiles.clear();
    if (status === "cached") {
      // All tiles are on disk already – skip per-tile checks
      this._allTilesReady = true;
    } else {
      this._allTilesReady = false;
      // LOD 0 tiles were written synchronously before the API responded
      this._markLodTilesReady(0);
    }

    const levels = this._getGeometryLevelsForLod(this._maxAvailableLod);
    this._geometry = new Marzipano.CubeGeometry(levels);

    const source = this._createFastRetrySource(tiles);

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

      // LOD fade: inicia dessaturado
      this._applyDesaturation(newScene);

      // Initialize tile fade overlay for this scene
      if (this._tileFadeOverlay) {
        this._tileFadeOverlay.initializeScene(tiles.build);
      }

      requestAnimationFrame(() => {
        this._viewer?.updateSize();
      });

      this._scheduleTileEventPolling(tiles);

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

    // LOD fade: inicia dessaturado para a nova cena
    this._applyDesaturation(newScene);

    // Initialize tile fade overlay for new scene
    if (this._tileFadeOverlay) {
      this._tileFadeOverlay.initializeScene(tiles.build);
    }

    requestAnimationFrame(() => {
      this._viewer?.updateSize();
    });

    const oldScene = this._currentScene;
    this._currentScene = newScene;
    this._currentBuild = tiles.build;
    this._scheduleTileEventPolling(tiles);

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

    this._cancelLodFade();
    
    // Clean up tile fade overlay
    if (this._tileFadeOverlay) {
      this._tileFadeOverlay.destroy();
      this._tileFadeOverlay = null;
    }
    
    this._viewer?.destroy();
    this._viewer = null;
    this._stopTileEventPolling();
  }
}
