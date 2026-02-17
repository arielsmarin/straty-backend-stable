# Placeholder Texture Configuration - Examples

This document shows how to configure custom placeholder textures for the tile loading system.

## Overview

The tile placeholder system allows you to show a custom texture (or gray color) for each tile while it's loading. Each tile fades in gradually and asynchronously as it loads within its LOD level.

## Configuration Methods

### Method 1: Global Static Property (Recommended)

Set the placeholder URL before creating the viewer:

```javascript
// In main.js or before viewer initialization
import { ViewerManager } from "./viewer/ViewerManager.js";

// Set placeholder texture URL (will be used for all tiles)
ViewerManager.PLACEHOLDER_TILE_URL = '/assets/placeholder-texture.jpg';

// Then initialize viewer normally
const viewerManager = new ViewerManager(VIEWER_CONTAINER_ID, viewerConfig);
await viewerManager.initialize();
```

### Method 2: Via Viewer Configuration

Pass the placeholder URL in the viewer configuration:

```javascript
// In main.js
const viewerConfig = {
  ...configLoader.getViewerConfig(),
  placeholderTileUrl: '/assets/placeholder-texture.jpg'
};

const viewerManager = new ViewerManager(VIEWER_CONTAINER_ID, viewerConfig);
await viewerManager.initialize();
```

### Method 3: Dynamic Update

Change the placeholder at runtime:

```javascript
// After viewer is initialized
viewerManager.setPlaceholderTileUrl('/assets/new-placeholder.jpg');
```

## Placeholder Image Requirements

### Recommended Specifications
- **Format**: JPG or PNG
- **Size**: 256×256 pixels (or larger, will be scaled)
- **File size**: < 50KB for best performance
- **CORS**: 
  - Same-origin: No special headers required
  - Cross-origin: Server must send `Access-Control-Allow-Origin` header
  - The image loads with `crossOrigin="anonymous"` for canvas compatibility

### CORS Notes
If loading placeholder from a different domain:
```
Server must respond with:
Access-Control-Allow-Origin: * 
  (or the specific origin of your app)
```
For same-origin images (e.g., `/assets/placeholder.jpg`), no CORS configuration needed.

### Example Placeholder Textures

#### Simple Gray Texture
```javascript
ViewerManager.PLACEHOLDER_TILE_URL = null; // Uses default gray color
```

#### Custom Pattern (Same Origin)
```javascript
// Use a subtle pattern or brand texture from your assets
ViewerManager.PLACEHOLDER_TILE_URL = '/assets/textures/loading-pattern.jpg';
```

#### Custom Pattern (Cross Origin)
```javascript
// External CDN - ensure CORS headers are set
ViewerManager.PLACEHOLDER_TILE_URL = 'https://cdn.example.com/placeholder.jpg';
```

#### Loading Animation (Static Frame)
```javascript
// Use a static frame from a loading animation
ViewerManager.PLACEHOLDER_TILE_URL = '/assets/textures/loading-frame.png';
```

## Complete Integration Example

Here's a complete example showing how to integrate placeholder configuration in `main.js`:

```javascript
import { ConfigLoader } from "./config/ConfigLoader.js";
import { Configurator } from "./core/Configurator.js";
import { ViewerManager } from "./viewer/ViewerManager.js";
import { RenderService } from "./services/RenderService.js";
import { UIController } from "./ui/UIController.js";

// ======================================================
// CONFIGURAÇÃO
// ======================================================
const CLIENT_ID = "monte-negro";
const VIEWER_CONTAINER_ID = "pano-config-api";

// Configure placeholder texture (OPTIONAL)
// Comment out or set to null to use default gray color
ViewerManager.PLACEHOLDER_TILE_URL = '/assets/placeholder-texture.jpg';

// ======================================================
// INSTÂNCIAS GLOBAIS
// ======================================================
let configLoader = null;
let configurator = null;
let viewerManager = null;
// ... rest of initialization code ...

async function init() {
  try {
    console.log("[Main] Iniciando aplicação...");

    // 1. Carrega configuração
    configLoader = new ConfigLoader(CLIENT_ID);
    await configLoader.load();

    // 2. Cria configurator
    configurator = new Configurator(configLoader);
    configurator.initializeSelection();

    // 3. Inicializa o viewer (with placeholder configured above)
    const viewerConfig = configLoader.getViewerConfig();
    viewerManager = new ViewerManager(VIEWER_CONTAINER_ID, viewerConfig);
    await viewerManager.initialize();

    // ... rest of initialization ...
  } catch (error) {
    console.error("[Main] Erro na inicialização:", error);
  }
}

document.addEventListener("DOMContentLoaded", init);
```

## Visual Behavior

### Without Placeholder Texture (Default)
```
Initial: [Gray] [Gray] [Gray] [Gray]
LOD 0:   [Tile] [Gray] [Gray] [Tile]
LOD 1:   [Tile] [Tile] [Gray] [Tile]
LOD 2:   [Tile] [Tile] [Tile] [Tile]
```

### With Placeholder Texture
```
Initial: [Texture] [Texture] [Texture] [Texture]
LOD 0:   [Tile]    [Texture] [Texture] [Tile]
LOD 1:   [Tile]    [Tile]    [Texture] [Tile]
LOD 2:   [Tile]    [Tile]    [Tile]    [Tile]
```

Each transition is smooth (400ms fade) and asynchronous.

## Troubleshooting

### Placeholder not showing
```javascript
// Check if URL is set correctly
console.log('Placeholder URL:', ViewerManager.PLACEHOLDER_TILE_URL);

// Check browser console for image loading errors
// Look for CORS or 404 errors
```

### Placeholder image doesn't load
```javascript
// Test if image is accessible
const img = new Image();
img.onload = () => console.log('✓ Placeholder loaded successfully');
img.onerror = () => console.error('✗ Failed to load placeholder');
img.src = ViewerManager.PLACEHOLDER_TILE_URL;
```

### Falls back to gray
If the placeholder image fails to load, the system automatically falls back to a gray color (#808080).

## Best Practices

1. **Use compressed images**: Keep file size under 50KB
2. **Test CORS**: Ensure image is accessible from your domain
3. **Provide fallback**: The system handles failures gracefully
4. **Consider branding**: Use your brand colors or patterns
5. **Test visibility**: Ensure placeholder is visible on dark/light backgrounds

## Related Documentation

- [TILE_FADE_TRANSITION.md](./TILE_FADE_TRANSITION.md) - Complete technical documentation
- [TILE_PARAMETERS.md](./TILE_PARAMETERS.md) - Tile URL parameters and caching
