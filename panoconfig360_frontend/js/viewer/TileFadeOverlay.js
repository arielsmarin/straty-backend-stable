/**
 * TileFadeOverlay - Manages progressive tile loading transitions
 *
 * Provides visual feedback for LOD transitions between tiles.
 * Each tile fades in gradually and asynchronously as it loads.
 *
 * This provides a visual feedback system where:
 * 1. LOD 0 (256px tiles, 512px faces): tiles fade in as they arrive
 * 2. LOD 1 (512px tiles, 1024px faces): appears gradually on top of LOD 0
 * 3. LOD 2 (512px tiles, 2048px faces): appears gradually on top of LOD 1
 *
 * Technical approach:
 * - Tracks each tile's load state independently
 * - Each tile fades in asynchronously within its LOD
 * - Uses requestAnimationFrame for smooth 60fps animations
 */

export class TileFadeOverlay {
  static FADE_DURATION = 400; // milliseconds for each tile fade (faster for better UX)

  constructor(container, geometry) {
    this._container = container;
    this._geometry = geometry;
    this._canvas = null;
    this._ctx = null;
    this._tiles = new Map(); // tile key -> { opacity: 0-1, fadeStartTime: timestamp }
    this._animationFrame = null;
    this._isActive = false;

    this._createCanvas();
  }

  _createCanvas() {
    this._canvas = document.createElement("canvas");
    this._canvas.style.position = "absolute";
    this._canvas.style.top = "0";
    this._canvas.style.left = "0";
    this._canvas.style.width = "100%";
    this._canvas.style.height = "100%";
    this._canvas.style.pointerEvents = "none";
    this._canvas.style.zIndex = "10";
    this._ctx = this._canvas.getContext("2d");
    this._container.appendChild(this._canvas);

    this._updateCanvasSize();
  }

  _updateCanvasSize() {
    const rect = this._container.getBoundingClientRect();
    this._canvas.width = rect.width;
    this._canvas.height = rect.height;
  }

  _buildTileKey(build, face, level, x, y) {
    return `${build}:${face}:${level}:${x}:${y}`;
  }

  /**
   * Initialize all tiles for a new scene (opacity = 1)
   * This is called when a new scene is loaded
   */
  initializeScene(build) {
    if (this._currentBuild !== build) {
      this._tiles.clear();
      this._currentBuild = build;
    }

    // Get geometry levels from Marzipano
    const levels = this._geometry.levelList || [];
    const faces = ["f", "b", "l", "r", "u", "d"];

    // Initialize all tiles as fully opaque gray
    levels.forEach((level, levelIndex) => {
      const tileSize = level.tileWidth ? level.tileWidth() : (level._tileSize || 512);
      const size = level.width ? level.width() : (level._size || 512);
      const tilesPerSide = Math.ceil(size / tileSize);

      faces.forEach((face) => {
        for (let y = 0; y < tilesPerSide; y++) {
          for (let x = 0; x < tilesPerSide; x++) {
            const key = this._buildTileKey(build, face, levelIndex, x, y);
            this._tiles.set(key, {
              opacity: 1.0,
              fadeStartTime: null,
              level: levelIndex,
              face,
              x,
              y,
              tilesPerSide,
            });
          }
        }
      });
    });

    this._startAnimation();
  }

  /**
   * Mark a tile as loaded and start its fade-out animation
   */
  markTileLoaded(build, face, level, x, y) {
    if (build !== this._currentBuild) return;

    const key = this._buildTileKey(build, face, level, x, y);
    const tile = this._tiles.get(key);

    if (tile && tile.opacity > 0 && tile.fadeStartTime === null) {
      tile.fadeStartTime = performance.now();
    }
  }

  /**
   * Animation loop that updates tile opacities and renders the overlay
   */
  _animate() {
    const now = performance.now();
    let hasActiveAnimations = false;

    // Update tile opacities based on fade duration
    this._tiles.forEach((tile) => {
      if (tile.fadeStartTime !== null && tile.opacity > 0) {
        const elapsed = now - tile.fadeStartTime;
        const progress = Math.min(elapsed / TileFadeOverlay.FADE_DURATION, 1);
        // Ease-out cubic for smooth deceleration
        const eased = 1 - Math.pow(1 - progress, 3);
        tile.opacity = Math.max(0, 1 - eased);

        if (tile.opacity > 0) {
          hasActiveAnimations = true;
        }
      } else if (tile.opacity > 0) {
        hasActiveAnimations = true;
      }
    });

    // Render the overlay
    this._render();

    // Continue animation if there are still tiles fading
    if (hasActiveAnimations) {
      this._animationFrame = requestAnimationFrame(() => this._animate());
    } else {
      this._animationFrame = null;
    }
  }

  _startAnimation() {
    if (!this._animationFrame) {
      this._animationFrame = requestAnimationFrame(() => this._animate());
    }
  }

  /**
   * Render overlay for LOD transitions
   * Tiles fade in asynchronously within their LOD
   */
  _render() {
    if (!this._ctx || !this._isActive) return;

    this._updateCanvasSize();

    const ctx = this._ctx;
    const width = this._canvas.width;
    const height = this._canvas.height;

    // Clear canvas - LOD transitions are handled by Marzipano's built-in system
    ctx.clearRect(0, 0, width, height);
  }

  /**
   * Clean up and remove the overlay
   */
  destroy() {
    if (this._animationFrame) {
      cancelAnimationFrame(this._animationFrame);
      this._animationFrame = null;
    }

    if (this._canvas && this._canvas.parentNode) {
      this._canvas.parentNode.removeChild(this._canvas);
    }

    this._tiles.clear();
    this._isActive = false;
  }

  /**
   * Pause rendering (e.g., when scene changes)
   */
  pause() {
    this._isActive = false;
    if (this._canvas) {
      this._canvas.style.display = "none";
    }
  }

  /**
   * Resume rendering
   */
  resume() {
    this._isActive = true;
    if (this._canvas) {
      this._canvas.style.display = "block";
    }
    this._startAnimation();
  }
}
