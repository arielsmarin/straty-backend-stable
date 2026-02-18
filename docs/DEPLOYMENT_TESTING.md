# End-to-End Testing Guide

## Overview

This guide provides comprehensive end-to-end testing procedures for validating the complete Panoconfig360 deployment in the production Cloudflare environment.

## Test Environment Setup

### Prerequisites

- [ ] Backend deployed to Render.com
- [ ] Frontend deployed to Cloudflare Pages
- [ ] R2 bucket configured and accessible
- [ ] Custom domains configured (api.example.com, app.example.com, cdn.example.com)
- [ ] SSL certificates active
- [ ] CORS configured
- [ ] Test client data uploaded to R2

### Test Data Preparation

Create test configuration in R2:

```bash
# Upload test client configuration
aws s3 cp test_data/clients/test-client/config.json \
  s3://panoconfig360-tiles/clients/test-client/config.json \
  --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
  --profile r2

# Upload test catalog
aws s3 cp test_data/catalog/test-client_catalog.json \
  s3://panoconfig360-tiles/catalog/test-client_catalog.json \
  --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
  --profile r2
```

## Test Suite 1: Infrastructure Tests

### Test 1.1: DNS Resolution

```bash
# Test DNS resolution for all domains
dig api.example.com
dig app.example.com
dig cdn.example.com
```

**Expected**:
```
api.example.com.    300    IN    CNAME    panoconfig360-api.onrender.com.
app.example.com.    300    IN    CNAME    panoconfig360-app.pages.dev.
cdn.example.com.    300    IN    CNAME    panoconfig360-tiles.ACCOUNT_ID.r2.cloudflarestorage.com.
```

### Test 1.2: SSL/TLS Certificates

```bash
# Check SSL certificates
echo | openssl s_client -servername api.example.com -connect api.example.com:443 2>/dev/null | openssl x509 -noout -dates

echo | openssl s_client -servername app.example.com -connect app.example.com:443 2>/dev/null | openssl x509 -noout -dates

echo | openssl s_client -servername cdn.example.com -connect cdn.example.com:443 2>/dev/null | openssl x509 -noout -dates
```

**Expected**: Valid certificates, not expired, issued by Let's Encrypt

### Test 1.3: HTTP to HTTPS Redirect

```bash
# Test HTTP redirects to HTTPS
curl -I http://api.example.com/health
curl -I http://app.example.com
curl -I http://cdn.example.com
```

**Expected**: 301/302 redirect to https://

### Test 1.4: Security Headers

```bash
# Check security headers on frontend
curl -I https://app.example.com
```

**Expected headers**:
```
strict-transport-security: max-age=31536000; includeSubDomains
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
```

## Test Suite 2: Backend API Tests

### Test 2.1: Health Check

```bash
curl https://api.example.com/health | jq .
```

**Expected**:
```json
{
  "status": "healthy",
  "service": "panoconfig360-api",
  "version": "1.0.0",
  "timestamp": 1234567890,
  "storage": "healthy"
}
```

### Test 2.2: API Documentation

Open in browser:
```
https://api.example.com/docs
```

**Expected**: FastAPI Swagger UI loads with all endpoints documented

### Test 2.3: CORS Preflight

```bash
curl -X OPTIONS https://api.example.com/api/render \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -v
```

**Expected headers**:
```
< access-control-allow-origin: https://app.example.com
< access-control-allow-methods: GET, POST, PUT, DELETE, OPTIONS
< access-control-allow-headers: *
```

### Test 2.4: Render Endpoint (New Configuration)

```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -H "Origin: https://app.example.com" \
  -d '{
    "client": "test-client",
    "scene": "test-scene",
    "selection": {
      "layer1": "material1"
    }
  }' | jq .
```

**Expected response**:
```json
{
  "status": "generated",
  "build": "abc123def456",
  "tiles": {
    "baseUrl": "https://cdn.example.com",
    "tileRoot": "clients/test-client/cubemap/test-scene/tiles/abc123def456",
    "pattern": "abc123def456_{f}_{z}_{x}_{y}.jpg",
    "build": "abc123def456"
  },
  "metadata": {
    "levels": [
      {"tileSize": 512, "size": 512},
      {"tileSize": 512, "size": 1024},
      {"tileSize": 512, "size": 2048}
    ]
  }
}
```

### Test 2.5: Render Endpoint (Cached)

```bash
# Run same request again
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "test-client",
    "scene": "test-scene",
    "selection": {
      "layer1": "material1"
    }
  }' | jq .
```

**Expected**: Same response, but faster (<200ms), status might be "cached"

### Test 2.6: Events Endpoint

```bash
# Poll for tile events
curl "https://api.example.com/api/render/events?tile_root=clients/test-client/cubemap/test-scene/tiles/abc123def456&cursor=0&limit=50" | jq .
```

**Expected response**:
```json
{
  "status": "success",
  "data": {
    "events": [
      {
        "filename": "abc123def456_f_0_0_0.jpg",
        "build": "abc123def456",
        "state": "visible",
        "lod": 0,
        "ts": 1234567890000
      }
    ],
    "cursor": 1,
    "hasMore": false,
    "completed": false
  }
}
```

### Test 2.7: Rate Limiting

```bash
# Send rapid requests to trigger rate limit
for i in {1..15}; do
  curl -X POST https://api.example.com/api/render \
    -H "Content-Type: application/json" \
    -d '{"client":"test","scene":"test","selection":{}}' \
    -w "\nStatus: %{http_code}\n" \
    -s -o /dev/null
done
```

**Expected**: First 10 succeed (200), next 5 return 429 (rate limited)

## Test Suite 3: Storage (R2) Tests

### Test 3.1: R2 Bucket Accessibility

```bash
# Test public read access
curl -I https://cdn.example.com/clients/test-client/config.json
```

**Expected**: 200 OK

### Test 3.2: CORS on R2

```bash
# Test CORS headers from CDN
curl -H "Origin: https://app.example.com" \
  https://cdn.example.com/clients/test-client/cubemap/test-scene/tiles/abc123/abc123_f_0_0_0.jpg \
  -I
```

**Expected headers**:
```
access-control-allow-origin: *
access-control-allow-methods: GET, HEAD
```

### Test 3.3: Tile Upload and Retrieval

After render, verify tiles are in R2:

```bash
# List tiles
aws s3 ls s3://panoconfig360-tiles/clients/test-client/cubemap/test-scene/tiles/abc123/ \
  --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
  --profile r2
```

**Expected**: List of .jpg files and metadata.json

### Test 3.4: CDN Caching

```bash
# First request (cache miss)
curl -I https://cdn.example.com/clients/test/tiles/test_f_0_0_0.jpg

# Second request (cache hit)
curl -I https://cdn.example.com/clients/test/tiles/test_f_0_0_0.jpg
```

**Expected**:
- First: `cf-cache-status: MISS`
- Second: `cf-cache-status: HIT`

## Test Suite 4: Frontend Tests

### Test 4.1: Frontend Page Load

Open in browser:
```
https://app.example.com
```

**Expected**:
- Page loads within 2 seconds
- No console errors
- UI elements visible
- Marzipano viewer initializes

### Test 4.2: Frontend Asset Loading

Check Network tab in DevTools:

**Expected**:
- All CSS files load (200 OK)
- All JS files load (200 OK)
- No 404 errors
- Assets served from Cloudflare CDN

### Test 4.3: API Communication from Frontend

1. Open browser console
2. Run:

```javascript
// Test API health from frontend
fetch('https://api.example.com/health')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error);
```

**Expected**: No CORS errors, health data returned

### Test 4.4: Configuration Loading

```javascript
// Test config loading from R2
fetch('https://cdn.example.com/clients/test-client/config.json')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error);
```

**Expected**: Config JSON loads without CORS errors

## Test Suite 5: Complete User Flow Tests

### Test 5.1: Complete Render Flow

**Manual test procedure**:

1. Open https://app.example.com
2. Select a client configuration
3. Select materials for each layer
4. Click "Render" button
5. Observe progressive loading:
   - Spinner appears
   - Low-quality panorama appears (~2-3s)
   - Quality gradually improves
   - High-quality panorama fully loaded (~15-30s)

**Validation checkpoints**:
- [ ] No JavaScript errors in console
- [ ] No CORS errors
- [ ] API call succeeds
- [ ] Tiles load progressively
- [ ] No broken images
- [ ] Pan/zoom works smoothly
- [ ] Transitions are smooth

### Test 5.2: Material Selection Flow

1. Open app
2. Select different materials
3. Render each combination
4. Verify:
   - [ ] Build string changes for different selections
   - [ ] Same selection returns same build (cache)
   - [ ] Tiles load correctly for each selection

### Test 5.3: Scene Navigation

1. Open app
2. Switch between scenes
3. Verify:
   - [ ] Each scene loads correctly
   - [ ] Tiles are specific to each scene
   - [ ] No cross-contamination between scenes

### Test 5.4: Multi-User Concurrent Access

**Test with multiple browser windows/users**:

1. Open app in 3 different browsers
2. Trigger renders simultaneously
3. Verify:
   - [ ] All renders complete successfully
   - [ ] No conflicts or errors
   - [ ] Rate limiting doesn't block legitimate users
   - [ ] Each user sees their own render

## Test Suite 6: Error Handling Tests

### Test 6.1: Invalid Client ID

```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "nonexistent-client",
    "scene": "test-scene",
    "selection": {}
  }'
```

**Expected**: 404 or 400 with clear error message

### Test 6.2: Invalid Scene ID

```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "test-client",
    "scene": "nonexistent-scene",
    "selection": {}
  }'
```

**Expected**: 404 or 400 with clear error message

### Test 6.3: Missing Required Fields

```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "test-client"
  }'
```

**Expected**: 422 Validation error

### Test 6.4: Tile 404 Handling

```bash
curl -I https://cdn.example.com/clients/test/tiles/nonexistent_f_0_0_0.jpg
```

**Expected**: 404 Not Found

### Test 6.5: Backend Downtime

1. Stop Render service temporarily
2. Open frontend
3. Try to render

**Expected**:
- Clear error message to user
- No white screen of death
- Graceful degradation

## Test Suite 7: Performance Tests

### Test 7.1: Page Load Performance

```bash
lighthouse https://app.example.com \
  --only-categories=performance \
  --output=json \
  --output-path=./performance-report.json
```

**Expected scores**:
- Performance: >90
- First Contentful Paint: <1.5s
- Largest Contentful Paint: <2.5s

### Test 7.2: API Response Times

```bash
# Average 10 cached requests
for i in {1..10}; do
  curl -X POST https://api.example.com/api/render \
    -H "Content-Type: application/json" \
    -d '{"client":"test","scene":"test","selection":{}}' \
    -w "\nTime: %{time_total}s\n" \
    -s -o /dev/null
done | grep "Time:" | awk '{sum+=$2; count++} END {print "Average:", sum/count, "s"}'
```

**Expected average**: <0.2s

### Test 7.3: Tile Loading Performance

Use browser DevTools Network tab:
- Load a panorama
- Check tile loading times
- Verify parallel loading (multiple tiles at once)

**Expected**:
- Tiles load in parallel (8-12 concurrent)
- Each tile <100ms from CDN
- No request queuing

## Test Suite 8: Security Tests

### Test 8.1: SQL Injection Attempt

```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "test'\''; DROP TABLE users; --",
    "scene": "test",
    "selection": {}
  }'
```

**Expected**: 400/422 validation error, no SQL execution

### Test 8.2: XSS Attempt

```bash
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "<script>alert(1)</script>",
    "scene": "test",
    "selection": {}
  }'
```

**Expected**: Input sanitized or rejected

### Test 8.3: Path Traversal Attempt

```bash
curl https://cdn.example.com/clients/../../etc/passwd
```

**Expected**: 403/404, no file access

### Test 8.4: CORS Security

```bash
# Try request from disallowed origin
curl -X POST https://api.example.com/api/render \
  -H "Origin: https://malicious-site.com" \
  -H "Content-Type: application/json" \
  -d '{"client":"test","scene":"test","selection":{}}'
```

**Expected**: Request blocked or CORS headers not present

## Test Suite 9: Mobile/Responsive Tests

### Test 9.1: Mobile Browser Test

Open on mobile devices:
- iOS Safari
- Android Chrome
- Mobile Firefox

**Expected**:
- Responsive layout
- Touch controls work
- Panorama viewer works
- No horizontal scroll
- Performance acceptable

### Test 9.2: Network Throttling Test

1. Open DevTools
2. Set Network: Slow 3G
3. Load panorama

**Expected**:
- Progressive loading works
- Low-quality appears quickly
- No timeout errors

## Test Suite 10: Monitoring & Logging Tests

### Test 10.1: Verify Logs

Check Render logs:
```
Render Dashboard → Service → Logs
```

**Expected log entries**:
- Request logging working
- No unexpected errors
- Structured JSON logs (if configured)

### Test 10.2: Verify Metrics

Check Render metrics:
```
Render Dashboard → Service → Metrics
```

**Expected**:
- CPU usage <70%
- Memory usage <80%
- Response times consistent
- No error spikes

### Test 10.3: Verify Cloudflare Analytics

Check Cloudflare Analytics:
```
Cloudflare Dashboard → Analytics
```

**Expected**:
- Traffic visible
- Cache hit ratio >90%
- No error spikes
- Geographic distribution matches expectations

## Automated Test Suite

Create `tests/e2e/test_full_flow.py`:

```python
import pytest
import requests
import time

BASE_URL = "https://api.example.com"
CDN_URL = "https://cdn.example.com"
APP_URL = "https://app.example.com"

class TestE2E:
    def test_1_health_check(self):
        """Test backend health"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_2_render_new(self):
        """Test rendering new configuration"""
        response = requests.post(
            f"{BASE_URL}/api/render",
            json={
                "client": "test-client",
                "scene": "test-scene",
                "selection": {"layer1": "mat1"}
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "build" in data
        assert data["status"] in ["generated", "cached"]
        return data
    
    def test_3_tiles_accessible(self):
        """Test tiles are accessible from CDN"""
        # First render to get tile URLs
        render_data = self.test_2_render_new()
        tile_root = render_data["tiles"]["tileRoot"]
        build = render_data["tiles"]["build"]
        
        # Try to fetch a tile
        tile_url = f"{CDN_URL}/{tile_root}/{build}_f_0_0_0.jpg"
        response = requests.get(tile_url, timeout=10)
        assert response.status_code == 200
        assert response.headers.get("content-type") == "image/jpeg"
    
    def test_4_events_polling(self):
        """Test event polling works"""
        render_data = self.test_2_render_new()
        tile_root = render_data["tiles"]["tileRoot"]
        
        response = requests.get(
            f"{BASE_URL}/api/render/events",
            params={"tile_root": tile_root, "cursor": 0},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data["data"]
    
    def test_5_cors_headers(self):
        """Test CORS headers are present"""
        response = requests.post(
            f"{BASE_URL}/api/render",
            json={"client": "test", "scene": "test", "selection": {}},
            headers={"Origin": APP_URL}
        )
        assert "access-control-allow-origin" in response.headers
    
    def test_6_rate_limiting(self):
        """Test rate limiting is active"""
        # Send many requests rapidly
        success_count = 0
        rate_limited_count = 0
        
        for _ in range(15):
            response = requests.post(
                f"{BASE_URL}/api/render",
                json={"client": "test", "scene": "test", "selection": {}},
                timeout=5
            )
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                rate_limited_count += 1
        
        # Should have some rate limiting
        assert rate_limited_count > 0, "Rate limiting not working"
        print(f"Rate limit test: {success_count} succeeded, {rate_limited_count} rate limited")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

Run automated tests:
```bash
pip install pytest requests
pytest tests/e2e/test_full_flow.py -v
```

## Test Execution Checklist

### Pre-Deployment
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Code review completed
- [ ] Security scan completed (CodeQL)

### Post-Deployment (Staging/Preview)
- [ ] Infrastructure tests pass
- [ ] Backend API tests pass
- [ ] Storage tests pass
- [ ] Frontend loads correctly
- [ ] User flow tests pass
- [ ] Performance benchmarks meet targets

### Production Validation
- [ ] All test suites executed
- [ ] Performance validation complete
- [ ] Security tests pass
- [ ] Mobile/responsive tests pass
- [ ] Monitoring and logging verified
- [ ] Load testing complete
- [ ] Geographic performance validated

### Ongoing Monitoring
- [ ] Daily health checks
- [ ] Weekly performance reviews
- [ ] Monthly security audits
- [ ] Quarterly disaster recovery drills

## Troubleshooting Common Issues

### Issue: CORS errors
**Solution**: Verify CORS_ORIGINS in Render includes frontend domain

### Issue: Tiles don't load
**Solution**: Check R2 public access, CDN configuration, tile URLs

### Issue: Slow performance
**Solution**: Check CDN cache hit ratio, R2 region, Render instance size

### Issue: Rate limiting too aggressive
**Solution**: Adjust RATE_LIMIT_REQUESTS in environment variables

### Issue: 500 errors
**Solution**: Check Render logs, verify R2 credentials, check storage quota

## Success Criteria

All tests must pass before considering deployment successful:

- ✅ Infrastructure: DNS, SSL, redirects working
- ✅ Backend: All endpoints functional, CORS configured
- ✅ Storage: R2 accessible, tiles uploadable/downloadable
- ✅ Frontend: Page loads, assets load, no console errors
- ✅ User Flow: Complete render flow works end-to-end
- ✅ Performance: Meets all targets (<3s cold start, <50ms tiles)
- ✅ Security: All security tests pass, no vulnerabilities
- ✅ Mobile: Works on mobile devices
- ✅ Monitoring: Logs and metrics visible

## Next Steps

- [Performance Validation](./DEPLOYMENT_PERFORMANCE.md)
- [Production Hardening](./DEPLOYMENT_HARDENING.md)
- [Deployment Architecture](./DEPLOYMENT_ARCHITECTURE.md)
