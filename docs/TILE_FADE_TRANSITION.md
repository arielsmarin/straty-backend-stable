# Tile Fade Transition System

## Overview

The Tile Fade Transition system provides smooth visual feedback as panorama tiles load progressively through LOD (Level of Detail) transitions.

## Visual Behavior

### Initial State
When a scene is first loaded, the panorama begins loading tiles progressively.

### Progressive Loading
As tiles load from the backend, each tile fades in individually and asynchronously:
1. **LOD 0 tiles** (256×256px tiles, 512×512px faces): Initial quality appears
2. **LOD 1 tiles** (512×512px tiles, 1024×1024px faces): Appears gradually on top of LOD 0
3. **LOD 2 tiles** (512×512px tiles, 2048×2048px faces): Appears gradually on top of LOD 1

### Transition Effect
- Each tile fades in independently when it loads (400ms duration)
- Tiles fade asynchronously within their LOD level
- Smooth ease-out animation for professional appearance

## Technical Implementation

### Files Modified

1. **`TileFadeOverlay.js`** (MODIFIED)
   - Canvas-based overlay system
   - Tracks tile loading state per face/LOD/position
   - Each tile fades independently and asynchronously
   - Manages 60fps fade animations

2. **`ViewerManager.js`** (MODIFIED)
   - Initializes TileFadeOverlay
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

This sets all tiles to opacity = 1.0 (fully visible).

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
- Manages tile fade states
- Each tile fades out independently as it loads
- Updates at 60fps until all tiles are fully visible

### Fade Duration

- **Per-tile fade**: 400ms (fast enough for responsiveness)
- **Easing function**: Cubic ease-out (smooth deceleration)
- **Animation**: requestAnimationFrame (60fps)

## Performance Considerations

### Optimizations
- Canvas overlay only renders when tiles are fading (stops when opacity = 0)
- Each tile rendered individually for precise visual feedback
- Minimal DOM updates (single canvas element)

### Memory Usage
- Tracks ~150 tiles maximum (6 faces × 3 LOD levels × 8 tiles per face per LOD)
- Each tile state: ~100 bytes (key, opacity, timestamp, metadata)
- Total overhead: ~15KB per scene

### CPU Usage
- Animation loop active only during fade transitions
- Typical fade time: 1-2 seconds per scene load
- Negligible impact once tiles are loaded

## Adjustable Parameters

In `TileFadeOverlay.js`:

```javascript
static FADE_DURATION = 400;          // Milliseconds per tile fade
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
   - Initial load: Tiles begin loading
   - As LOD 0 tiles arrive: Each tile fades in individually and asynchronously
   - As LOD 1 tiles arrive: Higher quality appears gradually on top
   - As LOD 2 tiles arrive: Final quality appears gradually
   - Change material selection: Tiles fade in again

### Expected Behavior

✅ **Correct**:
- Each tile fades in independently as it loads
- Tiles fade asynchronously within each LOD level
- LOD 0 → LOD 1 → LOD 2 progressive quality improvement
- Smooth transitions between LOD levels

❌ **Issues to watch for**:
- Choppy animation (check for performance issues)
- Tiles not fading (check tile event polling)

## Troubleshooting

### Tiles don't fade in
- Verify tile event polling is working (`/api/render/events`)
- Check that `markTileLoaded()` is being called
- Inspect tile state in `this._tiles` Map
- Check browser console for tile loading errors

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

## Related Documentation

- [TILE_PARAMETERS.md](./TILE_PARAMETERS.md) - Explains `?v=` cache-busting system
- [ViewerManager.js](../panoconfig360_frontend/js/viewer/ViewerManager.js) - Viewer integration
- [TileFadeOverlay.js](../panoconfig360_frontend/js/viewer/TileFadeOverlay.js) - Implementation details

