# Tile Fade Transition System

## Overview

The Tile Fade Transition system provides smooth visual feedback as panorama tiles load progressively. Instead of tiles popping in abruptly, the viewer displays a gray overlay that fades out gradually as tiles become available.

## Visual Behavior

### Initial State
When a scene is first loaded:
- The entire panorama appears as a solid gray color
- No texture is visible until tiles start loading

### Progressive Loading
As tiles load from the backend:
1. **LOD 0 tiles** (512×512, low quality): Gray starts fading, low-res preview appears
2. **LOD 1 tiles** (1024×1024, medium quality): Gray fades more, better quality visible
3. **LOD 2 tiles** (2048×2048, high quality): Gray fully fades, final quality revealed

### Transition Effect
- Each tile that loads triggers its individual fade-out animation (400ms duration)
- Higher LOD tiles have more weight in the overall fade calculation
- The overlay uses a vignette effect (darker at edges, lighter in center)
- Smooth ease-out animation for professional appearance

## Technical Implementation

### Files Modified

1. **`TileFadeOverlay.js`** (NEW)
   - Canvas-based overlay system
   - Tracks tile loading state per face/LOD/position
   - Renders weighted gray overlay with vignette effect
   - Manages 60fps fade animations

2. **`ViewerManager.js`** (MODIFIED)
   - Initializes TileFadeOverlay on viewer creation
   - Calls `initializeScene()` when loading a new scene
   - Calls `markTileLoaded()` when tile events arrive from backend
   - Cleans up overlay on destroy

### How It Works

#### 1. Initialization
```javascript
// In ViewerManager.initialize()
this._tileFadeOverlay = new TileFadeOverlay(container, this._geometry);
```

#### 2. Scene Loading
```javascript
// In ViewerManager.loadScene()
if (this._tileFadeOverlay) {
  this._tileFadeOverlay.initializeScene(tiles.build);
}
```

This sets all tiles to opacity = 1.0 (fully gray).

#### 3. Tile Events
```javascript
// In ViewerManager._scheduleTileEventPolling()
if (this._tileFadeOverlay) {
  this._tileFadeOverlay.markTileLoaded(face, numLevel, Number(x), Number(y));
}
```

Each loaded tile starts its fade-out animation.

#### 4. Rendering
The overlay:
- Calculates weighted opacity (LOD 2 tiles = 16× weight of LOD 0)
- Draws a radial gradient (darker at edges, lighter in center)
- Updates at 60fps until all tiles are fully visible

### Weight Calculation

```javascript
// LOD weights (exponential based on pixel count)
LOD 0 (512×512):    weight = 4^0 = 1
LOD 1 (1024×1024):  weight = 4^1 = 4
LOD 2 (2048×2048):  weight = 4^2 = 16
```

This ensures that high-quality tiles have the most impact on the fade.

### Fade Duration

- **Per-tile fade**: 400ms (fast enough for responsiveness)
- **Easing function**: Cubic ease-out (smooth deceleration)
- **Animation**: requestAnimationFrame (60fps)

## Performance Considerations

### Optimizations
- Canvas overlay only renders when tiles are fading (stops when opacity = 0)
- Batch opacity calculations in single animation frame
- Minimal DOM updates (single canvas element)
- Lightweight radial gradient rendering

### Memory Usage
- Tracks ~150 tiles maximum (6 faces × 3 LOD levels × 8 tiles per face per LOD)
- Each tile state: ~100 bytes (key, opacity, timestamp, metadata)
- Total overhead: ~15KB per scene

### CPU Usage
- Animation loop active only during fade transitions
- Typical fade time: 1-2 seconds per scene load
- Negligible impact once tiles are loaded

## Configuration

### Adjustable Parameters

In `TileFadeOverlay.js`:

```javascript
static GRAY_COLOR = '#808080';      // Color of the overlay
static FADE_DURATION = 400;         // Milliseconds per tile fade
```

In `_render()` method:
```javascript
const centerOpacity = finalOpacity * 0.35;  // Vignette center opacity
const edgeOpacity = finalOpacity * 0.75;    // Vignette edge opacity
```

## Testing

### Manual Testing

1. **Start the backend**:
```bash
cd panoconfig360_backend
uvicorn panoconfig360_backend.api.server:app --reload --port 8000
```

2. **Open the frontend**:
```
http://localhost:8000
```

3. **Observe the behavior**:
   - Initial load: Gray overlay visible
   - After 1-2 seconds: Overlay fades as LOD 0/1 tiles load
   - After 3-5 seconds: Overlay disappears as LOD 2 tiles complete
   - Change material selection: Gray overlay reappears, fades again

### Expected Behavior

✅ **Correct**:
- Gray overlay on initial scene load
- Smooth fade-out as tiles load
- Higher quality tiles fade later (progressive reveal)
- No gray overlay after all tiles loaded

❌ **Issues to watch for**:
- Gray not appearing (check console for errors)
- Gray persisting after tiles loaded (check tile event polling)
- Choppy animation (check for performance issues)

## Troubleshooting

### Gray overlay doesn't appear
- Check browser console for JavaScript errors
- Verify TileFadeOverlay.js is loaded correctly
- Check that container element exists

### Gray doesn't fade out
- Verify tile event polling is working (`/api/render/events`)
- Check that `markTileLoaded()` is being called
- Inspect tile state in `this._tiles` Map

### Performance issues
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

## Future Improvements

Potential enhancements:
1. **Per-face fading**: Track opacity per cube face for more accurate transitions
2. **3D projection**: Project actual tile positions to 2D screen coordinates
3. **Customizable colors**: Allow theme-based overlay colors
4. **Loading indicator**: Add subtle tile grid overlay to show loading progress
5. **Accessibility**: Add ARIA labels and screen reader support

## Related Documentation

- [TILE_PARAMETERS.md](./TILE_PARAMETERS.md) - Explains `?v=` cache-busting system
- [ViewerManager.js](../panoconfig360_frontend/js/viewer/ViewerManager.js) - Viewer integration
- [TileFadeOverlay.js](../panoconfig360_frontend/js/viewer/TileFadeOverlay.js) - Implementation details
