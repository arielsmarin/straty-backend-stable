# CORS Configuration Guide

## Overview

This guide covers Cross-Origin Resource Sharing (CORS) configuration for the Panoconfig360 system, ensuring secure communication between:
- Frontend (Cloudflare Pages) → Backend API (Render)
- Frontend (Browser) → Tiles CDN (Cloudflare R2)

## Understanding the CORS Architecture

```
Browser (https://app.example.com)
    │
    ├──> API Requests (POST /api/render)
    │    └──> Backend (https://api.example.com)  [CORS Required]
    │
    └──> Tile Requests (GET /tiles/*.jpg)
         └──> CDN (https://cdn.example.com)      [CORS Required]
```

## Part 1: Backend API CORS (Render)

### 1.1 Install FastAPI CORS Middleware

Already included in FastAPI. Ensure `fastapi` is in requirements.txt.

### 1.2 Configure CORS in Backend

Update `panoconfig360_backend/api/server.py`:

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Panoconfig360 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # List of allowed origins
    allow_credentials=True,       # Allow cookies and auth headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],          # Allow all headers
    expose_headers=["*"],         # Expose all response headers
    max_age=3600,                 # Cache preflight requests for 1 hour
)

# ... rest of your app
```

### 1.3 Set CORS Origins in Render

In Render dashboard, set environment variable:

**Development + Production**:
```bash
CORS_ORIGINS=https://app.example.com,https://*.pages.dev,http://localhost:3000
```

Note: `https://*.pages.dev` allows all preview deployments from Cloudflare Pages.

### 1.4 Handle Wildcard Subdomains

For preview deployments, you may need custom logic:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import re

class DynamicCORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_origins_patterns: list[str]):
        super().__init__(app)
        self.patterns = [re.compile(pattern) for pattern in allowed_origins_patterns]

    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        
        # Check if origin matches any pattern
        allowed = False
        if origin:
            for pattern in self.patterns:
                if pattern.match(origin):
                    allowed = True
                    break
        
        # Handle preflight
        if request.method == "OPTIONS":
            if allowed:
                return Response(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                        "Access-Control-Max-Age": "3600",
                        "Access-Control-Allow-Credentials": "true",
                    },
                )
            return Response(status_code=403)
        
        # Process request
        response = await call_next(request)
        
        # Add CORS headers to response
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response

# Use this instead of CORSMiddleware for wildcard support
app.add_middleware(
    DynamicCORSMiddleware,
    allowed_origins_patterns=[
        r"https://app\.example\.com",
        r"https://.*\.pages\.dev",  # All Cloudflare Pages previews
        r"http://localhost:\d+",     # Local development
    ]
)
```

## Part 2: CDN CORS (Cloudflare R2)

### 2.1 Configure R2 Bucket CORS

Create `scripts/r2-cors-config.json`:

```json
{
  "CORSRules": [
    {
      "ID": "AllowFrontendAccess",
      "AllowedOrigins": [
        "https://app.example.com",
        "https://*.pages.dev"
      ],
      "AllowedMethods": [
        "GET",
        "HEAD"
      ],
      "AllowedHeaders": [
        "*"
      ],
      "ExposeHeaders": [
        "ETag",
        "Content-Length",
        "Content-Type",
        "Last-Modified"
      ],
      "MaxAgeSeconds": 3600
    },
    {
      "ID": "AllowLocalDev",
      "AllowedOrigins": [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
      ],
      "AllowedMethods": [
        "GET",
        "HEAD"
      ],
      "AllowedHeaders": [
        "*"
      ],
      "ExposeHeaders": [
        "ETag",
        "Content-Length"
      ],
      "MaxAgeSeconds": 3600
    }
  ]
}
```

### 2.2 Apply CORS Configuration

Using AWS CLI (configured for R2):

```bash
#!/bin/bash
# scripts/apply-r2-cors.sh

ACCOUNT_ID="your_account_id"
BUCKET_NAME="panoconfig360-tiles"

aws s3api put-bucket-cors \
  --bucket "$BUCKET_NAME" \
  --cors-configuration file://scripts/r2-cors-config.json \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2

echo "✅ CORS configuration applied to R2 bucket"
```

### 2.3 Verify R2 CORS

```bash
aws s3api get-bucket-cors \
  --bucket panoconfig360-tiles \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2
```

### 2.4 Add CORS Headers via Cloudflare Transform Rules

For custom domain (cdn.example.com), add headers via Cloudflare:

1. Go to Cloudflare Dashboard → Your domain
2. Navigate to **Rules** → **Transform Rules** → **Modify Response Header**
3. Create new rule

**Rule: Add CORS Headers to CDN**
```
Rule name: CDN CORS Headers

When incoming requests match:
  - Hostname equals cdn.example.com

Then:
  Set static header:
    - Access-Control-Allow-Origin: *
    - Access-Control-Allow-Methods: GET, HEAD
    - Access-Control-Max-Age: 3600
    - Timing-Allow-Origin: *
```

**For restricted origins** (more secure):
```
When incoming requests match:
  - Hostname equals cdn.example.com

Then:
  Set dynamic header:
    - Header name: Access-Control-Allow-Origin
    - Value: 
      if (http.request.headers["origin"][0] contains "example.com" or 
          http.request.headers["origin"][0] contains "pages.dev",
        http.request.headers["origin"][0],
        "null"
      )
```

## Part 3: Testing CORS Configuration

### 3.1 Test Backend CORS

**Test from command line**:

```bash
# Preflight request (OPTIONS)
curl -X OPTIONS \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  https://api.example.com/api/render \
  -v

# Actual request
curl -X POST \
  -H "Origin: https://app.example.com" \
  -H "Content-Type: application/json" \
  -d '{"client":"test","scene":"test","selection":{}}' \
  https://api.example.com/api/render \
  -v
```

**Expected headers**:
```
< access-control-allow-origin: https://app.example.com
< access-control-allow-methods: GET, POST, PUT, DELETE, OPTIONS
< access-control-allow-headers: *
< access-control-max-age: 3600
```

**Test from browser console**:

```javascript
// Open https://app.example.com in browser
// Run in console:

fetch('https://api.example.com/api/render', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    client: 'test',
    scene: 'test',
    selection: {}
  })
})
.then(r => r.json())
.then(console.log)
.catch(console.error);
```

### 3.2 Test CDN CORS

**Test from command line**:

```bash
curl -X GET \
  -H "Origin: https://app.example.com" \
  https://cdn.example.com/clients/test/cubemap/test/tiles/abc123/abc123_f_0_0_0.jpg \
  -v
```

**Expected headers**:
```
< access-control-allow-origin: https://app.example.com
< access-control-allow-methods: GET, HEAD
```

**Test from browser console**:

```javascript
// Open https://app.example.com in browser
// Run in console:

fetch('https://cdn.example.com/clients/test/cubemap/test/tiles/abc123/abc123_f_0_0_0.jpg')
  .then(r => r.blob())
  .then(blob => console.log('Image loaded:', blob.size, 'bytes'))
  .catch(console.error);
```

### 3.3 Test with Real Panorama Viewer

Create a test HTML file:

```html
<!DOCTYPE html>
<html>
<head>
  <title>CORS Test</title>
</head>
<body>
  <h1>CORS Test</h1>
  <div id="status"></div>
  
  <script>
    const status = document.getElementById('status');
    
    async function testCORS() {
      status.innerHTML = '<p>Testing CORS...</p>';
      
      // Test API
      try {
        const apiResponse = await fetch('https://api.example.com/health');
        status.innerHTML += '<p>✅ API CORS working</p>';
      } catch (err) {
        status.innerHTML += `<p>❌ API CORS failed: ${err.message}</p>`;
      }
      
      // Test CDN
      try {
        const cdnResponse = await fetch('https://cdn.example.com/test.jpg');
        status.innerHTML += '<p>✅ CDN CORS working</p>';
      } catch (err) {
        status.innerHTML += `<p>❌ CDN CORS failed: ${err.message}</p>`;
      }
    }
    
    testCORS();
  </script>
</body>
</html>
```

## Part 4: Common CORS Errors and Solutions

### Error 1: "No 'Access-Control-Allow-Origin' header"

**Symptom**: 
```
Access to fetch at 'https://api.example.com/api/render' from origin 
'https://app.example.com' has been blocked by CORS policy: 
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

**Causes**:
1. CORS middleware not configured
2. Origin not in allowed list
3. Backend not returning CORS headers

**Solutions**:
- Verify CORS middleware is added
- Check `CORS_ORIGINS` environment variable
- Test preflight request manually
- Check backend logs for errors

### Error 2: "Preflight request failed"

**Symptom**:
```
Access to fetch at '...' from origin '...' has been blocked by CORS policy: 
Response to preflight request doesn't pass access control check: 
It does not have HTTP ok status.
```

**Causes**:
1. OPTIONS request not handled
2. 404/500 error on OPTIONS
3. Authentication required for OPTIONS

**Solutions**:
- Ensure OPTIONS method is allowed
- Don't require auth for OPTIONS requests
- Check server logs for OPTIONS requests

### Error 3: "Wildcard in Allow-Origin with credentials"

**Symptom**:
```
The value of the 'Access-Control-Allow-Origin' header in the response must not 
be the wildcard '*' when the request's credentials mode is 'include'.
```

**Cause**: Using `allow_origins=["*"]` with `allow_credentials=True`

**Solution**: Use specific origins or use dynamic CORS (Part 1.4)

### Error 4: "Method not allowed"

**Symptom**:
```
Method POST is not allowed by Access-Control-Allow-Methods in preflight response.
```

**Cause**: Method not in `allow_methods` list

**Solution**: Add method to `allow_methods`:
```python
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
```

### Error 5: "Header not allowed"

**Symptom**:
```
Request header field content-type is not allowed by Access-Control-Allow-Headers 
in preflight response.
```

**Cause**: Header not in `allow_headers` list

**Solution**: Use `allow_headers=["*"]` or add specific headers

## Part 5: Security Best Practices

### 5.1 Principle of Least Privilege

**Don't use wildcards in production**:

```python
# ❌ TOO PERMISSIVE
allow_origins=["*"]

# ✅ SPECIFIC ORIGINS
allow_origins=[
    "https://app.example.com",
    "https://www.example.com"
]
```

### 5.2 Limit Methods

**Only allow necessary HTTP methods**:

```python
# ❌ TOO PERMISSIVE
allow_methods=["*"]

# ✅ SPECIFIC METHODS
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
```

### 5.3 Limit Headers

**For APIs with auth**:

```python
# ❌ ALLOWS ALL HEADERS
allow_headers=["*"]

# ✅ SPECIFIC HEADERS
allow_headers=[
    "Content-Type",
    "Authorization",
    "X-Request-ID"
]
```

### 5.4 Set Appropriate Max Age

**Cache preflight requests**:

```python
# Cache for 1 hour (reduces preflight requests)
max_age=3600

# For frequently changing CORS config
max_age=300  # 5 minutes
```

### 5.5 Use HTTPS Everywhere

**Never allow HTTP origins in production**:

```python
# ❌ INSECURE
CORS_ORIGINS = "http://app.example.com"

# ✅ SECURE
CORS_ORIGINS = "https://app.example.com"
```

### 5.6 Monitor CORS Errors

**Log rejected CORS requests**:

```python
import logging

class CORSLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        
        if origin and origin not in ALLOWED_ORIGINS:
            logging.warning(f"CORS rejected: {origin} -> {request.url}")
        
        return await call_next(request)

app.add_middleware(CORSLoggingMiddleware)
```

## Part 6: Development vs Production

### 6.1 Environment-Specific Configuration

```python
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    CORS_ORIGINS = [
        "https://app.example.com",
        "https://www.example.com",
    ]
else:
    CORS_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "https://app.example.com",  # Still allow prod for testing
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)
```

### 6.2 Preview Deployments

For Cloudflare Pages preview deployments:

```python
import re

def is_allowed_origin(origin: str) -> bool:
    allowed_patterns = [
        r"^https://app\.example\.com$",
        r"^https://.*\.pages\.dev$",  # All preview deployments
        r"^http://localhost:\d+$",     # Local dev
    ]
    
    for pattern in allowed_patterns:
        if re.match(pattern, origin):
            return True
    
    return False

# Use in middleware
```

## Part 7: Monitoring and Debugging

### 7.1 Enable CORS Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Log all CORS requests
@app.middleware("http")
async def log_cors(request, call_next):
    origin = request.headers.get("origin")
    if origin:
        logging.info(f"CORS request: {request.method} {request.url} from {origin}")
    
    response = await call_next(request)
    
    if origin:
        allowed_origin = response.headers.get("access-control-allow-origin")
        if allowed_origin:
            logging.info(f"CORS allowed: {origin}")
        else:
            logging.warning(f"CORS rejected: {origin}")
    
    return response
```

### 7.2 Browser DevTools

**Check Network tab**:
1. Open DevTools (F12)
2. Go to Network tab
3. Look for failed requests (red)
4. Click request → Headers tab
5. Check "Response Headers" for CORS headers

**Check Console**:
- CORS errors appear in console
- Shows which header/method/origin is rejected

### 7.3 CORS Testing Tools

**Online tools**:
- [Test CORS](https://www.test-cors.org/)
- [CORS Tester](https://cors-test.codehappy.dev/)

**Browser extensions**:
- CORS Unblock (for testing only, disable in production)
- ModHeader (modify headers for testing)

## Quick Reference

### Backend CORS Checklist
- [ ] CORS middleware installed and configured
- [ ] Allowed origins include frontend domain
- [ ] Allowed methods include all used methods
- [ ] Allowed headers include all used headers
- [ ] `allow_credentials=True` if using cookies/auth
- [ ] Environment variable `CORS_ORIGINS` set in Render
- [ ] Test preflight and actual requests

### CDN CORS Checklist
- [ ] R2 bucket CORS configured
- [ ] Cloudflare Transform Rules add CORS headers
- [ ] Test tile loading from browser
- [ ] Verify headers in Network tab
- [ ] Check both direct R2 URLs and custom domain

### Security Checklist
- [ ] No wildcard origins in production
- [ ] HTTPS only (no HTTP origins)
- [ ] Limited methods (only what's needed)
- [ ] Limited headers (if using auth)
- [ ] CORS logging enabled
- [ ] Monitor rejected requests

## Next Steps

- [Production Hardening](./DEPLOYMENT_HARDENING.md)
- [Performance Validation](./DEPLOYMENT_PERFORMANCE.md)
- [End-to-End Testing](./DEPLOYMENT_TESTING.md)
