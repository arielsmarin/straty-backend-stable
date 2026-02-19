# Render.com Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Panoconfig360 FastAPI backend to Render.com with production-ready configuration.

## Prerequisites

- GitHub repository with your code
- Render.com account (free tier available)
- Cloudflare R2 credentials (see [DEPLOYMENT_R2.md](./DEPLOYMENT_R2.md))

## Step 1: Prepare Repository

### 1.1 Create `render.yaml` Blueprint

Create a file `render.yaml` in the repository root:

```yaml
services:
  - type: web
    name: panoconfig360-api
    env: python
    region: oregon  # or frankfurt, singapore (choose closest to users)
    plan: starter  # or free, standard depending on needs
    branch: main
    buildCommand: pip install --upgrade pip && pip install -r panoconfig360_backend/requirements.txt
    startCommand: uvicorn panoconfig360_backend.api.server:app --host 0.0.0.0 --port $PORT --workers 2
    healthCheckPath: /health
    envVars:
      # Environment mode
      - key: ENVIRONMENT
        value: production
      
      # R2 Storage configuration
      - key: STORAGE_BACKEND
        value: r2
      - key: R2_ACCOUNT_ID
        sync: false  # Set in Render dashboard (secret)
      - key: R2_ACCESS_KEY_ID
        sync: false  # Set in Render dashboard (secret)
      - key: R2_SECRET_ACCESS_KEY
        sync: false  # Set in Render dashboard (secret)
      - key: R2_BUCKET_NAME
        value: panoconfig360-tiles
      - key: R2_ENDPOINT_URL
        sync: false  # Computed: https://{ACCOUNT_ID}.r2.cloudflarestorage.com
      - key: R2_PUBLIC_URL
        value: https://cdn.example.com  # Your CDN domain
      
      # CORS configuration
      - key: CORS_ORIGINS
        value: https://app.example.com,https://www.example.com
      
      # Performance tuning
      - key: TILE_WORKERS
        value: 4
      - key: MAX_TILE_CONCURRENCY
        value: 8
      
      # Rate limiting
      - key: RATE_LIMIT_ENABLED
        value: true
      - key: RATE_LIMIT_REQUESTS
        value: 10
      - key: RATE_LIMIT_PERIOD
        value: 1
      
      # Request size limits
      - key: MAX_UPLOAD_SIZE_MB
        value: 10
      
      # Logging
      - key: LOG_LEVEL
        value: INFO
      - key: LOG_FORMAT
        value: json
```

### 1.2 Update `requirements.txt`

Ensure all production dependencies are listed in `panoconfig360_backend/requirements.txt`:

```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
pyvips>=2.2.1
pillow>=10.0.0
python-multipart>=0.0.6
httpx>=0.25.0
boto3>=1.28.0  # For S3-compatible R2 access
python-dotenv>=1.0.0  # For local development
slowapi>=0.1.9  # Rate limiting
```

### 1.3 Create Health Check Endpoint

Add to `panoconfig360_backend/api/server.py`:

```python
@app.get("/health")
async def health_check():
    """
    Health check endpoint for Render monitoring.
    Returns 200 OK if service is healthy.
    """
    return {
        "status": "healthy",
        "service": "panoconfig360-api",
        "version": "1.0.0",
        "timestamp": int(time.time())
    }
```

### 1.4 Add Runtime Specification (Optional)

Create `panoconfig360_backend/runtime.txt` if you need a specific Python version:

```txt
python-3.11.6
```

## Step 2: Configure Render Service

### 2.1 Create New Web Service

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select the repository: `your-username/panoconfig360_totem`

### 2.2 Configure Build Settings

**Service Name**: `panoconfig360-api`
**Region**: Choose closest to your users (Oregon, Frankfurt, Singapore)
**Branch**: `main`
**Root Directory**: *(leave empty, use full repo)*
**Runtime**: `Python 3`
**Build Command**:
```bash
pip install --upgrade pip && pip install -r panoconfig360_backend/requirements.txt
```
**Start Command**:
```bash
uvicorn panoconfig360_backend.api.server:app --host 0.0.0.0 --port $PORT --workers 2
```

### 2.3 Configure Instance

**Plan**: 
- **Free**: For testing only (spins down after inactivity, 750 hrs/month)
- **Starter ($7/month)**: Best for development (suspends when idle, saves cost)
- **Standard ($25/month)**: Production (always-on, auto-scales)

**Recommended for Production**: Standard plan with auto-scaling

### 2.4 Health Check Configuration

**Health Check Path**: `/health`
**Health Check Interval**: 30 seconds
**Timeout**: 10 seconds
**Healthy Threshold**: 2
**Unhealthy Threshold**: 3

## Step 3: Set Environment Variables

In the Render dashboard, go to **Environment** tab and add:

### Required Variables

```bash
# Storage
STORAGE_BACKEND=r2
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET_NAME=panoconfig360-tiles
R2_ENDPOINT_URL=https://your_account_id.r2.cloudflarestorage.com
R2_PUBLIC_URL=https://cdn.example.com

# CORS (comma-separated origins)
CORS_ORIGINS=https://app.example.com,https://www.example.com

# Performance
TILE_WORKERS=4
MAX_TILE_CONCURRENCY=8

# Security
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_PERIOD=1
MAX_UPLOAD_SIZE_MB=10

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### Optional Variables

```bash
# JWT Authentication (if using token-based auth)
JWT_SECRET_KEY=your-secret-key-here-min-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Sentry (error tracking)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# New Relic (APM monitoring)
NEW_RELIC_LICENSE_KEY=your-license-key
NEW_RELIC_APP_NAME=panoconfig360-api
```

## Step 4: Configure Auto-Deploy

### 4.1 Enable Auto-Deploy

In **Settings** → **Build & Deploy**:
- ✅ Enable **Auto-Deploy**: Yes
- **Branch**: `main`
- **Deploy on push**: Enabled

### 4.2 Deploy Hooks (Optional)

For manual deployments or CI/CD integration:

1. Go to **Settings** → **Deploy Hook**
2. Create a new deploy hook
3. Copy the webhook URL
4. Use in GitHub Actions or manual triggers:

```bash
curl -X POST https://api.render.com/deploy/srv-xxxxx?key=yyyy
```

## Step 5: Configure Custom Domain

### 5.1 Add Custom Domain

1. Go to **Settings** → **Custom Domain**
2. Click **"Add Custom Domain"**
3. Enter your API domain: `api.example.com`
4. Render will provide DNS records

### 5.2 Update DNS Records

Add to your DNS provider (e.g., Cloudflare):

**CNAME Record**:
```
api.example.com → panoconfig360-api.onrender.com
```

**Or A Record** (if CNAME not supported at apex):
```
api.example.com → [IP provided by Render]
```

### 5.3 Enable SSL/TLS

Render automatically provisions Let's Encrypt SSL certificates.
Wait 5-10 minutes for certificate issuance.

## Step 6: Configure Auto-Scaling (Standard Plan Only)

### 6.1 Scaling Settings

In **Settings** → **Scaling**:

**Auto-Scaling**:
- Minimum instances: 1
- Maximum instances: 3
- Target CPU: 70%
- Target Memory: 80%

**Manual Scaling** (if needed):
- Set a fixed number of instances

### 6.2 Scaling Triggers

Render auto-scales based on:
- CPU usage
- Memory usage
- Request queue depth

## Step 7: Install System Dependencies (VIPS)

### 7.1 Add Build Script

Create `panoconfig360_backend/build.sh`:

```bash
#!/bin/bash
set -e

echo "Installing system dependencies..."

# Install libvips for image processing
apt-get update
apt-get install -y libvips-dev libvips-tools

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r panoconfig360_backend/requirements.txt

echo "Build complete!"
```

Make it executable:
```bash
chmod +x panoconfig360_backend/build.sh
```

### 7.2 Update Build Command

In Render dashboard, update **Build Command**:
```bash
bash panoconfig360_backend/build.sh
```

## Step 8: Deploy and Verify

### 8.1 Trigger First Deploy

Click **"Manual Deploy"** → **"Deploy latest commit"**

Monitor the deploy logs in real-time.

### 8.2 Verify Deployment

Once deployed, test endpoints:

**Health Check**:
```bash
curl https://api.example.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "panoconfig360-api",
  "version": "1.0.0",
  "timestamp": 1234567890
}
```

**API Documentation**:
```
https://api.example.com/docs
```

**Render Test**:
```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "test-client",
    "scene": "test-scene",
    "selection": {"layer1": "material1"}
  }'
```

## Step 9: Configure Monitoring

### 9.1 Render Built-in Metrics

In Render dashboard, monitor:
- **Metrics** tab: CPU, Memory, Requests/sec
- **Logs** tab: Application logs in real-time
- **Events** tab: Deploy history and system events

### 9.2 Set Up Alerts

In **Settings** → **Notifications**:

**Email Alerts**:
- Service crashes
- Deploy failures
- High error rates

**Slack Integration** (optional):
- Connect to Slack workspace
- Get real-time notifications

### 9.3 External Monitoring (Recommended)

**UptimeRobot** (free tier):
```
Monitor URL: https://api.example.com/health
Interval: 5 minutes
Alert on: Down status
```

**Better Uptime** (paid):
```
Monitor URL: https://api.example.com/health
Interval: 30 seconds
On-call schedule: Yes
```

## Step 10: Production Hardening

### 10.1 Enable DDoS Protection

Cloudflare (if using Cloudflare DNS):
- Enable "Under Attack" mode if needed
- Set security level to "High"
- Enable rate limiting rules

### 10.2 Configure CORS Properly

Update environment variable:
```bash
CORS_ORIGINS=https://app.example.com,https://preview-*.pages.dev
```

This allows both production and Cloudflare Pages preview deployments.

### 10.3 Set Request Size Limits

In application code (`server.py`):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    max_age=3600,
)

# Add request size limit
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                return JSONResponse(
                    status_code=413,
                    content={"error": "Request too large"}
                )
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware, max_size=10 * 1024 * 1024)
```

## Troubleshooting

### Build Fails

**Issue**: `libvips not found`
**Solution**: Add system dependencies in `build.sh` (see Step 7)

**Issue**: `requirements.txt not found`
**Solution**: Verify path is `panoconfig360_backend/requirements.txt`

### Service Crashes

**Issue**: Out of memory
**Solution**: Upgrade to larger instance or optimize image processing

**Issue**: Port binding error
**Solution**: Ensure using `$PORT` environment variable from Render

### Slow Cold Starts

**Issue**: Free tier spins down after inactivity
**Solution**: 
- Upgrade to Starter/Standard plan
- Use external ping service to keep warm
- Accept 10-20s cold start delay

### CORS Errors

**Issue**: `Access-Control-Allow-Origin` errors
**Solution**: Verify `CORS_ORIGINS` includes frontend domain with https://

## Performance Optimization

### 1. Enable HTTP/2
Render enables HTTP/2 by default. Ensure your client supports it.

### 2. Use Connection Pooling
Configure uvicorn workers based on instance size:
- Free/Starter: 1-2 workers
- Standard: 2-4 workers

### 3. Background Tasks
Use FastAPI background tasks for long-running operations:
```python
from fastapi import BackgroundTasks

@app.post("/api/render")
async def render(request: RenderRequest, background_tasks: BackgroundTasks):
    # Quick LOD 0 render
    result = quick_render(request)
    
    # Queue high-quality render
    background_tasks.add_task(render_high_quality, request)
    
    return result
```

### 4. Caching
Implement in-memory caching for frequently accessed data:
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def load_config(client_id: str):
    # Cached config loading
    return get_config_from_r2(client_id)
```

## Cost Optimization

### Free Tier Strategy
- Use free tier for development/staging
- Accept cold starts and limited hours
- Monitor usage carefully (750 hrs/month)

### Starter Plan Strategy ($7/month)
- Service suspends when idle (saves money)
- Auto-resumes on request (3-10s delay)
- Good for low-traffic production

### Standard Plan Strategy ($25/month)
- Always-on for production
- Auto-scales based on traffic
- Predictable costs

## Next Steps

- [Configure Cloudflare R2 Storage](./DEPLOYMENT_R2.md)
- [Set up Cloudflare Pages](./DEPLOYMENT_CLOUDFLARE_PAGES.md)
- [Configure CORS](./DEPLOYMENT_CORS.md)
- [Production hardening checklist](./DEPLOYMENT_HARDENING.md)
