# LOD Fade Transition System

## Overview

The LOD (Level of Detail) Fade Transition system provides smooth visual feedback as panorama quality improves through progressive loading.

## Visual Behavior

### Initial State
When a scene is first loaded, the panorama begins with desaturated colors (grayscale-like appearance).

### Progressive Loading
As higher quality LOD levels load from the backend:
1. **LOD 0** (256×256px tiles, 512×512px faces): Initial low-quality view appears desaturated
2. **LOD 1** (512×512px tiles, 1024×1024px faces): Color saturation begins to increase
3. **LOD 2** (512×512px tiles, 2048×2048px faces): Full color saturation achieved

### Transition Effect
- Smooth 800ms fade from desaturated to full color
- Ease-out animation for professional appearance
- Triggered when LOD 1+ tiles become available

## Technical Implementation

### Files Modified

1. **`ViewerManager.js`**
   - Manages LOD fade state
   - Applies saturation effects to scene layers
   - Triggers fade-in when higher LOD levels load

### How It Works

#### 1. Initial Desaturation
```javascript
// In ViewerManager._applyDesaturation()
const sat = ViewerManager.LOD_FADE_INITIAL_SATURATION; // 0.15
scene.layer().setEffects(this._buildSaturationEffects(sat));
```

This sets the initial saturation to 15% (mostly grayscale).

#### 2. Progressive Fade-In
```javascript
// In ViewerManager._startLodFadeIn()
// Animates saturation from 0.15 → 1.0 over 800ms
```

When LOD 1+ tiles are detected, saturation gradually increases to 100%.

#### 3. Saturation Matrix
The `_buildSaturationEffects()` method creates a color matrix that controls RGB channel saturation using luminance weights (0.2126 R, 0.7152 G, 0.0722 B).

### Fade Duration

- **Fade duration**: 800ms (smooth but not too slow)
- **Easing function**: Ease-out quadratic (smooth deceleration)
- **Animation**: requestAnimationFrame (60fps)

## Performance Considerations

### Optimizations
- Single animation frame loop per scene
- Cleanup on scene destroy
- Minimal DOM updates (color matrix only)

### CPU Usage
- Animation loop active only during fade transition
- Typical fade time: 800ms per scene load
- Negligible impact once fade completes

## Adjustable Parameters

In `ViewerManager.js`:

```javascript
static LOD_FADE_INITIAL_SATURATION = 0.15;  // Initial grayscale amount (0-1)
// Fade duration: 800ms (in _startLodFadeIn method)
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
   - Initial load: Panorama appears mostly grayscale
   - As LOD 1 tiles arrive: Colors gradually fade in
   - As LOD 2 tiles arrive: Full saturation achieved
   - Change material selection: Desaturation resets, then fades in again

### Expected Behavior

✅ **Correct**:
- Panorama starts desaturated (grayscale-like)
- Smooth transition to full color over ~800ms
- Fade triggered when LOD 1+ tiles are available

❌ **Issues to watch for**:
- Choppy animation (check for performance issues)
- No fade occurring (check that LOD 1+ tiles are loading)

## Troubleshooting

### Colors don't fade in
- Verify LOD 1+ tiles are loading (check Network tab)
- Check that `_startLodFadeIn()` is being called
- Inspect scene layer effects in browser console

### Performance issues
- Check animation frame rate
- Verify fade completes and stops

## Browser Compatibility

Tested on:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

Requires:
- Marzipano layer effects API
- requestAnimationFrame
- ES6 Modules
- Performance API

## Related Documentation

- [TILE_PARAMETERS.md](./TILE_PARAMETERS.md) - Explains `?v=` cache-busting system
- [ViewerManager.js](../panoconfig360_frontend/js/viewer/ViewerManager.js) - Implementation details

