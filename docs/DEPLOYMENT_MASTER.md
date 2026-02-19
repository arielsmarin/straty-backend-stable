# Production Deployment Master Guide

## Overview

This is the **master deployment guide** that provides a step-by-step workflow for deploying Panoconfig360 to production using Render.com (backend), Cloudflare Pages (frontend), and Cloudflare R2 (storage).

**Target Architecture**: Serverless, globally distributed, cost-optimized

**Estimated Setup Time**: 2-3 hours (first time)

**Estimated Monthly Cost**: $8-$30 depending on traffic

## Quick Navigation

- **Architecture Overview**: [DEPLOYMENT_ARCHITECTURE.md](./DEPLOYMENT_ARCHITECTURE.md)
- **Backend Setup**: [DEPLOYMENT_RENDER.md](./DEPLOYMENT_RENDER.md)
- **Storage Setup**: [DEPLOYMENT_R2.md](./DEPLOYMENT_R2.md)
- **Frontend Setup**: [DEPLOYMENT_CLOUDFLARE_PAGES.md](./DEPLOYMENT_CLOUDFLARE_PAGES.md)
- **CORS Configuration**: [DEPLOYMENT_CORS.md](./DEPLOYMENT_CORS.md)
- **Security**: [DEPLOYMENT_HARDENING.md](./DEPLOYMENT_HARDENING.md)
- **Performance**: [DEPLOYMENT_PERFORMANCE.md](./DEPLOYMENT_PERFORMANCE.md)
- **Testing**: [DEPLOYMENT_TESTING.md](./DEPLOYMENT_TESTING.md)

## Prerequisites

### Accounts Required
- [ ] GitHub account (for code repository)
- [ ] Cloudflare account (free tier OK)
- [ ] Render.com account (free tier OK for testing)

### Domain Names (Optional but Recommended)
- [ ] Custom domain for frontend: `app.example.com`
- [ ] Custom domain for API: `api.example.com`
- [ ] Custom domain for CDN: `cdn.example.com`

### Tools Required
- [ ] Git
- [ ] Python 3.11+
- [ ] Node.js 18+ (for testing tools)
- [ ] AWS CLI (for R2 configuration)

## Deployment Workflow

### Phase 1: Preparation (30 minutes)

#### 1.1 Review Architecture
Read: [DEPLOYMENT_ARCHITECTURE.md](./DEPLOYMENT_ARCHITECTURE.md)

**Key decisions**:
- Render plan: Free (testing), Starter ($7/month), or Standard ($25/month)?
- Custom domains: Yes or use default subdomains?
- Authentication: Public or JWT/API key protected?

#### 1.2 Clone and Prepare Repository

```bash
# Clone repository
git clone https://github.com/your-username/panoconfig360_totem.git
cd panoconfig360_totem

# Create .env file from example
cp .env.example .env

# Edit .env with your values (for local testing)
nano .env
```

#### 1.3 Test Locally

```bash
# Install dependencies
cd panoconfig360_backend
pip install -r requirements.txt

# Run backend
uvicorn panoconfig360_backend.api.server:app --reload

# Test in browser
# http://localhost:8000/docs
```

### Phase 2: Storage Setup (30 minutes)

Follow: [DEPLOYMENT_R2.md](./DEPLOYMENT_R2.md)

#### 2.1 Create R2 Bucket

1. Log in to Cloudflare Dashboard
2. Navigate to R2
3. Create bucket: `panoconfig360-tiles`
4. Note the bucket name and region

#### 2.2 Generate R2 API Credentials

1. Go to R2 → Manage R2 API Tokens
2. Create token with read/write permissions
3. Save credentials:
   - Access Key ID
   - Secret Access Key
   - Account ID

#### 2.3 Configure R2 CORS

```bash
# Set environment variables
export R2_ACCOUNT_ID=your_account_id
export R2_BUCKET_NAME=panoconfig360-tiles
export FRONTEND_DOMAIN=https://app.example.com

# Run CORS configuration script
./scripts/configure-r2-cors.sh
```

#### 2.4 Test R2 Access

```bash
# Set credentials
export STORAGE_BACKEND=r2
export R2_ACCESS_KEY_ID=your_key
export R2_SECRET_ACCESS_KEY=your_secret

# Test upload (Python)
python3 << EOF
from panoconfig360_backend.storage.storage_r2 import upload_file, exists
import tempfile

with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
    f.write('test')
    upload_file(f.name, 'test/hello.txt', 'text/plain')

print(f"Exists: {exists('test/hello.txt')}")
EOF
```

### Phase 3: Backend Deployment (30 minutes)

Follow: [DEPLOYMENT_RENDER.md](./DEPLOYMENT_RENDER.md)

#### 3.1 Push Code to GitHub

```bash
git add .
git commit -m "Prepare for production deployment"
git push origin main
```

#### 3.2 Create Render Service

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. New → Web Service
3. Connect GitHub repository
4. Use `render.yaml` blueprint (auto-detected)

**Or manually configure**:
- Name: `panoconfig360-api`
- Build Command: `pip install -r panoconfig360_backend/requirements.txt`
- Start Command: `uvicorn panoconfig360_backend.api.server:app --host 0.0.0.0 --port $PORT --workers 2`
- Plan: Starter ($7/month recommended)

#### 3.3 Configure Environment Variables

In Render dashboard, add environment variables:

```bash
STORAGE_BACKEND=r2
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET_NAME=panoconfig360-tiles
R2_ENDPOINT_URL=https://your_account_id.r2.cloudflarestorage.com
R2_PUBLIC_URL=https://cdn.example.com
CORS_ORIGINS=https://app.example.com,https://*.pages.dev
LOG_LEVEL=INFO
ENVIRONMENT=production
```

#### 3.4 Deploy and Test

1. Click "Manual Deploy" → "Deploy latest commit"
2. Wait for deployment (~3-5 minutes)
3. Test health endpoint:

```bash
curl https://panoconfig360-api.onrender.com/health
```

Expected:
```json
{"status": "healthy", "service": "panoconfig360-api"}
```

#### 3.5 Configure Custom Domain (Optional)

1. Render → Settings → Custom Domain
2. Add: `api.example.com`
3. Update DNS (CNAME): `api.example.com` → `panoconfig360-api.onrender.com`
4. Wait for SSL certificate (~10 min)

### Phase 4: Frontend Deployment (20 minutes)

Follow: [DEPLOYMENT_CLOUDFLARE_PAGES.md](./DEPLOYMENT_CLOUDFLARE_PAGES.md)

#### 4.1 Prepare Frontend Configuration

Update `panoconfig360_frontend/js/config/environment.js`:

```javascript
const ENV = {
  isProd: window.location.hostname !== 'localhost',
  apiBaseUrl: window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://api.example.com',  // Your backend URL
  cdnBaseUrl: window.location.hostname === 'localhost'
    ? 'http://localhost:8000/panoconfig360_cache'
    : 'https://cdn.example.com',  // Your R2 custom domain
};
```

Commit and push:
```bash
git add panoconfig360_frontend/js/config/environment.js
git commit -m "Configure production URLs"
git push origin main
```

#### 4.2 Create Cloudflare Pages Project

1. Cloudflare Dashboard → Workers & Pages → Pages
2. Create application → Connect to Git
3. Select repository
4. Configure:
   - Project name: `panoconfig360-app`
   - Build output directory: `panoconfig360_frontend`
   - Build command: *(empty)*

#### 4.3 Deploy

1. Click "Save and Deploy"
2. Wait for deployment (~1 minute)
3. Test: `https://panoconfig360-app.pages.dev`

#### 4.4 Configure Custom Domain

1. Pages project → Custom domains
2. Add: `app.example.com`
3. Cloudflare automatically configures DNS
4. Wait for SSL certificate (~5 min)

### Phase 5: CDN Configuration (15 minutes)

#### 5.1 Enable R2 Public Access

1. R2 → Buckets → panoconfig360-tiles
2. Settings → Public access → Allow Access
3. Copy R2.dev URL or add custom domain

#### 5.2 Add Custom Domain to R2

1. R2 bucket → Settings → Custom domains
2. Add domain: `cdn.example.com`
3. Cloudflare creates DNS record automatically
4. Enable "Proxy" (orange cloud) for CDN

#### 5.3 Configure Cache Rules

Cloudflare Dashboard → Rules → Page Rules (or Cache Rules):

**Rule 1: Tile caching**
```
URL: cdn.example.com/clients/*/cubemap/*/tiles/*/*.jpg
Cache Level: Cache Everything
Edge Cache TTL: 1 month
Browser Cache TTL: 1 year
```

**Rule 2: Metadata**
```
URL: cdn.example.com/clients/*/cubemap/*/tiles/*/metadata.json
Cache Level: Cache Everything
Edge Cache TTL: 5 minutes
```

### Phase 6: CORS Configuration (15 minutes)

Follow: [DEPLOYMENT_CORS.md](./DEPLOYMENT_CORS.md)

#### 6.1 Verify Backend CORS

```bash
curl -X OPTIONS https://api.example.com/api/render \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -v
```

Expected: `access-control-allow-origin: https://app.example.com`

#### 6.2 Verify CDN CORS

```bash
curl -H "Origin: https://app.example.com" \
  https://cdn.example.com/test.jpg \
  -I
```

Expected: `access-control-allow-origin` header present

#### 6.3 Test from Frontend

1. Open `https://app.example.com` in browser
2. Open DevTools Console
3. Run:

```javascript
fetch('https://api.example.com/health')
  .then(r => r.json())
  .then(console.log);
```

Expected: No CORS errors

### Phase 7: Testing & Validation (30 minutes)

Follow: [DEPLOYMENT_TESTING.md](./DEPLOYMENT_TESTING.md)

#### 7.1 End-to-End Flow Test

1. Open `https://app.example.com`
2. Select materials
3. Click "Render"
4. Verify:
   - [ ] Panorama appears
   - [ ] Tiles load progressively
   - [ ] No console errors
   - [ ] High quality eventually loads

#### 7.2 Performance Test

Follow: [DEPLOYMENT_PERFORMANCE.md](./DEPLOYMENT_PERFORMANCE.md)

Run performance checks:

```bash
# Health check
curl https://api.example.com/health

# Render request
time curl -X POST https://api.example.com/api/render \
  -H "Content-Type: application/json" \
  -d '{"client":"test","scene":"test","selection":{}}'

# Lighthouse
lighthouse https://app.example.com --view
```

Verify targets:
- [ ] Health check < 1s
- [ ] Cached render < 200ms
- [ ] New render < 3s
- [ ] Lighthouse score > 90

#### 7.3 Security Test

Follow: [DEPLOYMENT_HARDENING.md](./DEPLOYMENT_HARDENING.md)

Verify:
- [ ] HTTPS everywhere
- [ ] CORS properly configured
- [ ] Rate limiting active
- [ ] No sensitive data exposed

### Phase 8: Monitoring Setup (15 minutes)

#### 8.1 Render Monitoring

1. Render Dashboard → Metrics
2. Enable email alerts for:
   - Service crashes
   - High error rates
   - Deploy failures

#### 8.2 Cloudflare Analytics

1. Cloudflare Dashboard → Analytics
2. Monitor:
   - Traffic patterns
   - Cache hit ratio
   - Error rates

#### 8.3 External Monitoring (Optional)

Set up UptimeRobot or similar:
```
Monitor: https://api.example.com/health
Interval: 5 minutes
Alert: Email on downtime
```

## Post-Deployment Checklist

### Immediate Validation
- [ ] Frontend loads at custom domain
- [ ] Backend health check passes
- [ ] Complete render flow works
- [ ] Tiles load from CDN
- [ ] No CORS errors in console
- [ ] SSL certificates active on all domains

### Performance Validation
- [ ] Cold start < 3s
- [ ] Cached render < 200ms
- [ ] Tile streaming < 50ms
- [ ] Cache hit ratio > 90% (after warm-up)
- [ ] Lighthouse score > 90

### Security Validation
- [ ] HTTPS enforced
- [ ] CORS configured (no wildcards in production)
- [ ] Rate limiting active
- [ ] Security headers present
- [ ] No API keys in client code

### Monitoring Validation
- [ ] Logs visible in Render dashboard
- [ ] Metrics tracking in Cloudflare
- [ ] Alerts configured
- [ ] Error tracking set up (Sentry optional)

## Common Issues and Solutions

### Issue: CORS Errors

**Symptom**: Console shows "blocked by CORS policy"

**Solution**:
1. Verify CORS_ORIGINS in Render includes frontend domain
2. Check R2 CORS configuration
3. Test CORS headers manually

### Issue: Tiles Don't Load

**Symptom**: Broken image placeholders

**Solution**:
1. Check R2 public access enabled
2. Verify custom domain DNS
3. Check tile URLs in Network tab
4. Verify storage backend is R2

### Issue: Slow Performance

**Symptom**: Render takes >5s, tiles load slowly

**Solution**:
1. Check Render plan (upgrade from free tier)
2. Verify CDN cache hit ratio
3. Check Render instance CPU/memory
4. Verify R2 region matches users

### Issue: Rate Limiting Too Aggressive

**Symptom**: Legitimate users getting 429 errors

**Solution**:
1. Increase RATE_LIMIT_REQUESTS in Render env vars
2. Implement user-based rate limiting (not IP)
3. Add bypass for authenticated users

## Rollback Procedure

If deployment fails:

1. **Render**: Dashboard → Deployments → Rollback to previous version
2. **Cloudflare Pages**: Dashboard → Deployments → Rollback
3. **R2**: Restore from backup (if configured)
4. **DNS**: Revert DNS changes if needed

## Scaling Considerations

### Traffic Growth

**10 → 100 users**:
- Render: Upgrade to Standard plan
- R2: No changes needed
- Cloudflare: No changes needed

**100 → 1000 users**:
- Render: Enable auto-scaling (2-4 instances)
- R2: Consider lifecycle policies
- Monitor costs and optimize

### Geographic Expansion

- Consider multiple Render regions
- R2 is globally distributed automatically
- Cloudflare CDN covers worldwide

## Cost Optimization Tips

1. **Use Render Starter plan** ($7/month) with suspend-on-idle for low traffic
2. **Leverage Cloudflare free tier** for CDN and Pages
3. **R2 has zero egress fees** unlike AWS S3
4. **Monitor usage** and adjust plans monthly
5. **Implement caching** to reduce backend load

## Support and Resources

### Documentation
- [Full deployment documentation](./docs/)
- [Render documentation](https://render.com/docs)
- [Cloudflare Pages docs](https://developers.cloudflare.com/pages/)
- [Cloudflare R2 docs](https://developers.cloudflare.com/r2/)

### Community
- GitHub Issues: Report bugs and feature requests
- Render Community: https://community.render.com/
- Cloudflare Community: https://community.cloudflare.com/

## Next Steps After Deployment

1. **Monitor for 24 hours**: Watch metrics, errors, performance
2. **Optimize based on real traffic**: Adjust cache rules, rate limits
3. **Set up backups**: Configure R2 versioning and backups
4. **Implement CI/CD**: Automate deployments with GitHub Actions
5. **Add features**: Authentication, user accounts, analytics

## Success Criteria

Your deployment is successful when:

✅ All domains accessible via HTTPS  
✅ Frontend loads in < 2 seconds  
✅ Render flow completes successfully  
✅ Tiles load progressively  
✅ No console errors  
✅ Performance metrics meet targets  
✅ Security checks pass  
✅ Monitoring active  

**Congratulations! Your Panoconfig360 application is now live in production!** 🎉
