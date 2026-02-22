# Production Deployment Architecture

## Architecture Overview

This document describes the complete production architecture for deploying the Panoconfig360 Totem application to a cloud environment optimized for cost, scalability, and performance.

### High-Level Architecture Diagram (Logical)

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT BROWSER                          │
│                     (https://app.example.com)                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ HTTPS
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUDFLARE PAGES                             │
│              (Static Frontend Hosting + CDN)                    │
│   ┌──────────────────────────────────────────────────────┐     │
│   │  - index.html, CSS, JS (Marzipano viewer)           │     │
│   │  - Auto SSL/TLS                                       │     │
│   │  - Global CDN edge caching                            │     │
│   │  - HTTP/2, Brotli compression                         │     │
│   └──────────────────────────────────────────────────────┘     │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ API Calls (CORS enabled)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        RENDER.COM                               │
│                 (FastAPI Backend Service)                       │
│   ┌──────────────────────────────────────────────────────┐     │
│   │  - FastAPI app (Python)                              │     │
│   │  - Image processing (VIPS, Pillow)                   │     │
│   │  - Cubemap generation & tiling                       │     │
│   │  - Auto-scaling (0-N instances)                      │     │
│   │  - Health checks & monitoring                        │     │
│   │  - Environment variables management                  │     │
│   └──────────────────────────────────────────────────────┘     │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ S3-compatible API
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUDFLARE R2                                │
│              (Object Storage - S3 Compatible)                   │
│   ┌──────────────────────────────────────────────────────┐     │
│   │  Bucket: panoconfig360-tiles                         │     │
│   │  ├── clients/{client_id}/                            │     │
│   │  │   ├── cubemap/{scene_id}/tiles/{build}/          │     │
│   │  │   │   ├── {build}_f_0_0_0.jpg                    │     │
│   │  │   │   ├── {build}_f_1_0_0.jpg                    │     │
│   │  │   │   ├── metadata.json                          │     │
│   │  │   │   └── tile_events.ndjson                     │     │
│   │  └── config/{client_id}/                             │     │
│   │      └── {client_id}_cfg.json                        │     │
│   └──────────────────────────────────────────────────────┘     │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ Public Access (R2.dev domain or custom domain)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUDFLARE CDN                               │
│               (Tiles & Assets Delivery)                         │
│   ┌──────────────────────────────────────────────────────┐     │
│   │  - Custom domain: cdn.example.com                    │     │
│   │  - Cache rules for tiles (immutable, 1 year)         │     │
│   │  - CORS headers for browser access                   │     │
│   │  - High cache hit ratio (>95%)                       │     │
│   │  - Parallel tile loading (8+ concurrent)             │     │
│   └──────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Frontend (Cloudflare Pages)

**Purpose**: Serve static Marzipano viewer and configuration UI

**Technology Stack**:
- Static HTML, CSS, JavaScript
- Marzipano panorama viewer library
- No build process required (vanilla JS)

**Features**:
- **Global CDN**: 200+ edge locations worldwide
- **Auto SSL/TLS**: Free Let's Encrypt certificates
- **HTTP/2 & HTTP/3**: Modern protocol support
- **Brotli compression**: Automatic text compression
- **Atomic deployments**: Zero-downtime deploys
- **Preview deployments**: Every commit gets a preview URL
- **Custom domains**: Multiple domains supported
- **Free tier**: Unlimited bandwidth for static files

**Performance Characteristics**:
- First Contentful Paint: <500ms
- Time to Interactive: <1.5s
- Edge cache: 30 days for static assets
- Support for Cache-Control headers

### 2. Backend (Render.com)

**Purpose**: FastAPI service for image processing and tile generation

**Technology Stack**:
- Python 3.11+
- FastAPI framework
- VIPS for image processing
- Uvicorn ASGI server

**Service Specifications**:
- **Instance type**: Standard (512MB RAM minimum, 1GB recommended)
- **Auto-scaling**: Based on CPU/memory metrics
- **Auto-deploy**: On git push to main branch
- **Health checks**: `/health` endpoint monitoring
- **Zero-downtime deploys**: Rolling updates
- **Persistent disk**: Optional for temporary processing
- **Environment variables**: Encrypted secrets management
- **Custom domains**: SSL/TLS included

**Pricing Strategy**:
- Free tier: Limited hours/month (good for testing)
- Starter: $7/month (suspended when idle)
- Standard: $25/month (always-on, auto-scaling)

**Cold Start Mitigation**:
- Keep-alive ping service (optional, for free tier)
- Render auto-scaling settings
- Background tasks for tile generation
- Async processing queue

### 3. Storage (Cloudflare R2)

**Purpose**: Store generated tiles, metadata, and client configurations

**Key Advantages**:
- **Zero egress fees**: No bandwidth charges
- **S3-compatible API**: Easy migration and integration
- **Low cost**: $0.015/GB storage (much cheaper than S3)
- **Global distribution**: Automatic edge caching
- **Custom domains**: R2.dev subdomain or custom domain
- **Public buckets**: Support for public read access

**Bucket Structure**:
```
panoconfig360-tiles/
├── clients/
│   └── {client-id}/
│       ├── cubemap/{scene-id}/tiles/{build}/
│       │   ├── {build}_f_0_0_0.jpg      # Front face, LOD 0
│       │   ├── {build}_f_1_0_0.jpg      # Front face, LOD 1
│       │   ├── {build}_f_2_0_0.jpg      # Front face, LOD 2
│       │   ├── ... (other faces: b, l, r, u, d)
│       │   ├── metadata.json
│       │   └── tile_events.ndjson
│       └── config/
│           └── {client-id}_cfg.json
└── catalog/
    └── {client-id}_catalog.json
```

**Access Patterns**:
- **Backend (write)**: S3-compatible API with credentials
- **Frontend (read)**: Public HTTPS URLs via R2.dev or custom domain
- **CDN (cache)**: Cloudflare automatically caches at edge

### 4. CDN (Cloudflare)

**Purpose**: Cache and deliver tiles with optimal performance

**Configuration**:
- **Cache Everything**: Enable for R2 custom domain
- **Browser Cache TTL**: 1 year for immutable tiles
- **Edge Cache TTL**: 30 days minimum
- **Query String Sort**: Enabled for consistent cache keys
- **Polish**: Lossless compression for JPEG tiles
- **Mirage**: Lazy loading for mobile

**Cache Rules**:
```
Pattern: cdn.example.com/clients/*/cubemap/*/tiles/*/*.jpg
  └── Cache Level: Cache Everything
  └── Edge Cache TTL: 30 days
  └── Browser Cache TTL: 1 year
  └── Origin Cache Control: respect
  └── Query String Sort: On

Pattern: cdn.example.com/clients/*/config/*.json
  └── Cache Level: Cache Everything
  └── Edge Cache TTL: 5 minutes
  └── Browser Cache TTL: 5 minutes
```

## Data Flow

### 1. Initial Page Load
```
User → Cloudflare Pages (CDN) → index.html, CSS, JS (cached)
                               → Client config.json (from R2/CDN)
```

### 2. Render Request (New Configuration)
```
Frontend → Render API POST /api/render
         ↓
Backend: Process request
    1. Calculate build string (deterministic hash)
    2. Check if tiles exist in R2
    3. If exists: Return metadata (cache hit)
    4. If not exists:
       a. Render LOD 0 synchronously (~1-2s)
       b. Upload LOD 0 tiles to R2
       c. Return metadata immediately
       d. Queue LOD 1+ for background processing
    5. Background workers upload tiles to R2
         ↓
Frontend: Receives tile URLs
         ↓
Load tiles from CDN (R2 + Cloudflare cache)
```

### 3. Tile Loading (Progressive)
```
Frontend → CDN (cache miss) → R2 → Tile JPEG
        ↓
CDN caches tile (1 year TTL)
        ↓
Subsequent requests: CDN (cache hit) → Tile JPEG (instant)
```

### 4. Tile Events Polling
```
Frontend polls: GET /api/render/events?tile_root=...&cursor=...
                ↓
Backend reads: R2 → tile_events.ndjson
                ↓
Returns: New events since cursor
                ↓
Frontend: Updates tiles with ?v=N parameter (cache busting)
```

## Scaling Characteristics

### Multi-Tenant Support

**Isolation**:
- Each client has separate directory in R2
- Build strings ensure configuration uniqueness
- No cross-contamination between clients

**Capacity**:
- R2: Unlimited object count (millions of tiles)
- Backend: Auto-scales based on request volume
- CDN: Global distribution, no single point of failure

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Cold start latency | <3s | Backend warm-up time |
| Render request (cache hit) | <100ms | Metadata only |
| Render request (LOD 0 new) | 1-3s | Synchronous render + upload |
| Tile streaming speed | <50ms | From CDN cache |
| Cache hit ratio | >95% | After warm-up period |
| Parallel tile loading | 8-12 concurrent | Browser HTTP/2 limit |
| Time to first tile | <500ms | LOD 0 initial display |
| Full high-quality load | 10-30s | Progressive enhancement |

### Cost Estimates (Monthly)

**Low Traffic** (1-10 daily active users):
- Cloudflare Pages: $0 (free tier)
- Render.com: $7 (Starter, suspended when idle)
- Cloudflare R2: ~$1 (50GB storage, no egress)
- **Total: ~$8/month**

**Medium Traffic** (100-500 daily active users):
- Cloudflare Pages: $0 (free tier)
- Render.com: $25 (Standard, auto-scaling)
- Cloudflare R2: ~$5 (300GB storage, no egress)
- **Total: ~$30/month**

**High Traffic** (1000+ daily active users):
- Cloudflare Pages: $20 (Pro tier, advanced features)
- Render.com: $85-$200 (multiple instances, auto-scaling)
- Cloudflare R2: ~$15 (1TB storage, no egress)
- **Total: ~$120-$235/month**

## Security Considerations

### Authentication & Authorization
- Optional JWT tokens for API access
- Signed URLs for private client content
- CORS whitelist for allowed origins

### Data Protection
- HTTPS everywhere (TLS 1.3)
- Environment variables for secrets
- No sensitive data in URLs
- Regular security updates

### Rate Limiting
- API: 10 requests/second per IP
- Cloudflare: DDoS protection included
- Backend: Request size limits (10MB max)

## Monitoring & Observability

### Metrics to Track
1. **Backend (Render)**:
   - Request rate and latency
   - Error rate (4xx, 5xx)
   - Memory and CPU usage
   - Background task queue depth

2. **CDN (Cloudflare)**:
   - Cache hit ratio
   - Bandwidth usage
   - Geographic distribution
   - Origin requests

3. **Storage (R2)**:
   - Storage growth rate
   - Request count (GET, PUT)
   - Average object size
   - Failed requests

### Alerting Thresholds
- Backend error rate > 5%
- CDN cache hit ratio < 90%
- Backend response time > 5s (p95)
- Storage request failures > 1%

## Disaster Recovery

### Backup Strategy
- R2 versioning enabled for metadata
- Daily snapshots of configuration files
- Git repository for code and configs
- Recovery Time Objective (RTO): <1 hour
- Recovery Point Objective (RPO): <24 hours

### Rollback Procedures
- Render: One-click rollback to previous deployment
- Cloudflare Pages: Instant rollback to any previous build
- R2: Object versioning for critical files
- Database: Not applicable (stateless architecture)

## Migration Path

From local development to production:
1. **Phase 1**: Deploy backend to Render (keep local storage)
2. **Phase 2**: Migrate storage to R2 (dual-write during transition)
3. **Phase 3**: Deploy frontend to Cloudflare Pages
4. **Phase 4**: Configure CDN and cache rules
5. **Phase 5**: Cut over DNS and monitor
6. **Phase 6**: Optimize based on real traffic patterns

## Next Steps

Refer to the following documents for detailed implementation:
- [Render Deployment Guide](./DEPLOYMENT_RENDER.md)
- [Cloudflare Pages Deployment Guide](./DEPLOYMENT_CLOUDFLARE_PAGES.md)
- [R2 Storage Configuration](./DEPLOYMENT_R2.md)
- [CORS Configuration Guide](./DEPLOYMENT_CORS.md)
- [Production Hardening Checklist](./DEPLOYMENT_HARDENING.md)
- [Performance Validation Guide](./DEPLOYMENT_PERFORMANCE.md)
- [End-to-End Testing Procedures](./DEPLOYMENT_TESTING.md)
