# Tile Placeholder System - Visual Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Configuration                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ViewerManager.PLACEHOLDER_TILE_URL = '/assets/texture.jpg'    │
│                                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ViewerManager Init                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  new TileFadeOverlay(container, geometry, placeholderUrl)       │
│                                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TileFadeOverlay Init                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Create canvas overlay                                       │
│  2. Load placeholder image (async)                              │
│  3. Initialize tile tracking map                                │
│                                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Scene Loading                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  initializeScene(build):                                        │
│    For each LOD (0, 1, 2):                                      │
│      For each face (f, b, l, r, u, d):                         │
│        For each tile (x, y):                                    │
│          tiles.set(key, {                                       │
│            opacity: 1.0,     ← Start fully visible             │
│            fadeStartTime: null,                                 │
│            level, face, x, y                                    │
│          })                                                     │
│                                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Tile Loading Loop                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Backend sends tile events:                                     │
│    {filename: "build_f_0_0_0.jpg", state: "visible"}           │
│                                                                  │
│  ┌────────────────────────────────────────────────┐             │
│  │  markTileLoaded(build, face, level, x, y):   │             │
│  │    tile = tiles.get(key)                      │             │
│  │    tile.fadeStartTime = performance.now()     │  ← Trigger  │
│  │                                                │    fade    │
│  └────────────────────────────────────────────────┘             │
│                                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Animation Loop (60 FPS)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  _animate():                                                    │
│    For each tile:                                               │
│      If fadeStartTime != null:                                  │
│        elapsed = now - fadeStartTime                            │
│        progress = elapsed / 400ms                               │
│        opacity = 1 - easeOutCubic(progress)  ← Smooth fade    │
│                                                                  │
│    _render():                                                   │
│      For each tile with opacity > 0:                            │
│        Calculate position in cross pattern                      │
│        ctx.globalAlpha = opacity                                │
│        ctx.drawImage(placeholder, x, y, w, h)                   │
│                                                                  │
│    If any tile still fading:                                    │
│      requestAnimationFrame(_animate)  ← Continue                │
│    Else:                                                        │
│      Stop animation  ← All done!                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Tile Loading Timeline

```
Time    LOD0 Tiles    LOD1 Tiles    LOD2 Tiles    Placeholder Opacity
─────────────────────────────────────────────────────────────────────
0ms     [........]    [........]    [........]    100% (all tiles)
        
500ms   [LLLL....]    [........]    [........]    75%  (LOD0 loading)
        ████░░░░                                   
        
1000ms  [LLLLLLLL]    [........]    [........]    50%  (LOD0 done)
        ████████                                    
        
1500ms  [LLLLLLLL]    [LLLL....]    [........]    40%  (LOD1 loading)
        ████████      ████░░░░                     
        
2000ms  [LLLLLLLL]    [LLLLLLLL]    [........]    25%  (LOD1 done)
        ████████      ████████                     
        
3000ms  [LLLLLLLL]    [LLLLLLLL]    [LLLL....]    15%  (LOD2 loading)
        ████████      ████████      ████░░░░       
        
4000ms  [LLLLLLLL]    [LLLLLLLL]    [LLLLLLLL]    0%   (All done!)
        ████████      ████████      ████████       

Legend: L = Loaded, . = Loading, █ = Visible, ░ = Placeholder
```

## Cross Pattern Layout

```
Canvas representation of cube faces on 2D overlay:

        ┌────────┐
        │   Up   │
        │   (U)  │
        └────────┘
┌────────┬────────┬────────┬────────┐
│  Left  │ Front  │ Right  │  Back  │
│  (L)   │  (F)   │  (R)   │  (B)   │
└────────┴────────┴────────┴────────┘
        ┌────────┐
        │  Down  │
        │   (D)  │
        └────────┘

Each face subdivided into tiles:
┌──┬──┐
│T1│T2│  ← For example, LOD0: 2x2 tiles per face
├──┼──┤
│T3│T4│
└──┴──┘
```

## Opacity Fade Animation

```
                                    Cubic Ease-Out Curve
Opacity                            
  1.0  ●─────╮                     
       │      ╲                    Start: Placeholder fully visible
  0.8  │       ╲                   
       │        ╲                  
  0.6  │         ╲                 
       │          ╲                Middle: Rapid fade
  0.4  │           ╲               
       │            ╲              
  0.2  │             ╲             
       │              ╲            End: Gentle slowdown
  0.0  │               ●           Tile fully visible
       └────────────────────────── Time (400ms)
       0    100   200   300   400
```

## Data Flow

```
┌──────────────┐
│   Backend    │
│   (FastAPI)  │
└──────┬───────┘
       │ POST /api/render
       │ {client, scene, selection}
       ▼
┌──────────────┐
│ Render       │
│ Service      │
└──────┬───────┘
       │ Generates LOD 0, 1, 2 tiles
       │ Emits tile events
       ▼
┌──────────────┐
│ Event Poll   │ GET /api/render/events?cursor=0
│              │ {events: [{filename, state}]}
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ ViewerMgr    │ forceTileRefresh(face, level, x, y)
│              │ tileFadeOverlay.markTileLoaded(...)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ TileFade     │ tile.fadeStartTime = now()
│ Overlay      │ Start fade animation
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Marzipano    │ Load actual tile image
│ Viewer       │ Display tile on 3D cube
└──────────────┘
```

## Configuration Flow

```
Option 1: Static Property
─────────────────────────
ViewerManager.PLACEHOLDER_TILE_URL = '/texture.jpg'
  ↓
ViewerManager constructor reads static property
  ↓
Passed to TileFadeOverlay constructor
  ↓
Placeholder image loaded


Option 2: Viewer Config
───────────────────────
new ViewerManager(id, {placeholderTileUrl: '/texture.jpg'})
  ↓
Constructor reads config.placeholderTileUrl
  ↓
Passed to TileFadeOverlay constructor
  ↓
Placeholder image loaded


Option 3: Runtime Update
────────────────────────
viewerManager.setPlaceholderTileUrl('/new.jpg')
  ↓
TileFadeOverlay.setPlaceholderUrl('/new.jpg')
  ↓
New placeholder image loaded
  ↓
Re-render with new placeholder
```

## Implementation Highlights

### Key Classes

1. **TileFadeOverlay**
   - Manages canvas overlay
   - Tracks tile states (opacity, fade timing)
   - Renders placeholders with individual opacity
   - Animates fade transitions at 60 FPS

2. **ViewerManager**
   - Initializes TileFadeOverlay
   - Polls tile events from backend
   - Calls markTileLoaded() for each tile
   - Provides configuration API

### Key Data Structures

```javascript
// Tile tracking map
tiles = Map<key, {
  opacity: number,        // 0.0 to 1.0
  fadeStartTime: number,  // performance.now() or null
  level: number,          // LOD level (0, 1, 2)
  face: string,           // 'f', 'b', 'l', 'r', 'u', 'd'
  x: number,              // Tile X coordinate
  y: number,              // Tile Y coordinate
  tilesPerSide: number    // Tiles per face dimension
}>

// Tile key format
key = `${build}:${face}:${level}:${x}:${y}`
// Example: "abc123:f:0:0:0"
```

### Performance Characteristics

```
Initialization:  ~10ms  (canvas creation, image loading)
Per Frame:       ~2ms   (60 FPS during fade)
Total Duration:  1-2s   (scene load with fade)
Memory:          15KB   (tile tracking) + 50-200KB (placeholder image)
```

---

This visual guide provides a comprehensive overview of the tile placeholder system implementation.
