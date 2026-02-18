# Production Hardening Guide

## Overview

This guide covers security, reliability, and operational best practices for running Panoconfig360 in production.

## 1. Rate Limiting

### 1.1 Install SlowAPI (Token Bucket Rate Limiter)

Add to `panoconfig360_backend/requirements.txt`:
```txt
slowapi>=0.1.9
redis>=4.5.0  # Optional: for distributed rate limiting
```

### 1.2 Configure Rate Limiting

Update `panoconfig360_backend/api/server.py`:

```python
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,  # Rate limit by IP
    default_limits=["100/minute"],  # Global default
    storage_uri=os.getenv("REDIS_URL"),  # Optional: Redis for distributed
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Apply rate limits to endpoints
@app.post("/api/render")
@limiter.limit("10/minute")  # Max 10 renders per minute per IP
async def render_panorama(
    request: Request,
    render_request: RenderRequest
):
    # ... implementation
    pass

@app.get("/api/render/events")
@limiter.limit("60/minute")  # More lenient for polling
async def get_events(request: Request):
    # ... implementation
    pass

@app.get("/health")
@limiter.exempt  # No rate limit on health checks
async def health_check():
    return {"status": "healthy"}
```

### 1.3 Custom Rate Limit Keys

For authenticated users, rate limit by user ID:

```python
from slowapi import Limiter
from fastapi import Header, HTTPException

def get_user_id_or_ip(request: Request) -> str:
    """Rate limit by user ID if authenticated, otherwise by IP"""
    # Check for auth token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Decode token and extract user_id (simplified)
        try:
            user_id = decode_jwt(token).get("sub")
            return f"user:{user_id}"
        except:
            pass
    
    # Fallback to IP
    return get_remote_address(request)

limiter = Limiter(
    key_func=get_user_id_or_ip,
    default_limits=["100/minute"],
)
```

### 1.4 Rate Limit Response

Customize rate limit error response:

```python
from fastapi.responses import JSONResponse

@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": exc.detail.split("Retry after ")[1] if "Retry after" in exc.detail else "60 seconds"
        },
        headers={
            "Retry-After": "60",
            "X-RateLimit-Limit": "10",
            "X-RateLimit-Remaining": "0",
        }
    )
```

## 2. Request Size Limits

### 2.1 Configure Uvicorn Limits

In Render start command:
```bash
uvicorn panoconfig360_backend.api.server:app \
  --host 0.0.0.0 \
  --port $PORT \
  --workers 2 \
  --limit-max-requests 1000 \
  --limit-request-line 8192 \
  --limit-request-fields 100 \
  --limit-request-field-size 8192
```

### 2.2 Middleware for Body Size Limit

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length:
                if int(content_length) > self.max_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "request_too_large",
                            "message": f"Request body must be less than {self.max_size / 1024 / 1024}MB",
                            "max_size_bytes": self.max_size
                        }
                    )
        
        return await call_next(request)

# Add to app
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024
app.add_middleware(RequestSizeLimitMiddleware, max_size=MAX_UPLOAD_SIZE)
```

## 3. Authentication & Authorization

### 3.1 JWT Token Authentication (Optional)

Install dependencies:
```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

Create `panoconfig360_backend/auth/jwt.py`:

```python
import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Use in endpoints
from panoconfig360_backend.auth.jwt import verify_token

@app.post("/api/render")
async def render_panorama(
    render_request: RenderRequest,
    token: dict = Security(verify_token)  # Requires valid JWT
):
    user_id = token.get("sub")
    # ... implementation
```

### 3.2 API Key Authentication (Simpler Alternative)

```python
import os
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

VALID_API_KEYS = os.getenv("API_KEYS", "").split(",")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    return api_key

# Use in endpoints
@app.post("/api/render")
async def render_panorama(
    render_request: RenderRequest,
    api_key: str = Security(verify_api_key)
):
    # ... implementation
```

### 3.3 Signed URLs for Private Content

Generate time-limited signed URLs for R2 objects:

```python
import time
import hmac
import hashlib
from urllib.parse import urlencode

def generate_signed_url(
    object_key: str,
    expires_in: int = 3600,
    secret: str = None
) -> str:
    secret = secret or os.getenv("SIGNED_URL_SECRET", "change-me")
    
    expiration = int(time.time()) + expires_in
    
    # Create signature
    message = f"{object_key}:{expiration}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Build URL
    base_url = os.getenv("R2_PUBLIC_URL", "https://cdn.example.com")
    params = urlencode({
        "expires": expiration,
        "signature": signature
    })
    
    return f"{base_url}/{object_key}?{params}"

# Verify signature (middleware or endpoint)
def verify_signed_url(object_key: str, expires: str, signature: str) -> bool:
    secret = os.getenv("SIGNED_URL_SECRET", "change-me")
    
    # Check expiration
    if int(expires) < time.time():
        return False
    
    # Verify signature
    message = f"{object_key}:{expires}"
    expected_signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)
```

## 4. Logging & Monitoring

### 4.1 Structured Logging

```python
import logging
import json
import sys
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj)

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # or "text"

if LOG_FORMAT == "json":
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logging.root.addHandler(handler)
    logging.root.setLevel(LOG_LEVEL)
else:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout
    )

logger = logging.getLogger(__name__)
```

### 4.2 Request Logging Middleware

```python
import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log request
    logger.info(
        "Request started",
        extra={
            "method": request.method,
            "url": str(request.url),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
    )
    
    # Process request
    response = await call_next(request)
    
    # Log response
    duration = time.time() - start_time
    logger.info(
        "Request completed",
        extra={
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
        }
    )
    
    # Add custom headers
    response.headers["X-Response-Time"] = str(round(duration * 1000, 2))
    
    return response
```

### 4.3 Error Tracking (Sentry)

Install Sentry:
```bash
pip install sentry-sdk[fastapi]
```

Configure in `server.py`:

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

SENTRY_DSN = os.getenv("SENTRY_DSN")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        traces_sample_rate=0.1,  # 10% of transactions
        profiles_sample_rate=0.1,  # 10% profiling
        integrations=[
            StarletteIntegration(transaction_style="url"),
            FastApiIntegration(transaction_style="url"),
        ],
        before_send=lambda event, hint: event if ENVIRONMENT == "production" else None,
    )
```

### 4.4 Health Check with Dependencies

```python
@app.get("/health")
async def health_check():
    """
    Comprehensive health check
    """
    health = {
        "status": "healthy",
        "timestamp": int(time.time()),
        "service": "panoconfig360-api",
        "version": "1.0.0",
    }
    
    # Check R2 connection
    try:
        from panoconfig360_backend.storage.factory import exists
        exists("health-check.txt")
        health["storage"] = "healthy"
    except Exception as e:
        health["storage"] = "unhealthy"
        health["storage_error"] = str(e)
        health["status"] = "degraded"
    
    # Check memory usage
    import psutil
    memory = psutil.virtual_memory()
    health["memory_percent"] = memory.percent
    if memory.percent > 90:
        health["status"] = "degraded"
    
    # Return appropriate status code
    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)
```

## 5. Security Headers

### 5.1 Add Security Middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        
        # Remove server header
        response.headers.pop("server", None)
        
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

### 5.2 Content Security Policy

```python
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://cdn.example.com; "
    "font-src 'self'; "
    "connect-src 'self' https://api.example.com https://cdn.example.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP_POLICY
    return response
```

## 6. Input Validation

### 6.1 Pydantic Models with Constraints

```python
from pydantic import BaseModel, Field, validator
from typing import Dict

class RenderRequest(BaseModel):
    client: str = Field(..., min_length=1, max_length=100, regex="^[a-z0-9-]+$")
    scene: str = Field(..., min_length=1, max_length=100, regex="^[a-z0-9-]+$")
    selection: Dict[str, str] = Field(..., max_items=10)
    
    @validator('selection')
    def validate_selection(cls, v):
        # Ensure all keys and values are safe
        for key, value in v.items():
            if not key.isalnum():
                raise ValueError(f"Invalid layer name: {key}")
            if not value.replace("-", "").isalnum():
                raise ValueError(f"Invalid material name: {value}")
        return v

    class Config:
        # Prevent extra fields
        extra = "forbid"
```

### 6.2 Path Parameter Validation

```python
from fastapi import Path, HTTPException
import re

@app.get("/api/tiles/{client}/{scene}/{build}/{filename}")
async def get_tile(
    client: str = Path(..., regex="^[a-z0-9-]+$"),
    scene: str = Path(..., regex="^[a-z0-9-]+$"),
    build: str = Path(..., regex="^[0-9a-z]{12}$"),
    filename: str = Path(..., regex="^[0-9a-z]+_[fblrud]_\\d+_\\d+_\\d+\\.jpg$"),
):
    # Safe to use - all validated
    pass
```

## 7. DDoS Protection

### 7.1 Cloudflare Settings

In Cloudflare Dashboard:

**Security** → **Settings**:
- Security Level: High
- Challenge Passage: 30 minutes
- Browser Integrity Check: ✅
- Privacy Pass: ✅

**Security** → **WAF**:
- Enable OWASP Core Ruleset
- Enable Cloudflare Managed Ruleset

**Security** → **DDoS**:
- HTTP DDoS Attack Protection: ✅
- Network-layer DDoS Attack Protection: ✅

**Security** → **Rate Limiting** (Page Rules):
```
Rule 1: Render endpoint
  - URL: api.example.com/api/render
  - Requests: 10 per minute
  - Period: 1 minute
  - Action: Challenge or Block

Rule 2: API overall
  - URL: api.example.com/api/*
  - Requests: 100 per minute
  - Period: 1 minute
  - Action: Challenge
```

### 7.2 Render Protection

Enable in Render dashboard:
- **DDoS Protection**: Included by default
- **Auto-scaling**: Handles traffic spikes
- **Health checks**: Automatic restart on failures

## 8. Data Validation & Sanitization

### 8.1 Sanitize User Input

```python
import re
import bleach

def sanitize_string(value: str, max_length: int = 100) -> str:
    """Remove potentially dangerous characters"""
    # Remove control characters
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
    
    # Remove path traversal attempts
    value = value.replace('../', '').replace('..\\', '')
    
    # Limit length
    value = value[:max_length]
    
    # Remove HTML tags (if any)
    value = bleach.clean(value, tags=[], strip=True)
    
    return value.strip()

# Use in validators
@validator('client', 'scene')
def sanitize_field(cls, v):
    return sanitize_string(v, max_length=100)
```

### 8.2 File Upload Validation (If Applicable)

```python
from fastapi import UploadFile
import magic  # python-magic

ALLOWED_MIME_TYPES = ["image/jpeg", "image/png"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_upload(file: UploadFile):
    # Check file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large")
    
    # Check MIME type
    mime_type = magic.from_buffer(contents, mime=True)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Invalid file type: {mime_type}")
    
    # Reset file pointer
    await file.seek(0)
    
    return file
```

## 9. Secrets Management

### 9.1 Environment Variables Best Practices

**Never commit secrets**:
```bash
# .gitignore
.env
.env.local
.env.production
secrets/
*.key
*.pem
```

**Use .env for local development**:
```bash
# .env.example (commit this)
STORAGE_BACKEND=local
R2_ACCOUNT_ID=your_account_id_here
R2_ACCESS_KEY_ID=your_access_key_here
# ... other vars

# .env (don't commit this)
STORAGE_BACKEND=r2
R2_ACCOUNT_ID=actual_account_id
R2_ACCESS_KEY_ID=actual_access_key
R2_SECRET_ACCESS_KEY=actual_secret_key
```

**Load environment variables**:
```python
from dotenv import load_dotenv
import os

# Load .env file in development
if os.getenv("ENVIRONMENT") != "production":
    load_dotenv()

# Use environment variables
R2_SECRET = os.getenv("R2_SECRET_ACCESS_KEY")
if not R2_SECRET:
    raise ValueError("R2_SECRET_ACCESS_KEY not set")
```

### 9.2 Rotate Secrets Regularly

**Create rotation script** `scripts/rotate-r2-keys.sh`:
```bash
#!/bin/bash
# Rotate R2 API keys

# 1. Generate new API token in Cloudflare
# 2. Update Render environment variables
# 3. Deploy with new keys
# 4. Wait for deployment
# 5. Delete old API token

echo "Remember to:"
echo "1. Create new R2 API token in Cloudflare dashboard"
echo "2. Update RENDER environment variables"
echo "3. Delete old token after successful deployment"
```

## 10. Backup & Recovery

### 10.1 Backup Strategy

**Configuration files** (daily):
```bash
#!/bin/bash
# scripts/backup-configs.sh

BACKUP_DIR="backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup R2 metadata
aws s3 cp s3://panoconfig360-tiles/clients/ "$BACKUP_DIR/clients/" \
  --recursive \
  --exclude "*.jpg" \
  --include "*.json" \
  --profile r2

# Backup to another region/service (optional)
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
```

### 10.2 Disaster Recovery Plan

**RPO (Recovery Point Objective)**: 24 hours
**RTO (Recovery Time Objective)**: 1 hour

**Recovery procedure**:
1. Deploy backend to Render from Git (5 min)
2. Restore R2 bucket from backup (30 min)
3. Deploy frontend to Cloudflare Pages (5 min)
4. Update DNS if needed (10 min)
5. Test critical paths (10 min)

## Security Checklist

- [ ] Rate limiting enabled (10 req/min for render endpoint)
- [ ] Request size limits configured (10MB max)
- [ ] Authentication implemented (JWT or API key)
- [ ] CORS properly configured (no wildcards)
- [ ] Security headers added (CSP, HSTS, etc.)
- [ ] Input validation on all endpoints
- [ ] Structured logging enabled
- [ ] Error tracking configured (Sentry)
- [ ] Health checks implemented
- [ ] Secrets in environment variables (not code)
- [ ] HTTPS everywhere
- [ ] Cloudflare WAF enabled
- [ ] DDoS protection active
- [ ] Regular security updates scheduled
- [ ] Backup strategy implemented
- [ ] Disaster recovery plan documented

## Next Steps

- [Performance Validation](./DEPLOYMENT_PERFORMANCE.md)
- [End-to-End Testing](./DEPLOYMENT_TESTING.md)
- [Deployment Architecture](./DEPLOYMENT_ARCHITECTURE.md)
