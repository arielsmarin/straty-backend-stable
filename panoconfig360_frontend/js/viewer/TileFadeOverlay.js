/**
 * TileFadeOverlay - Manages progressive tile loading transitions
 *
 * Creates a canvas overlay that fades from a placeholder texture to transparent as tiles load.
 * Each tile shows its placeholder and fades in gradually and asynchronously as it loads.
 *
 * This provides a visual feedback system where:
 * 1. Initially, all tiles show the placeholder texture
 * 2. As tiles load progressively in each LOD, they fade in asynchronously
 * 3. LOD 0 (256px tiles, 512px faces): placeholders fade as tiles arrive
 * 4. LOD 1 (512px tiles, 1024px faces): appears gradually on top of LOD 0
 * 5. LOD 2 (512px tiles, 2048px faces): appears gradually on top of LOD 1
 *
 * Technical approach:
 * - Tracks each tile's load state independently
 * - Each tile fades in asynchronously within its LOD
 * - Renders placeholder texture that fades as actual tiles load
 * - Uses requestAnimationFrame for smooth 60fps animations
 */

export class TileFadeOverlay {
  static PLACEHOLDER_TILE_URL = null; // Will be set to a texture URL later
  static FADE_DURATION = 400; // milliseconds for each tile fade (faster for better UX)

  constructor(container, geometry, placeholderUrl = null) {
    this._container = container;
    this._geometry = geometry;
    this._canvas = null;
    this._ctx = null;
    this._tiles = new Map(); // tile key -> { opacity: 0-1, fadeStartTime: timestamp }
    this._animationFrame = null;
    this._isActive = false;
    this._placeholderUrl = placeholderUrl || TileFadeOverlay.PLACEHOLDER_TILE_URL;
    this._placeholderImage = null;
    this._isPlaceholderLoaded = false;

    this._createCanvas();
    this._loadPlaceholderImage();
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

  _loadPlaceholderImage() {
    if (!this._placeholderUrl) {
      // If no placeholder URL, use gray color as fallback
      this._isPlaceholderLoaded = true;
      return;
    }

    this._placeholderImage = new Image();
    this._placeholderImage.crossOrigin = "anonymous";
    this._placeholderImage.onload = () => {
      this._isPlaceholderLoaded = true;
      this._render(); // Re-render with loaded placeholder
    };
    this._placeholderImage.onerror = () => {
      console.warn("Failed to load placeholder image:", this._placeholderUrl);
      this._isPlaceholderLoaded = true; // Fall back to gray
    };
    this._placeholderImage.src = this._placeholderUrl;
  }

  setPlaceholderUrl(url) {
    if (this._placeholderUrl !== url) {
      this._placeholderUrl = url;
      this._isPlaceholderLoaded = false;
      this._loadPlaceholderImage();
    }
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
   * Initialize all tiles for a new scene as gray (opacity = 1)
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
   * Render placeholder for each tile that hasn't fully faded in yet
   * Each tile fades in asynchronously within its LOD
   */
  _render() {
    if (!this._ctx || !this._isActive) return;

    this._updateCanvasSize();

    const ctx = this._ctx;
    const width = this._canvas.width;
    const height = this._canvas.height;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    if (!this._isPlaceholderLoaded) return;

    // Render individual tile placeholders
    // Each tile fades out asynchronously as it loads
    this._tiles.forEach((tile) => {
      if (tile.opacity <= 0.01) return; // Skip fully faded tiles

      // Calculate tile position on screen
      // This is a simplified projection - tiles are rendered as a grid overlay
      const tilePixelSize = width / 6; // Approximate size (6 faces arranged)
      const tileSize = tilePixelSize / tile.tilesPerSide;

      // For cube faces, we render on a 2D projection
      // This is simplified - proper projection would require 3D math
      let faceOffsetX = 0;
      let faceOffsetY = 0;

      // Arrange faces in a cross pattern (approximate)
      switch (tile.face) {
        case "f": faceOffsetX = tilePixelSize; faceOffsetY = tilePixelSize; break; // front
        case "b": faceOffsetX = 3 * tilePixelSize; faceOffsetY = tilePixelSize; break; // back
        case "l": faceOffsetX = 0; faceOffsetY = tilePixelSize; break; // left
        case "r": faceOffsetX = 2 * tilePixelSize; faceOffsetY = tilePixelSize; break; // right
        case "u": faceOffsetX = tilePixelSize; faceOffsetY = 0; break; // up
        case "d": faceOffsetX = tilePixelSize; faceOffsetY = 2 * tilePixelSize; break; // down
      }

      const x = faceOffsetX + tile.x * tileSize;
      const y = faceOffsetY + tile.y * tileSize;

      // Set opacity for this tile
      ctx.globalAlpha = tile.opacity;

      // Draw placeholder texture or gray color
      if (this._placeholderImage && this._placeholderImage.complete) {
        // Draw the placeholder image, tiled to fit the tile area
        ctx.drawImage(this._placeholderImage, x, y, tileSize, tileSize);
      } else {
        // Fallback to gray color
        ctx.fillStyle = "#808080";
        ctx.fillRect(x, y, tileSize, tileSize);
      }
    });

    // Reset global alpha
    ctx.globalAlpha = 1.0;
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

    if (this._placeholderImage) {
      this._placeholderImage.onload = null;
      this._placeholderImage.onerror = null;
      this._placeholderImage = null;
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
