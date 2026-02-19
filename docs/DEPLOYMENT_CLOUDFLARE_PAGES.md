# Cloudflare Pages Deployment Guide

## Overview

Deploy the Panoconfig360 frontend (static Marzipano viewer) to Cloudflare Pages for global CDN distribution with zero configuration.

## Prerequisites

- GitHub repository with your code
- Cloudflare account (free tier available)
- Custom domain (optional, but recommended)

## Step 1: Prepare Frontend for Deployment

### 1.1 Create Build Configuration

Since the frontend is vanilla JavaScript (no build step), we just need a simple configuration.

Create `panoconfig360_frontend/_headers`:

```
# Cache static assets aggressively
/css/*
  Cache-Control: public, max-age=31536000, immutable

/js/*
  Cache-Control: public, max-age=31536000, immutable

/js/libs/*
  Cache-Control: public, max-age=31536000, immutable

# Cache HTML with shorter TTL
/*.html
  Cache-Control: public, max-age=3600

# API proxy headers (if using Functions)
/api/*
  Access-Control-Allow-Origin: *
  Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
  Access-Control-Allow-Headers: *
```

### 1.2 Create Redirects (Optional)

Create `panoconfig360_frontend/_redirects`:

```
# SPA fallback (if needed for routing)
/*    /index.html   200

# Legacy URLs (if migrating)
/old-path    /new-path    301
```

### 1.3 Update API Base URL

In your frontend JavaScript, use environment-aware API URLs.

Create `panoconfig360_frontend/js/config/environment.js`:

```javascript
/**
 * Environment configuration
 * Detects production vs development and sets appropriate API URLs
 */

const ENV = {
  // Auto-detect environment
  isProd: window.location.hostname !== 'localhost',
  
  // API endpoints
  apiBaseUrl: window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://api.example.com',
  
  // CDN for tiles
  cdnBaseUrl: window.location.hostname === 'localhost'
    ? 'http://localhost:8000/panoconfig360_cache'
    : 'https://cdn.example.com',
  
  // Feature flags
  enableDebugLogs: window.location.hostname === 'localhost',
  enablePerformanceTracking: true,
};

export default ENV;
```

Update API calls to use `ENV.apiBaseUrl`:

```javascript
// OLD:
// const response = await fetch('/api/render', { ... });

// NEW:
import ENV from './config/environment.js';

const response = await fetch(`${ENV.apiBaseUrl}/api/render`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(requestData),
});
```

Update tile URLs to use `ENV.cdnBaseUrl`:

```javascript
// OLD:
// const tileUrl = `/panoconfig360_cache/${tileRoot}/${filename}`;

// NEW:
import ENV from './config/environment.js';

const tileUrl = `${ENV.cdnBaseUrl}/${tileRoot}/${filename}`;
```

## Step 2: Connect GitHub Repository

### 2.1 Access Cloudflare Pages

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Select your account
3. Navigate to **Workers & Pages** → **Pages**
4. Click **"Create application"** → **"Connect to Git"**

### 2.2 Authorize GitHub

1. Click **"Connect GitHub"**
2. Authorize Cloudflare Pages
3. Select repository: `your-username/panoconfig360_totem`

## Step 3: Configure Build Settings

### 3.1 Project Settings

**Project name**: `panoconfig360-app`

**Production branch**: `main`

**Build settings**:
- **Framework preset**: None (static site)
- **Build command**: *(leave empty)*
- **Build output directory**: `panoconfig360_frontend`
- **Root directory**: *(leave empty)*

### 3.2 Environment Variables

Add these in **Settings** → **Environment variables**:

```bash
# Production
NODE_ENV=production

# Optional: If you need any build-time variables
API_BASE_URL=https://api.example.com
CDN_BASE_URL=https://cdn.example.com
```

Note: For client-side JS, you can't use build-time env vars directly. Use the `environment.js` approach from Step 1.3.

### 3.3 Build Configuration File (Alternative)

If you prefer file-based configuration, create `pages.json`:

```json
{
  "build": {
    "command": "",
    "output": "panoconfig360_frontend"
  },
  "routes": [
    {
      "pattern": "/api/*",
      "action": "rewrite",
      "destination": "https://api.example.com/api/:splat"
    }
  ]
}
```

## Step 4: Configure Custom Domain

### 4.1 Add Custom Domain

1. In Pages project, go to **Custom domains**
2. Click **"Set up a custom domain"**
3. Enter your domain: `app.example.com`

### 4.2 Update DNS

Cloudflare will automatically:
- Create CNAME record: `app.example.com` → `panoconfig360-app.pages.dev`
- Provision SSL certificate
- Enable Cloudflare proxy

**Manual DNS** (if not using Cloudflare DNS):
- Type: CNAME
- Name: app
- Target: `panoconfig360-app.pages.dev`

Wait 5-10 minutes for SSL provisioning.

### 4.3 Configure Apex Domain (Optional)

For `example.com` (without subdomain):

**Using Cloudflare DNS**:
- Automatically creates CNAME flattening
- Works seamlessly

**Using Other DNS**:
- Use ALIAS record (if supported)
- Or use A/AAAA records pointing to Cloudflare IPs

## Step 5: Deploy

### 5.1 Trigger First Deploy

Click **"Save and Deploy"**

Monitor deployment logs in real-time. Typical deploy time: 30-60 seconds.

### 5.2 Verify Deployment

**Production URL**: `https://panoconfig360-app.pages.dev`
**Custom URL**: `https://app.example.com`

Test in browser:
- Homepage loads
- Static assets (CSS, JS) load correctly
- API calls work (check Network tab)
- CORS is configured properly

### 5.3 Preview Deployments

Every git branch/PR gets a unique preview URL:
```
https://<branch>.<project>.pages.dev
```

Perfect for testing before merging to production.

## Step 6: Configure Automatic Deployments

### 6.1 Production Deployments

Cloudflare Pages automatically deploys when you push to `main`:

```bash
git add .
git commit -m "Update frontend"
git push origin main
```

Watch deployment at: Dashboard → Pages → Deployments

### 6.2 Preview Deployments

Every PR gets automatic preview deployment:

```bash
git checkout -b feature/new-ui
# Make changes
git push origin feature/new-ui
# Create PR in GitHub
```

Preview URL: `https://feature-new-ui.panoconfig360-app.pages.dev`

### 6.3 Deploy Hooks

For manual or CI/CD triggered deployments:

1. Go to **Settings** → **Builds & deployments**
2. Click **"Add deploy hook"**
3. Name: `Production deploy`
4. Branch: `main`
5. Copy webhook URL

Trigger deployment:
```bash
curl -X POST https://api.cloudflare.com/client/v4/pages/webhooks/deploy/xxxxx
```

## Step 7: Configure Page Rules (Optional)

### 7.1 Security Headers

In Cloudflare Dashboard (not Pages):

1. Select your domain
2. Go to **Rules** → **Transform Rules** → **HTTP Response Header**
3. Create rule

**Rule: Security Headers**
```
When incoming requests match: app.example.com/*

Then:
  Set static header:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: SAMEORIGIN
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: camera=(), microphone=(), geolocation=()
```

### 7.2 Cache Rules

**Rule: Static Assets**
```
When incoming requests match:
  - app.example.com/css/*
  - app.example.com/js/*

Then:
  - Cache Level: Standard
  - Edge TTL: 30 days
  - Browser TTL: 1 year
```

**Rule: HTML**
```
When incoming requests match:
  - app.example.com/*.html
  - app.example.com/ (root)

Then:
  - Cache Level: Standard
  - Edge TTL: 1 hour
  - Browser TTL: 5 minutes
```

## Step 8: Configure Functions (Optional API Proxy)

### 8.1 Create Functions Directory

If you want to proxy API calls through Cloudflare:

Create `panoconfig360_frontend/functions/api/[[path]].js`:

```javascript
/**
 * Cloudflare Pages Function
 * Proxies API calls to backend with CORS
 */

export async function onRequest(context) {
  const {
    request,
    env,
  } = context;

  // Get the path after /api/
  const url = new URL(request.url);
  const apiPath = url.pathname.replace(/^\/api/, '');
  
  // Backend API URL
  const backendUrl = `https://api.example.com${apiPath}${url.search}`;

  // Forward request to backend
  const backendRequest = new Request(backendUrl, {
    method: request.method,
    headers: request.headers,
    body: request.method !== 'GET' && request.method !== 'HEAD' 
      ? await request.arrayBuffer() 
      : undefined,
  });

  // Fetch from backend
  const response = await fetch(backendRequest);

  // Clone response and add CORS headers
  const modifiedResponse = new Response(response.body, response);
  modifiedResponse.headers.set('Access-Control-Allow-Origin', '*');
  modifiedResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  modifiedResponse.headers.set('Access-Control-Allow-Headers', '*');

  return modifiedResponse;
}
```

Now frontend can call `/api/render` instead of `https://api.example.com/api/render`.

### 8.2 Handle OPTIONS Requests

Create `panoconfig360_frontend/functions/api/_middleware.js`:

```javascript
/**
 * Handle CORS preflight requests
 */

export async function onRequest(context) {
  const { request } = context;

  // Handle OPTIONS (preflight)
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Max-Age': '86400',
      },
    });
  }

  // Continue to actual handler
  return context.next();
}
```

## Step 9: Performance Optimization

### 9.1 Enable Cloudflare Features

In Cloudflare Dashboard:

**Speed** tab:
- ✅ Auto Minify: HTML, CSS, JS
- ✅ Brotli compression
- ✅ Rocket Loader (test first, may break some JS)
- ✅ HTTP/2, HTTP/3
- ✅ Early Hints

**Caching** tab:
- Cache Level: Standard
- Browser Cache TTL: Respect Existing Headers
- Always Online: ✅ (serves stale content if origin down)

### 9.2 Optimize Images

If you have images in frontend:

**Option 1: Cloudflare Polish**
- Free tier: Lossless compression
- Pro tier: Lossy compression + WebP

**Option 2: Cloudflare Images** (separate product)
- Automatic format conversion
- Responsive images
- Fast resizing

### 9.3 Prefetch/Preload Critical Resources

Update `index.html`:

```html
<head>
  <!-- Preconnect to API and CDN -->
  <link rel="preconnect" href="https://api.example.com">
  <link rel="preconnect" href="https://cdn.example.com">
  
  <!-- Preload critical resources -->
  <link rel="preload" href="/js/libs/marzipano.js" as="script">
  <link rel="preload" href="/css/styles.css" as="style">
  
  <!-- DNS prefetch for external resources -->
  <link rel="dns-prefetch" href="https://api.example.com">
  <link rel="dns-prefetch" href="https://cdn.example.com">
</head>
```

## Step 10: Analytics and Monitoring

### 10.1 Enable Web Analytics

In Pages project:

1. Go to **Analytics** → **Web Analytics**
2. Click **"Enable Web Analytics"**
3. Copy the script snippet
4. Add to `index.html` before `</body>`:

```html
<!-- Cloudflare Web Analytics -->
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' 
        data-cf-beacon='{"token": "your-token-here"}'></script>
```

Tracks:
- Page views
- Performance metrics (Core Web Vitals)
- Geographic distribution
- Referrers

### 10.2 Real User Monitoring (RUM)

For detailed performance tracking, add custom tracking:

```javascript
// Performance tracking
window.addEventListener('load', () => {
  const perfData = performance.getEntriesByType('navigation')[0];
  
  // Send to analytics
  if (window.ENV?.enablePerformanceTracking) {
    console.log('Performance:', {
      dns: perfData.domainLookupEnd - perfData.domainLookupStart,
      tcp: perfData.connectEnd - perfData.connectStart,
      ttfb: perfData.responseStart - perfData.requestStart,
      download: perfData.responseEnd - perfData.responseStart,
      domInteractive: perfData.domInteractive,
      domComplete: perfData.domComplete,
      loadComplete: perfData.loadEventEnd - perfData.loadEventStart,
    });
  }
});
```

## Troubleshooting

### Build Fails

**Issue**: "No output directory found"
**Solution**: Set build output directory to `panoconfig360_frontend`

**Issue**: Build command fails
**Solution**: Leave build command empty (static site)

### Assets 404

**Issue**: CSS/JS files return 404
**Solution**: Verify paths are relative (no leading `/static/` in production)

### API CORS Errors

**Issue**: `Access-Control-Allow-Origin` errors
**Solution**: 
- Option 1: Configure CORS in backend
- Option 2: Use Cloudflare Functions proxy (Step 8)

### Slow Initial Load

**Issue**: First page load is slow
**Solution**:
- Enable Cloudflare Auto Minify
- Compress images
- Use preconnect/preload hints
- Enable Early Hints

### Cache Not Working

**Issue**: Assets not cached
**Solution**:
- Check `_headers` file is deployed
- Verify Page Rules configuration
- Check Cache-Control headers in Network tab

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| First Contentful Paint | <1s | First meaningful content |
| Time to Interactive | <2s | App becomes interactive |
| Largest Contentful Paint | <2.5s | Main content loaded |
| Cumulative Layout Shift | <0.1 | Visual stability |
| Total Blocking Time | <300ms | Main thread availability |

Test with:
- [PageSpeed Insights](https://pagespeed.web.dev/)
- [WebPageTest](https://www.webpagetest.org/)
- Chrome DevTools Lighthouse

## Cost

**Cloudflare Pages Pricing**:
- **Free tier**: 
  - Unlimited requests
  - Unlimited bandwidth
  - 500 builds/month
  - 1 concurrent build
  
- **Pro tier ($20/month)**:
  - Unlimited requests
  - Unlimited bandwidth
  - 5000 builds/month
  - 5 concurrent builds
  - Advanced features

**Recommendation**: Start with free tier, upgrade if you need more builds.

## Next Steps

- [Configure CORS between services](./DEPLOYMENT_CORS.md)
- [Production hardening](./DEPLOYMENT_HARDENING.md)
- [Performance validation](./DEPLOYMENT_PERFORMANCE.md)
- [End-to-end testing](./DEPLOYMENT_TESTING.md)
