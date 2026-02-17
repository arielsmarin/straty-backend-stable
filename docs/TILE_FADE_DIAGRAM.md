# Tile Fade Transition - Visual Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Panorama Viewer Container                   │  │
│  │                                                          │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │         Marzipano WebGL Renderer                   │ │  │
│  │  │  (Renders 360° panorama with cube map tiles)       │ │  │
│  │  │                                                     │ │  │
│  │  │  LOD 0: 512×512   (6 faces × 1 tile  = 6 tiles)   │ │  │
│  │  │  LOD 1: 1024×1024 (6 faces × 4 tiles = 24 tiles)  │ │  │
│  │  │  LOD 2: 2048×2048 (6 faces × 16 tiles = 96 tiles) │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                         ↑                                │  │
│  │                         │ Textures                       │  │
│  │                         │                                │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │      Canvas Overlay (TileFadeOverlay)              │ │  │
│  │  │  ┌──────────────────────────────────────────────┐  │ │  │
│  │  │  │ Gray Vignette Gradient                       │  │ │  │
│  │  │  │                                              │  │ │  │
│  │  │  │  Opacity = f(LOD weights, tile load states) │  │ │  │
│  │  │  │                                              │  │ │  │
│  │  │  │  Fades: 100% → 70% → 30% → 0%               │  │ │  │
│  │  │  └──────────────────────────────────────────────┘  │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

                              ↓ Tile Events

┌─────────────────────────────────────────────────────────────────┐
│                        Backend Server                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  /api/render/events?cursor=N&limit=300                         │
│  └─> Returns: { events: [{filename, state, build}], cursor }  │
│                                                                 │
│  Progressive Tile Generation:                                  │
│  1. LOD 0/1 tiles (immediate) → event: state="visible"        │
│  2. LOD 2 tiles (background) → event: state="visible"         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
┌──────────────┐
│ Scene Load   │
└──────┬───────┘
       │
       ↓
┌────────────────────────────────────────────┐
│ ViewerManager.loadScene(tiles)             │
├────────────────────────────────────────────┤
│ 1. Create Marzipano scene                  │
│ 2. tileFadeOverlay.initializeScene()       │
│    → Sets all tiles to opacity = 1.0       │
│ 3. Start tile event polling                │
└──────┬─────────────────────────────────────┘
       │
       ↓
┌────────────────────────────────────────────┐
│ Tile Event Polling (150ms intervals)       │
├────────────────────────────────────────────┤
│ while (!completed) {                       │
│   events = fetch('/api/render/events')     │
│   for each event:                          │
│     if (state == "visible"):               │
│       forceTileRefresh(face, level, x, y)  │
│       tileFadeOverlay.markTileLoaded(...)  │
│         → tile.fadeStartTime = now()       │
│ }                                          │
└──────┬─────────────────────────────────────┘
       │
       ↓
┌────────────────────────────────────────────┐
│ Animation Loop (requestAnimationFrame)     │
├────────────────────────────────────────────┤
│ for each tile:                             │
│   if (tile.fadeStartTime != null):        │
│     progress = (now - fadeStartTime) / 400 │
│     eased = cubic-ease-out(progress)       │
│     tile.opacity = 1 - eased               │
│                                            │
│ weightedOpacity = Σ(opacity × weight) / Σw │
│ render(vignette_gradient(weightedOpacity)) │
└──────┬─────────────────────────────────────┘
       │
       ↓
┌────────────────────────────────────────────┐
│ Result: Smooth Gray → Transparent Fade    │
└────────────────────────────────────────────┘
```

## Tile Loading Timeline

```
Time →
  0ms   500ms   1000ms  1500ms  2000ms  2500ms  3000ms  3500ms  4000ms
  │       │       │       │       │       │       │       │       │
  │       │       │       │       │       │       │       │       │
  ├─ Scene Load ────────────────────────────────────────────────────→
  │
  ├─ Gray Overlay: 100% ──────────────────────────────────────────→ 0%
  │                    ↓       ↓       ↓       ↓       ↓
  │                   70%     50%     30%     10%      0%
  │
  ├─ LOD 0 (512×512)
  │  ████████ Loaded (6 tiles)
  │        └─ Triggers fade start
  │
  ├─ LOD 1 (1024×1024)
  │  │       ████████████ Loaded (24 tiles)
  │  │               └─ Accelerates fade
  │
  ├─ LOD 2 (2048×2048)
  │  │       │       ████████████████████████ Loaded (96 tiles)
  │  │       │                           └─ Final fade to 0%
  │
  └──┴───────┴───────┴───────┴───────┴───────┴───────┴───────┴────
```

## Weight Distribution

```
LOD Level │ Tile Count │ Weight per Tile │ Total Weight │ % Impact
──────────┼────────────┼─────────────────┼──────────────┼──────────
LOD 0     │     6      │       1         │      6       │   ~4%
LOD 1     │    24      │       4         │     96       │  ~59%
LOD 2     │    96      │      16         │   1536       │  ~95%
──────────┴────────────┴─────────────────┴──────────────┴──────────
Total:        126 tiles                     1638           100%

Formula: weight = 4^LOD_level
Impact = (tile_count × weight) / total_weight
```

## Opacity Calculation Example

```javascript
// Scenario: LOD 0 fully loaded, LOD 1 half loaded, LOD 2 not loaded

LOD 0: 6 tiles × opacity 0.0 × weight 1  = 0
LOD 1: 24 tiles (12 loaded):
       12 × 0.0 × 4 + 12 × 1.0 × 4       = 48
LOD 2: 96 tiles × opacity 1.0 × weight 16 = 1536

weightedOpacity = (0 + 48 + 1536) / 1638 = 0.97

Result: Gray overlay at 97% opacity
        → Slightly see-through, waiting for more tiles
```

## Gradient Rendering

```
     ┌─────────────────────────────────────────┐
     │                                         │
     │    Center: opacity × 0.35 (lighter)     │
     │         ┌───────────────────┐           │
     │         │                   │           │
     │         │    Panorama       │           │
     │         │    Content        │           │
     │         │                   │           │
     │         └───────────────────┘           │
     │    Edge: opacity × 0.75 (darker)        │
     │                                         │
     └─────────────────────────────────────────┘

Radial gradient from center (lighter) to edges (darker)
Creates professional vignette effect
Helps focus attention on center content
```

## State Transitions

```
┌─────────────┐
│ Scene Load  │
└──────┬──────┘
       │
       ↓
┌─────────────────────────┐
│ All Tiles: Opacity = 1.0│  ← Initial state (fully gray)
│ fadeStartTime = null    │
└──────┬──────────────────┘
       │
       │ Tile event arrives
       ↓
┌─────────────────────────┐
│ Tile marked as loaded   │
│ fadeStartTime = now()   │
└──────┬──────────────────┘
       │
       │ Animation loop
       ↓
┌─────────────────────────┐
│ Opacity decreases:      │
│ 1.0 → 0.9 → 0.8 → ...   │  ← Fading out (400ms)
└──────┬──────────────────┘
       │
       │ After 400ms
       ↓
┌─────────────────────────┐
│ Opacity = 0.0           │  ← Fully transparent
│ Animation stops         │
└─────────────────────────┘
```

## Browser Rendering Pipeline

```
┌────────────────────┐
│ requestAnimationFrame │
└─────────┬──────────┘
          │ 60 FPS (16.67ms per frame)
          ↓
┌─────────────────────────────────────┐
│ TileFadeOverlay._animate()          │
├─────────────────────────────────────┤
│ 1. Update tile opacities (1-2ms)    │
│ 2. Calculate weighted avg (1ms)     │
│ 3. Render gradient (2-3ms)          │
│ 4. Schedule next frame (if needed)  │
└─────────┬───────────────────────────┘
          │ Total: ~5ms per frame
          ↓
┌─────────────────────────────────────┐
│ Canvas 2D Context                   │
├─────────────────────────────────────┤
│ clearRect() → createRadialGradient()│
│ → fillRect()                        │
└─────────┬───────────────────────────┘
          │
          ↓
┌─────────────────────────────────────┐
│ Browser Compositor                  │
│ (GPU-accelerated blending)          │
└─────────────────────────────────────┘
```

---

**Legend:**
- `█` = Loaded tiles
- `→` = Progressive loading
- `↓` = Data/control flow
