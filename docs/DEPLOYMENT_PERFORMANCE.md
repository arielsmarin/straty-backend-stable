# Performance Validation Guide

## Overview

This guide provides comprehensive performance testing and validation procedures for the Panoconfig360 production deployment.

## Performance Targets

### 1. Cold Start Latency
- **Target**: < 3 seconds
- **Measurement**: Time from first request to healthy response
- **Acceptable**: 3-10 seconds (free/starter tier)
- **Ideal**: < 1 second (standard tier, pre-warmed)

### 2. Tile Streaming Speed
- **Target**: < 50ms per tile (from CDN cache)
- **Acceptable**: < 200ms per tile (from R2 origin)
- **Critical**: < 500ms per tile

### 3. Cache Hit Ratio
- **Target**: > 95% after warm-up
- **Acceptable**: > 85%
- **Critical**: > 70%

### 4. Parallel Tile Loading
- **Target**: 8-12 concurrent connections
- **Metric**: Browser HTTP/2 multiplexing
- **Validation**: Network waterfall shows parallel requests

### 5. Time to First Tile (TTFT)
- **Target**: < 500ms
- **Measurement**: From page load to first tile displayed
- **Includes**: API call + LOD 0 generation + first tile fetch

### 6. Full High-Quality Load Time
- **Target**: 10-30 seconds
- **Measurement**: All LOD 2+ tiles loaded
- **Progressive**: User sees improvement throughout

## Test 1: Cold Start Latency

### 1.1 Manual Test

**Prerequisites**: Service must be completely cold (free tier after inactivity)

```bash
# Wait for service to sleep (free tier: ~15 min inactivity)
# Or restart service in Render dashboard

# Measure cold start
time curl https://api.example.com/health
```

**Expected output**:
```
real    0m2.456s  # <3s is good
user    0m0.012s
sys     0m0.008s
```

### 1.2 Automated Test

Create `tests/performance/test_cold_start.py`:

```python
import time
import requests

def test_cold_start_latency():
    """Test backend cold start time"""
    url = "https://api.example.com/health"
    
    # Measure request time
    start = time.time()
    response = requests.get(url, timeout=30)
    duration = time.time() - start
    
    assert response.status_code == 200, "Health check failed"
    assert duration < 10, f"Cold start took {duration:.2f}s (target: <3s)"
    
    print(f"✅ Cold start: {duration:.2f}s")
```

### 1.3 Keep-Alive Service (Optional)

For free tier, prevent cold starts with external ping:

**UptimeRobot** (free):
```
Monitor: https://api.example.com/health
Interval: 5 minutes
Alert: Email on downtime
```

**Custom cron** (if you have a server):
```bash
# Crontab entry
*/5 * * * * curl -s https://api.example.com/health > /dev/null
```

## Test 2: Render Request Performance

### 2.1 Test Cache Hit (Fast Path)

```bash
# Test existing configuration (should be cached)
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "monte-negro",
    "scene": "living",
    "selection": {
      "floor": "baccarat",
      "wall": "monte-negro"
    }
  }' \
  -w "\nTime: %{time_total}s\n" \
  -s | jq .
```

**Expected**:
```json
{
  "status": "cached",
  "build": "abc123def456",
  "tiles": {...}
}
Time: 0.123s  # <200ms is excellent
```

### 2.2 Test New Render (Slow Path)

```bash
# Test new configuration (will render LOD 0)
curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "client": "test-client",
    "scene": "test-scene",
    "selection": {
      "layer1": "material1",
      "layer2": "material2"
    }
  }' \
  -w "\nTime: %{time_total}s\n" \
  -s | jq .
```

**Expected**:
```
Time: 2.456s  # 1-3s is good for LOD 0 generation
```

### 2.3 Automated Render Performance Test

Create `tests/performance/test_render_performance.py`:

```python
import time
import requests

API_URL = "https://api.example.com"

def test_cached_render_performance():
    """Test render performance for cached configuration"""
    start = time.time()
    response = requests.post(
        f"{API_URL}/api/render",
        json={
            "client": "monte-negro",
            "scene": "living",
            "selection": {"floor": "baccarat"}
        },
        timeout=30
    )
    duration = time.time() - start
    
    assert response.status_code == 200
    assert response.json()["status"] in ["cached", "generated"]
    assert duration < 1.0, f"Cached render took {duration:.2f}s (target: <200ms)"
    
    print(f"✅ Cached render: {duration:.3f}s")

def test_new_render_performance():
    """Test render performance for new configuration"""
    import random
    
    # Generate unique selection to force render
    unique_id = random.randint(1000, 9999)
    
    start = time.time()
    response = requests.post(
        f"{API_URL}/api/render",
        json={
            "client": f"test-{unique_id}",
            "scene": "scene-1",
            "selection": {"layer1": "mat1"}
        },
        timeout=30
    )
    duration = time.time() - start
    
    assert response.status_code == 200
    assert response.json()["status"] == "generated"
    assert duration < 5.0, f"New render took {duration:.2f}s (target: <3s)"
    
    print(f"✅ New render: {duration:.3f}s")
```

## Test 3: Tile Streaming Speed

### 3.1 Test Single Tile Load (CDN)

```bash
# Test tile from CDN
curl -w "@curl-format.txt" -o /dev/null -s \
  https://cdn.example.com/clients/monte-negro/cubemap/living/tiles/abc123/abc123_f_0_0_0.jpg
```

Create `curl-format.txt`:
```
time_namelookup:  %{time_namelookup}s\n
time_connect:     %{time_connect}s\n
time_appconnect:  %{time_appconnect}s\n
time_pretransfer: %{time_pretransfer}s\n
time_starttransfer: %{time_starttransfer}s\n
time_total:       %{time_total}s\n
speed_download:   %{speed_download} bytes/s\n
```

**Expected output**:
```
time_namelookup:  0.012s
time_connect:     0.034s
time_appconnect:  0.067s
time_pretransfer: 0.067s
time_starttransfer: 0.089s  # <100ms is excellent (CDN cache hit)
time_total:       0.145s
speed_download:   345678 bytes/s
```

### 3.2 Test Parallel Tile Loading

Create `tests/performance/test_tile_streaming.py`:

```python
import time
import asyncio
import aiohttp

async def fetch_tile(session, url):
    """Fetch a single tile and measure time"""
    start = time.time()
    async with session.get(url) as response:
        await response.read()
        duration = time.time() - start
        return {
            "url": url,
            "status": response.status,
            "duration": duration,
            "size": len(await response.read()) if response.status == 200 else 0
        }

async def test_parallel_tile_loading():
    """Test loading multiple tiles in parallel"""
    base_url = "https://cdn.example.com/clients/monte-negro/cubemap/living/tiles/abc123"
    
    # Generate tile URLs (6 faces, LOD 0, 1 tile each = 6 tiles)
    tile_urls = [
        f"{base_url}/abc123_{face}_0_0_0.jpg"
        for face in ["f", "b", "l", "r", "u", "d"]
    ]
    
    # Fetch all tiles in parallel
    start = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_tile(session, url) for url in tile_urls]
        results = await asyncio.gather(*tasks)
    total_duration = time.time() - start
    
    # Analyze results
    successful = [r for r in results if r["status"] == 200]
    avg_duration = sum(r["duration"] for r in successful) / len(successful)
    max_duration = max(r["duration"] for r in successful)
    
    print(f"✅ Loaded {len(successful)} tiles in {total_duration:.3f}s")
    print(f"   Average tile time: {avg_duration:.3f}s")
    print(f"   Max tile time: {max_duration:.3f}s")
    print(f"   Parallelization factor: {sum(r['duration'] for r in successful) / total_duration:.2f}x")
    
    assert len(successful) == 6, f"Expected 6 tiles, got {len(successful)}"
    assert avg_duration < 0.2, f"Avg tile time {avg_duration:.3f}s (target: <200ms)"
    assert max_duration < 0.5, f"Max tile time {max_duration:.3f}s (target: <500ms)"

# Run test
asyncio.run(test_parallel_tile_loading())
```

## Test 4: Cache Hit Ratio

### 4.1 Check Cloudflare Analytics

In Cloudflare Dashboard:
1. Go to **Analytics & Logs** → **Traffic**
2. Select **Caching** tab
3. Check **Cache Hit Ratio** graph

**Target**: >95% after warm-up period

### 4.2 Test Cache Headers

```bash
# First request (cache miss)
curl -I https://cdn.example.com/clients/monte-negro/cubemap/living/tiles/abc123/abc123_f_0_0_0.jpg

# Expected headers:
# cf-cache-status: MISS
# cache-control: public, max-age=31536000, immutable

# Second request (cache hit)
curl -I https://cdn.example.com/clients/monte-negro/cubemap/living/tiles/abc123/abc123_f_0_0_0.jpg

# Expected headers:
# cf-cache-status: HIT
# age: 5  # Seconds since cached
```

### 4.3 Automated Cache Test

```python
import requests
import time

def test_cdn_caching():
    """Test CDN cache behavior"""
    tile_url = "https://cdn.example.com/clients/test/tiles/test_f_0_0_0.jpg"
    
    # First request (likely MISS)
    response1 = requests.get(tile_url)
    cache_status1 = response1.headers.get("cf-cache-status", "UNKNOWN")
    
    # Wait a moment
    time.sleep(0.5)
    
    # Second request (should be HIT)
    response2 = requests.get(tile_url)
    cache_status2 = response2.headers.get("cf-cache-status", "UNKNOWN")
    
    print(f"First request: {cache_status1}")
    print(f"Second request: {cache_status2}")
    
    # On second request, we should see either HIT or REVALIDATED
    assert cache_status2 in ["HIT", "REVALIDATED", "UPDATING"], \
        f"Expected cache hit, got {cache_status2}"
    
    print("✅ CDN caching working correctly")
```

## Test 5: Full Page Load Performance

### 5.1 Browser DevTools Analysis

1. Open https://app.example.com in Chrome
2. Open DevTools (F12) → **Network** tab
3. Disable cache (for fresh test)
4. Reload page and trigger render
5. Analyze waterfall

**Key metrics**:
- DOMContentLoaded: <2s
- Load event: <5s (before tile streaming)
- First tile visible: <1s
- All LOD 0 tiles: <5s
- All LOD 2 tiles: <30s

### 5.2 Lighthouse Performance Test

```bash
# Install Lighthouse
npm install -g lighthouse

# Run test
lighthouse https://app.example.com \
  --output html \
  --output-path ./reports/lighthouse-report.html \
  --only-categories=performance \
  --chrome-flags="--headless"
```

**Target scores**:
- Performance: >90
- First Contentful Paint: <1.5s
- Largest Contentful Paint: <2.5s
- Total Blocking Time: <300ms
- Cumulative Layout Shift: <0.1

### 5.3 WebPageTest

Use [WebPageTest](https://www.webpagetest.org/):

1. Enter URL: https://app.example.com
2. Select test location: Multiple locations worldwide
3. Run test
4. Analyze:
   - First Byte Time: <200ms
   - Start Render: <1s
   - Speed Index: <2s
   - Fully Loaded: <5s (excluding progressive tiles)

## Test 6: Load Testing (Stress Test)

### 6.1 Install Load Testing Tool

```bash
# Option 1: k6 (recommended)
brew install k6  # macOS
# or
sudo apt-get install k6  # Ubuntu

# Option 2: Apache Bench
sudo apt-get install apache2-utils
```

### 6.2 Create Load Test Script

Create `tests/load/render_load_test.js`:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '30s', target: 10 },  // Ramp up to 10 users
    { duration: '1m', target: 10 },   // Stay at 10 users
    { duration: '30s', target: 50 },  // Spike to 50 users
    { duration: '1m', target: 50 },   // Stay at 50 users
    { duration: '30s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],  // 95% of requests < 5s
    http_req_failed: ['rate<0.1'],      // <10% failed requests
  },
};

export default function () {
  const url = 'https://api.example.com/api/render';
  const payload = JSON.stringify({
    client: 'test-client',
    scene: 'test-scene',
    selection: { layer1: 'mat1' },
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const response = http.post(url, payload, params);

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 5s': (r) => r.timings.duration < 5000,
    'has build': (r) => JSON.parse(r.body).build !== undefined,
  });

  sleep(1);  // Think time between requests
}
```

### 6.3 Run Load Test

```bash
k6 run tests/load/render_load_test.js
```

**Expected output**:
```
checks.........................: 100.00% ✓ 3000  ✗ 0
data_received..................: 1.5 MB  25 kB/s
data_sent......................: 450 kB  7.5 kB/s
http_req_duration..............: avg=2.1s   min=150ms  p(95)=4.2s
http_req_failed................: 0.00%   ✓ 0     ✗ 1000
http_reqs......................: 1000    16.67/s
```

### 6.4 CDN Load Test

Test CDN with parallel tile requests:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export let options = {
  vus: 50,  // 50 concurrent users
  duration: '1m',
};

const tiles = [
  'https://cdn.example.com/clients/test/tiles/abc_f_0_0_0.jpg',
  'https://cdn.example.com/clients/test/tiles/abc_b_0_0_0.jpg',
  'https://cdn.example.com/clients/test/tiles/abc_l_0_0_0.jpg',
  'https://cdn.example.com/clients/test/tiles/abc_r_0_0_0.jpg',
  'https://cdn.example.com/clients/test/tiles/abc_u_0_0_0.jpg',
  'https://cdn.example.com/clients/test/tiles/abc_d_0_0_0.jpg',
];

export default function () {
  const responses = http.batch(tiles.map(url => ['GET', url]));
  
  responses.forEach((response) => {
    check(response, {
      'status is 200': (r) => r.status === 200,
      'from cache': (r) => r.headers['Cf-Cache-Status'] === 'HIT',
      'fast response': (r) => r.timings.duration < 100,
    });
  });
}
```

## Test 7: Geographic Performance

### 7.1 Multi-Region Testing

Use external service to test from different locations:

**Pingdom** (free tier):
```
Test from:
- North America (New York)
- Europe (London)
- Asia (Tokyo)
- South America (São Paulo)
- Australia (Sydney)
```

**Expected**:
- North America: <100ms (if Render is in Oregon)
- Europe: 150-200ms
- Asia: 200-300ms

### 7.2 CDN Geographic Performance

CDN should be fast from all locations:

```bash
# Test from multiple locations using online tools
# Or use curl from different regions

curl -w "Time: %{time_total}s\n" \
  https://cdn.example.com/clients/test/tiles/test_f_0_0_0.jpg
```

**Expected from any location**: <200ms (Cloudflare has 200+ POPs)

## Test 8: Progressive Loading

### 8.1 Visual Test

1. Open app in browser with Network throttling:
   - DevTools → Network → Throttling → "Fast 3G"
2. Trigger render
3. Observe progressive loading:
   - LOD 0 appears first (blurry but visible)
   - LOD 1 gradually replaces tiles
   - LOD 2 loads for high quality

**Expected**:
- First visible tile: <2s on 3G
- Smooth progressive enhancement
- No visual "pop" or jarring transitions

### 8.2 Automated Progressive Loading Test

```python
import asyncio
import aiohttp
import time

async def test_progressive_loading():
    """Test progressive loading of LOD levels"""
    base_url = "https://api.example.com"
    cdn_url = "https://cdn.example.com"
    
    # Start render
    async with aiohttp.ClientSession() as session:
        # Request render
        start = time.time()
        async with session.post(
            f"{base_url}/api/render",
            json={
                "client": "test",
                "scene": "scene1",
                "selection": {"layer1": "mat1"}
            }
        ) as response:
            render_data = await response.json()
            render_time = time.time() - start
        
        tile_root = render_data["tiles"]["tileRoot"]
        build = render_data["tiles"]["build"]
        
        # Test LOD 0 availability (should be immediate)
        lod0_url = f"{cdn_url}/{tile_root}/{build}_f_0_0_0.jpg"
        async with session.get(lod0_url) as response:
            assert response.status == 200, "LOD 0 not immediately available"
            lod0_time = time.time() - start
        
        # Poll for LOD 1 tiles
        cursor = 0
        lod1_found = False
        for _ in range(10):  # Poll for up to 10 seconds
            async with session.get(
                f"{base_url}/api/render/events",
                params={"tile_root": tile_root, "cursor": cursor}
            ) as response:
                events_data = await response.json()
                events = events_data["data"]["events"]
                
                # Check if any LOD 1 tiles are ready
                for event in events:
                    if event["lod"] == 1 and event["state"] == "visible":
                        lod1_found = True
                        lod1_time = time.time() - start
                        break
                
                if lod1_found:
                    break
                
                cursor = events_data["data"]["cursor"]
                await asyncio.sleep(1)
        
        print(f"✅ Render request: {render_time:.2f}s")
        print(f"✅ LOD 0 available: {lod0_time:.2f}s")
        if lod1_found:
            print(f"✅ LOD 1 tiles: {lod1_time:.2f}s")
        
        assert render_time < 5, f"Render took too long: {render_time:.2f}s"
        assert lod0_time < 5, f"LOD 0 took too long: {lod0_time:.2f}s"

asyncio.run(test_progressive_loading())
```

## Performance Monitoring Dashboard

### Create Performance Summary Script

Create `scripts/performance_summary.py`:

```python
import requests
import json
from datetime import datetime

def test_all_metrics():
    """Run all performance tests and create summary"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": []
    }
    
    # Test 1: Health check (cold start proxy)
    try:
        import time
        start = time.time()
        response = requests.get("https://api.example.com/health", timeout=30)
        duration = time.time() - start
        results["tests"].append({
            "name": "Health Check",
            "duration_ms": round(duration * 1000, 2),
            "status": "✅" if response.status_code == 200 else "❌",
            "target_ms": 3000,
        })
    except Exception as e:
        results["tests"].append({
            "name": "Health Check",
            "status": "❌",
            "error": str(e)
        })
    
    # Test 2: Cached render
    try:
        start = time.time()
        response = requests.post(
            "https://api.example.com/api/render",
            json={"client": "test", "scene": "test", "selection": {}},
            timeout=30
        )
        duration = time.time() - start
        results["tests"].append({
            "name": "Cached Render",
            "duration_ms": round(duration * 1000, 2),
            "status": "✅" if duration < 1.0 else "⚠️",
            "target_ms": 200,
        })
    except Exception as e:
        results["tests"].append({
            "name": "Cached Render",
            "status": "❌",
            "error": str(e)
        })
    
    # Test 3: CDN tile fetch
    try:
        start = time.time()
        response = requests.get(
            "https://cdn.example.com/test.jpg",
            timeout=10
        )
        duration = time.time() - start
        cache_status = response.headers.get("cf-cache-status", "UNKNOWN")
        results["tests"].append({
            "name": "CDN Tile Fetch",
            "duration_ms": round(duration * 1000, 2),
            "cache_status": cache_status,
            "status": "✅" if duration < 0.2 else "⚠️",
            "target_ms": 50,
        })
    except Exception as e:
        results["tests"].append({
            "name": "CDN Tile Fetch",
            "status": "❌",
            "error": str(e)
        })
    
    # Print summary
    print("\n" + "="*60)
    print("PERFORMANCE SUMMARY")
    print("="*60)
    print(f"Timestamp: {results['timestamp']}\n")
    
    for test in results["tests"]:
        print(f"{test['status']} {test['name']}")
        if "duration_ms" in test:
            print(f"   Duration: {test['duration_ms']}ms (target: {test.get('target_ms', 'N/A')}ms)")
        if "cache_status" in test:
            print(f"   Cache: {test['cache_status']}")
        if "error" in test:
            print(f"   Error: {test['error']}")
        print()
    
    # Save results
    with open("performance_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("Results saved to performance_results.json")

if __name__ == "__main__":
    test_all_metrics()
```

## Performance Checklist

- [ ] Cold start < 3s (measured)
- [ ] Cached render < 200ms (measured)
- [ ] New render < 3s for LOD 0 (measured)
- [ ] Tile fetch < 50ms from CDN (measured)
- [ ] Cache hit ratio > 95% (from Cloudflare Analytics)
- [ ] Parallel loading working (8-12 concurrent, visual check)
- [ ] Progressive loading smooth (visual check)
- [ ] Lighthouse score > 90 (measured)
- [ ] Load test passes (50 concurrent users, <10% errors)
- [ ] Geographic performance acceptable (all regions <300ms)
- [ ] No memory leaks (monitor Render metrics over 24h)
- [ ] No rate limit issues under normal load

## Next Steps

- [End-to-End Testing Guide](./DEPLOYMENT_TESTING.md)
- [Production Hardening](./DEPLOYMENT_HARDENING.md)
- [Deployment Architecture](./DEPLOYMENT_ARCHITECTURE.md)
