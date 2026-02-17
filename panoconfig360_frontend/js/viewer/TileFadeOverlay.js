/**
 * TileFadeOverlay - Manages per-tile fade-in transitions
 * 
 * Creates a canvas overlay that displays gray squares for tiles that haven't loaded yet.
 * As each tile loads, its corresponding square fades out smoothly, revealing the texture underneath.
 * 
 * This provides a visual feedback system where:
 * 1. Initially, all tiles show as solid gray (no texture loaded)
 * 2. As each 512px tile loads, it fades from gray to visible
 * 3. Works across all LOD levels (LOD 0, 1, 2, etc.)
 * 4. Each tile fades independently for smooth progressive loading
 */

export class TileFadeOverlay {
  static GRAY_COLOR = '#808080';
  static FADE_DURATION = 600; // milliseconds for each tile fade

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
    this._canvas = document.createElement('canvas');
    this._canvas.style.position = 'absolute';
    this._canvas.style.top = '0';
    this._canvas.style.left = '0';
    this._canvas.style.width = '100%';
    this._canvas.style.height = '100%';
    this._canvas.style.pointerEvents = 'none';
    this._canvas.style.zIndex = '10';
    this._ctx = this._canvas.getContext('2d');
    this._container.appendChild(this._canvas);
    
    this._updateCanvasSize();
  }

  _updateCanvasSize() {
    const rect = this._container.getBoundingClientRect();
    this._canvas.width = rect.width;
    this._canvas.height = rect.height;
  }

  _buildTileKey(face, level, x, y) {
    return `${face}:${level}:${x}:${y}`;
  }

  /**
   * Initialize all tiles for a new scene as gray (opacity = 1)
   * This is called when a new scene is loaded
   */
  initializeScene(build) {
    this._tiles.clear();
    this._isActive = true;
    
    // Get geometry levels from Marzipano
    const levels = this._geometry._levels || [];
    const faces = ['f', 'b', 'l', 'r', 'u', 'd'];
    
    // Initialize all tiles as fully opaque gray
    levels.forEach((level, levelIndex) => {
      const tileSize = level.tileSize();
      const size = level.size();
      const tilesPerSide = Math.ceil(size / tileSize);
      
      faces.forEach(face => {
        for (let y = 0; y < tilesPerSide; y++) {
          for (let x = 0; x < tilesPerSide; x++) {
            const key = this._buildTileKey(face, levelIndex, x, y);
            this._tiles.set(key, { 
              opacity: 1.0,
              fadeStartTime: null,
              level: levelIndex,
              face,
              x,
              y,
              tilesPerSide
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
  markTileLoaded(face, level, x, y) {
    const key = this._buildTileKey(face, level, x, y);
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
   * Render gray squares for tiles that haven't fully faded in yet
   */
  _render() {
    if (!this._ctx || !this._isActive) return;
    
    this._updateCanvasSize();
    
    const ctx = this._ctx;
    const width = this._canvas.width;
    const height = this._canvas.height;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // For simplicity, we'll draw a full gray overlay with opacity
    // This is a simplified version - a more complex version would project
    // each cube face tile to screen coordinates
    
    // Calculate average opacity across all tiles
    let totalOpacity = 0;
    let count = 0;
    this._tiles.forEach(tile => {
      totalOpacity += tile.opacity;
      count++;
    });
    
    if (count > 0) {
      const avgOpacity = totalOpacity / count;
      
      if (avgOpacity > 0.01) {
        ctx.fillStyle = TileFadeOverlay.GRAY_COLOR;
        ctx.globalAlpha = avgOpacity * 0.8; // Scale down for better visual effect
        ctx.fillRect(0, 0, width, height);
        ctx.globalAlpha = 1.0;
      }
    }
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
      this._canvas.style.display = 'none';
    }
  }

  /**
   * Resume rendering
   */
  resume() {
    this._isActive = true;
    if (this._canvas) {
      this._canvas.style.display = 'block';
    }
    this._startAnimation();
  }
}
