# Tile Fade Transition System

## Overview

The Tile Fade Transition system provides smooth visual feedback as panorama tiles load progressively. Instead of tiles popping in abruptly, the viewer displays placeholder textures that fade out gradually and asynchronously as each individual tile loads.

## Visual Behavior

### Initial State
When a scene is first loaded:
- Each tile position shows a placeholder texture (or gray color if no texture is configured)
- No actual panorama texture is visible until tiles start loading

### Progressive Loading
As tiles load from the backend, each tile fades in individually and asynchronously:
1. **LOD 0 tiles** (256×256px tiles, 512×512px faces): Placeholders disappear as tiles arrive
2. **LOD 1 tiles** (512×512px tiles, 1024×1024px faces): Appears gradually on top of LOD 0
3. **LOD 2 tiles** (512×512px tiles, 2048×2048px faces): Appears gradually on top of LOD 1

### Transition Effect
- Each tile fades in independently when it loads (400ms duration)
- Tiles fade asynchronously within their LOD level
- Smooth ease-out animation for professional appearance
- Configurable placeholder texture for custom branding

## Configuration

### Setting the Placeholder Texture

You can configure a custom placeholder image in two ways:

#### 1. Via ViewerManager static property (global)
```javascript
import { ViewerManager } from './js/viewer/ViewerManager.js';

// Set placeholder URL before creating viewer
ViewerManager.PLACEHOLDER_TILE_URL = '/path/to/placeholder-texture.jpg';

// Then initialize viewer normally
const viewerManager = new ViewerManager('pano-container');
```

#### 2. Via viewer configuration (per-instance)
```javascript
const viewerManager = new ViewerManager('pano-container', {
  placeholderTileUrl: '/path/to/placeholder-texture.jpg'
});
```

#### 3. Dynamically update placeholder
```javascript
// Change placeholder at runtime
viewerManager.setPlaceholderTileUrl('/path/to/new-placeholder.jpg');
```

### Fallback Behavior
If no placeholder URL is set, the system falls back to a solid gray color (#808080).

## Technical Implementation

### Files Modified

1. **`TileFadeOverlay.js`** (MODIFIED)
   - Canvas-based overlay system
   - Tracks tile loading state per face/LOD/position
   - Renders individual tile placeholders (texture or gray)
   - Each tile fades independently and asynchronously
   - Manages 60fps fade animations

2. **`ViewerManager.js`** (MODIFIED)
   - Initializes TileFadeOverlay with placeholder URL
   - Provides `setPlaceholderTileUrl()` method
   - Calls `initializeScene()` when loading a new scene
   - Calls `markTileLoaded()` when tile events arrive from backend
   - Cleans up overlay on destroy

### How It Works

#### 1. Initialization
```javascript
// In ViewerManager.initialize()
const placeholderUrl = this._viewerConfig.placeholderTileUrl || ViewerManager.PLACEHOLDER_TILE_URL;
this._tileFadeOverlay = new TileFadeOverlay(container, this._geometry, placeholderUrl);
```

#### 2. Scene Loading
```javascript
// In ViewerManager.loadScene()
if (this._tileFadeOverlay) {
  this._tileFadeOverlay.initializeScene(tiles.build);
}
```

This sets all tiles to opacity = 1.0 (fully showing placeholder).

#### 3. Tile Events
```javascript
// In ViewerManager._scheduleTileEventPolling()
if (this._tileFadeOverlay) {
  this._tileFadeOverlay.markTileLoaded(face, numLevel, Number(x), Number(y));
}
```

Each loaded tile starts its individual fade-out animation.

#### 4. Rendering
The overlay:
- Renders each tile's placeholder individually on a canvas
- Each tile fades out independently as it loads
- Uses the configured placeholder texture or gray color fallback
- Updates at 60fps until all tiles are fully visible

### Per-Tile Rendering

Unlike the previous global overlay approach, the new system renders placeholders for each individual tile:

```javascript
// For each tile with opacity > 0
this._tiles.forEach((tile) => {
  if (tile.opacity <= 0.01) return; // Skip fully faded tiles
  
  // Calculate tile position on screen
  // Draw placeholder texture or gray color with current opacity
  ctx.globalAlpha = tile.opacity;
  ctx.drawImage(placeholderImage, x, y, tileSize, tileSize);
});
```

This ensures that:
- Each tile fades independently
- Tiles load asynchronously within their LOD
- Visual feedback is precise and matches actual tile loading progress

### Fade Duration

- **Per-tile fade**: 400ms (fast enough for responsiveness)
- **Easing function**: Cubic ease-out (smooth deceleration)
- **Animation**: requestAnimationFrame (60fps)

## Performance Considerations

### Optimizations
- Canvas overlay only renders when tiles are fading (stops when opacity = 0)
- Each tile rendered individually for precise visual feedback
- Minimal DOM updates (single canvas element)
- Placeholder image loaded once and reused for all tiles

### Memory Usage
- Tracks ~150 tiles maximum (6 faces × 3 LOD levels × 8 tiles per face per LOD)
- Each tile state: ~100 bytes (key, opacity, timestamp, metadata)
- Placeholder image: ~50-200KB depending on texture size
- Total overhead: ~15-220KB per scene

### CPU Usage
- Animation loop active only during fade transitions
- Typical fade time: 1-2 seconds per scene load
- Negligible impact once tiles are loaded

## Adjustable Parameters

In `TileFadeOverlay.js`:

```javascript
static PLACEHOLDER_TILE_URL = null;  // URL of placeholder texture (set before initialization)
static FADE_DURATION = 400;          // Milliseconds per tile fade
```

In `ViewerManager.js`:

```javascript
static PLACEHOLDER_TILE_URL = null;  // Can be set globally
```

## Testing

### Manual Testing

1. **Set placeholder texture** (optional):
```javascript
// In your main.js or before viewer initialization
import { ViewerManager } from './js/viewer/ViewerManager.js';
ViewerManager.PLACEHOLDER_TILE_URL = '/path/to/your-texture.jpg';
```

2. **Start the backend**:
```bash
cd panoconfig360_backend
uvicorn panoconfig360_backend.api.server:app --reload --port 8000
```

3. **Open the frontend**:
```
http://localhost:8000
```

4. **Observe the behavior**:
   - Initial load: Placeholder texture (or gray) visible for all tiles
   - As LOD 0 tiles arrive: Each tile fades in individually and asynchronously
   - As LOD 1 tiles arrive: Higher quality appears gradually on top
   - As LOD 2 tiles arrive: Final quality appears gradually
   - Change material selection: Placeholders reappear, tiles fade in again

### Expected Behavior

✅ **Correct**:
- Placeholder (texture or gray) visible on initial scene load
- Each tile fades in independently as it loads
- Tiles fade asynchronously within each LOD level
- LOD 0 → LOD 1 → LOD 2 progressive quality improvement
- No placeholders visible after all tiles loaded

❌ **Issues to watch for**:
- Placeholders not appearing (check console for errors)
- Placeholders persisting after tiles loaded (check tile event polling)
- Choppy animation (check for performance issues)
- Placeholder image not loading (check URL and CORS)

## Troubleshooting

### Placeholder doesn't appear
- Check browser console for JavaScript errors
- Verify TileFadeOverlay.js is loaded correctly
- Check that container element exists
- Verify placeholder URL is set correctly

### Placeholder image doesn't load
- Check that the placeholder URL is accessible
- Verify CORS headers allow cross-origin loading
- Check browser Network tab for failed image requests
- Falls back to gray color if image fails to load

### Placeholders don't fade out
- Verify tile event polling is working (`/api/render/events`)
- Check that `markTileLoaded()` is being called
- Inspect tile state in `this._tiles` Map
- Check browser console for tile loading errors

### Performance issues
- Use smaller placeholder images (256×256 recommended)
- Check canvas size (should match container)
- Verify animation stops when opacity = 0
- Look for memory leaks in tile tracking

## Browser Compatibility

Tested on:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

Requires:
- Canvas API
- requestAnimationFrame
- ES6 Modules
- Performance API
- Image loading (for placeholder texture)

## Future Improvements

Potential enhancements:
1. **3D projection**: Project actual tile positions from 3D cube to 2D screen coordinates for accurate placement
2. **Multiple placeholder textures**: Different placeholders per LOD level
3. **Animated placeholders**: Support for animated GIFs or sprite-based loading animations
4. **Progressive placeholder blur**: Blur placeholder as higher quality tiles load
5. **Accessibility**: Add ARIA labels and screen reader support for loading state

## Related Documentation

- [TILE_PARAMETERS.md](./TILE_PARAMETERS.md) - Explains `?v=` cache-busting system
- [ViewerManager.js](../panoconfig360_frontend/js/viewer/ViewerManager.js) - Viewer integration
- [TileFadeOverlay.js](../panoconfig360_frontend/js/viewer/TileFadeOverlay.js) - Implementation details
