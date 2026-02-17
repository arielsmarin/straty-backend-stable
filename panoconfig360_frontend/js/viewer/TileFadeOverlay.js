/**
 * TileFadeOverlay - Manages progressive tile loading transitions
 * 
 * Creates a canvas overlay that fades from gray to transparent as tiles load.
 * The fade is weighted by LOD level, so higher quality tiles have more impact.
 * 
 * This provides a visual feedback system where:
 * 1. Initially, the entire panorama shows as gray (no tiles loaded)
 * 2. As 512px tiles load progressively (LOD 0, 1, 2), the gray fades out
 * 3. Higher LOD tiles (2048px) have more weight in the fade calculation
 * 4. The result is a smooth transition from gray → low quality → high quality
 * 
 * Technical approach:
 * - Tracks each tile's load state independently
 * - Calculates weighted opacity based on LOD level (LOD 2 = 16x weight of LOD 0)
 * - Renders a vignette-style gradient overlay that fades as tiles load
 * - Uses requestAnimationFrame for smooth 60fps animations
 */

export class TileFadeOverlay {
  static GRAY_COLOR = '#808080';
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
   * Uses LOD-aware opacity calculation for smooth progressive reveal
   */
  _render() {
    if (!this._ctx || !this._isActive) return;
    
    this._updateCanvasSize();
    
    const ctx = this._ctx;
    const width = this._canvas.width;
    const height = this._canvas.height;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Calculate opacity per LOD level
    const lodStats = new Map(); // level -> { totalOpacity, count, weight }
    
    this._tiles.forEach(tile => {
      const level = tile.level;
      if (!lodStats.has(level)) {
        // Weight: LOD 0 = 1, LOD 1 = 4, LOD 2 = 16 (exponential, represents pixel count)
        const weight = Math.pow(4, level);
        lodStats.set(level, { totalOpacity: 0, count: 0, weight });
      }
      const stats = lodStats.get(level);
      stats.totalOpacity += tile.opacity;
      stats.count++;
    });
    
    // Calculate weighted average opacity across all LOD levels
    let weightedOpacity = 0;
    let totalWeight = 0;
    
    lodStats.forEach(stats => {
      const avgOpacity = stats.totalOpacity / stats.count;
      weightedOpacity += avgOpacity * stats.weight;
      totalWeight += stats.weight;
    });
    
    if (totalWeight > 0) {
      const finalOpacity = weightedOpacity / totalWeight;
      
      if (finalOpacity > 0.01) {
        // Create a gradient that's darker at edges (vignette effect)
        // This looks better than a flat gray overlay
        const gradient = ctx.createRadialGradient(
          width / 2, height / 2, 0,
          width / 2, height / 2, Math.max(width, height) / 1.4
        );
        
        // Center is lighter (less gray), edges are darker (more gray)
        const centerOpacity = finalOpacity * 0.35;
        const edgeOpacity = finalOpacity * 0.75;
        
        gradient.addColorStop(0, `rgba(128, 128, 128, ${centerOpacity})`);
        gradient.addColorStop(0.7, `rgba(128, 128, 128, ${(centerOpacity + edgeOpacity) / 2})`);
        gradient.addColorStop(1, `rgba(128, 128, 128, ${edgeOpacity})`);
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, width, height);
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
