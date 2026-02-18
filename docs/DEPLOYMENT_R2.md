# Cloudflare R2 Storage Configuration

## Overview

Cloudflare R2 provides S3-compatible object storage with zero egress fees, making it ideal for serving panorama tiles to a global audience.

## Prerequisites

- Cloudflare account (free tier available)
- Cloudflare Workers/Pages subscription (for custom domains)

## Step 1: Create R2 Bucket

### 1.1 Access R2 Dashboard

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Select your account
3. Navigate to **R2** in the sidebar
4. Click **"Create bucket"**

### 1.2 Bucket Configuration

**Bucket name**: `panoconfig360-tiles`

**Location**: Automatic (Cloudflare chooses optimal location)

**Storage class**: Standard (no archive tier needed for active tiles)

Click **"Create bucket"**

## Step 2: Configure R2 API Access

### 2.1 Create API Token

1. In R2 dashboard, go to **"Manage R2 API Tokens"**
2. Click **"Create API token"**

**Token name**: `panoconfig360-backend-rw`

**Permissions**:
- Object Read & Write: ✅
- Bucket List: ✅ (optional)

**Bucket scope**:
- Specific buckets: `panoconfig360-tiles`

**TTL**: No expiration (or set custom expiration)

Click **"Create API Token"**

### 2.2 Save Credentials

You'll receive three pieces of information:

```
Access Key ID: a1b2c3d4e5f6g7h8i9j0
Secret Access Key: x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6n7o8p9q0
Endpoint URL: https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
```

**⚠️ IMPORTANT**: Save these credentials securely. The Secret Access Key is shown only once.

### 2.3 Find Your Account ID

Your R2 Account ID is in the endpoint URL:
```
https://ACCOUNT_ID.r2.cloudflarestorage.com
          ^^^^^^^^^^
```

Or find it at: Dashboard → R2 → Overview → Account ID

## Step 3: Configure Bucket CORS

### 3.1 Set CORS Policy

R2 CORS is configured via API. Use this script:

Create `scripts/configure-r2-cors.sh`:

```bash
#!/bin/bash

# Configuration
ACCOUNT_ID="your_account_id"
BUCKET_NAME="panoconfig360-tiles"
ACCESS_KEY_ID="your_access_key_id"
SECRET_ACCESS_KEY="your_secret_access_key"

# CORS configuration
CORS_CONFIG='{
  "CORSRules": [
    {
      "AllowedOrigins": ["https://app.example.com", "https://*.pages.dev"],
      "AllowedMethods": ["GET", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
      "MaxAgeSeconds": 3600
    }
  ]
}'

# Upload CORS configuration using AWS CLI
aws s3api put-bucket-cors \
  --bucket "$BUCKET_NAME" \
  --cors-configuration "$CORS_CONFIG" \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2

echo "CORS configuration applied successfully"
```

Make executable and run:
```bash
chmod +x scripts/configure-r2-cors.sh
./scripts/configure-r2-cors.sh
```

### 3.2 Configure AWS CLI for R2

Create AWS CLI profile in `~/.aws/credentials`:

```ini
[r2]
aws_access_key_id = your_r2_access_key_id
aws_secret_access_key = your_r2_secret_access_key
```

And in `~/.aws/config`:

```ini
[profile r2]
region = auto
output = json
```

### 3.3 Verify CORS Configuration

```bash
aws s3api get-bucket-cors \
  --bucket panoconfig360-tiles \
  --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
  --profile r2
```

## Step 4: Configure Public Access

### 4.1 Enable Public Access (Read-Only)

R2 buckets are private by default. To serve tiles publicly:

**Option 1: R2.dev Subdomain** (Free, Easy)
1. In R2 bucket settings, click **"Settings"**
2. Under **"Public access"**, click **"Allow Access"**
3. Copy the public URL: `https://pub-xxxx.r2.dev`

**Option 2: Custom Domain** (Recommended for Production)
1. In R2 bucket settings, click **"Settings"**
2. Under **"Custom domains"**, click **"Connect domain"**
3. Enter your domain: `cdn.example.com`
4. Add DNS record in Cloudflare DNS:
   - Type: CNAME
   - Name: cdn
   - Target: `panoconfig360-tiles.YOUR_ACCOUNT_ID.r2.cloudflarestorage.com`
   - Proxy status: ✅ Proxied (enables CDN)

### 4.2 Configure Bucket Permissions

By default, objects are private. To make specific paths public:

**Public Read Policy** (via AWS CLI):

Create `public-read-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::panoconfig360-tiles/clients/*/cubemap/*/tiles/*"
    }
  ]
}
```

Apply policy:
```bash
aws s3api put-bucket-policy \
  --bucket panoconfig360-tiles \
  --policy file://public-read-policy.json \
  --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
  --profile r2
```

## Step 5: Implement R2 Storage Backend

### 5.1 Create R2 Storage Adapter

Create `panoconfig360_backend/storage/storage_r2.py`:

```python
"""
R2 storage backend using boto3 (S3-compatible).
"""
import os
import json
import logging
import threading
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

# Configuration from environment
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "panoconfig360-tiles")
R2_ENDPOINT_URL = os.getenv(
    "R2_ENDPOINT_URL",
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
)
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", f"https://pub-xxxx.r2.dev")

logging.info(f"📦 Using R2 bucket: {R2_BUCKET_NAME}")
logging.info(f"🌐 R2 public URL: {R2_PUBLIC_URL}")

# Initialize S3 client for R2
s3_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto",
)

_append_lock = threading.Lock()


def exists(key: str) -> bool:
    """Check if object exists in R2."""
    try:
        s3_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False


def upload_file(file_path: str, key: str, content_type: str = "application/octet-stream"):
    """Upload file to R2."""
    try:
        extra_args = {
            "ContentType": content_type,
        }
        
        # Set cache headers for tiles
        if key.endswith(".jpg"):
            extra_args["CacheControl"] = "public, max-age=31536000, immutable"
        elif key.endswith(".json"):
            extra_args["CacheControl"] = "public, max-age=300"
        
        s3_client.upload_file(
            file_path,
            R2_BUCKET_NAME,
            key,
            ExtraArgs=extra_args
        )
        logging.info(f"☁️ Uploaded to R2: {key}")
    except Exception as e:
        logging.error(f"❌ Failed to upload to R2 {key}: {e}")
        raise


def download_file(key: str, dest_path: str):
    """Download file from R2."""
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        s3_client.download_file(R2_BUCKET_NAME, key, dest_path)
        logging.info(f"📥 Downloaded from R2: {key}")
    except Exception as e:
        logging.error(f"❌ Failed to download from R2 {key}: {e}")
        raise


def get_json(key: str) -> dict:
    """Get JSON object from R2."""
    try:
        response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return data
    except Exception as e:
        logging.error(f"❌ Failed to read JSON from R2 {key}: {e}")
        raise


def put_json(key: str, data: dict):
    """Put JSON object to R2."""
    try:
        s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
            CacheControl="public, max-age=300"
        )
        logging.info(f"☁️ Uploaded JSON to R2: {key}")
    except Exception as e:
        logging.error(f"❌ Failed to upload JSON to R2 {key}: {e}")
        raise


def append_jsonl(key: str, payload: dict):
    """
    Append to JSONL file in R2.
    Note: This is not atomic. For high-concurrency, consider using a queue.
    """
    with _append_lock:
        # Download existing file
        try:
            response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            existing_content = response["Body"].read().decode("utf-8")
        except ClientError:
            existing_content = ""
        
        # Append new line
        new_line = json.dumps(payload, ensure_ascii=False) + "\n"
        updated_content = existing_content + new_line
        
        # Upload back
        s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=updated_content.encode("utf-8"),
            ContentType="application/x-ndjson",
            CacheControl="no-cache"
        )


def read_jsonl_slice(key: str, cursor: int = 0, limit: int = 200) -> tuple[list[dict], int]:
    """Read slice of JSONL file from R2."""
    try:
        response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        content = response["Body"].read().decode("utf-8")
    except ClientError:
        return [], cursor
    
    events: list[dict] = []
    next_cursor = cursor
    
    for idx, line in enumerate(content.splitlines()):
        if idx < cursor:
            continue
        
        line = line.strip()
        if not line:
            continue
        
        try:
            events.append(json.loads(line))
            next_cursor = idx + 1
        except json.JSONDecodeError:
            logging.warning("⚠️ Invalid JSONL line in R2: %s", key)
        
        if len(events) >= limit:
            break
    
    return events, next_cursor


def get_public_url(key: str) -> str:
    """Get public URL for a key."""
    return f"{R2_PUBLIC_URL}/{key}"
```

### 5.2 Update Storage Factory

Create `panoconfig360_backend/storage/factory.py`:

```python
"""
Storage backend factory.
Selects storage backend based on STORAGE_BACKEND environment variable.
"""
import os

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")

if STORAGE_BACKEND == "r2":
    from panoconfig360_backend.storage.storage_r2 import (
        exists,
        upload_file,
        download_file,
        get_json,
        append_jsonl,
        read_jsonl_slice,
        get_public_url,
    )
else:
    from panoconfig360_backend.storage.storage_local import (
        exists,
        upload_file,
        download_file,
        get_json,
        append_jsonl,
        read_jsonl_slice,
    )
    
    def get_public_url(key: str) -> str:
        """Local storage returns relative URLs."""
        return f"/panoconfig360_cache/{key}"

__all__ = [
    "exists",
    "upload_file",
    "download_file",
    "get_json",
    "append_jsonl",
    "read_jsonl_slice",
    "get_public_url",
]
```

### 5.3 Update Server to Use Factory

In `panoconfig360_backend/api/server.py`, change imports:

```python
# OLD:
# from panoconfig360_backend.storage.storage_local import (...)

# NEW:
from panoconfig360_backend.storage.factory import (
    exists,
    upload_file,
    get_json,
    append_jsonl,
    read_jsonl_slice,
    get_public_url,
)
```

## Step 6: Configure CDN Caching

### 6.1 Create Cache Rules (Custom Domain Only)

In Cloudflare dashboard:

1. Select your domain (example.com)
2. Go to **Rules** → **Page Rules** (or **Cache Rules** in new dashboard)
3. Create new rule

**Rule 1: Tile Assets (Immutable)**
```
URL: cdn.example.com/clients/*/cubemap/*/tiles/*/*.jpg
Settings:
  - Cache Level: Cache Everything
  - Edge Cache TTL: 1 month
  - Browser Cache TTL: 1 year
  - Origin Cache Control: On
```

**Rule 2: Metadata (Short TTL)**
```
URL: cdn.example.com/clients/*/cubemap/*/tiles/*/metadata.json
Settings:
  - Cache Level: Cache Everything
  - Edge Cache TTL: 5 minutes
  - Browser Cache TTL: 5 minutes
```

**Rule 3: Events (No Cache)**
```
URL: cdn.example.com/clients/*/cubemap/*/tiles/*/tile_events.ndjson
Settings:
  - Cache Level: Bypass
```

### 6.2 Configure Transform Rules (Optional)

Add response headers for all R2 content:

**Headers**:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, HEAD
Access-Control-Max-Age: 3600
Timing-Allow-Origin: *
```

## Step 7: Test R2 Integration

### 7.1 Test Upload

```bash
# Set environment variables
export STORAGE_BACKEND=r2
export R2_ACCOUNT_ID=your_account_id
export R2_ACCESS_KEY_ID=your_access_key_id
export R2_SECRET_ACCESS_KEY=your_secret_access_key
export R2_BUCKET_NAME=panoconfig360-tiles
export R2_PUBLIC_URL=https://cdn.example.com

# Test upload
python3 << EOF
from panoconfig360_backend.storage.factory import upload_file, exists, get_public_url
import tempfile

# Create test file
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write('Test upload')
    temp_path = f.name

# Upload
key = 'test/upload.txt'
upload_file(temp_path, key, 'text/plain')

# Check exists
print(f"File exists: {exists(key)}")

# Get public URL
print(f"Public URL: {get_public_url(key)}")
EOF
```

### 7.2 Test Public Access

```bash
# Using R2.dev domain
curl https://pub-xxxx.r2.dev/test/upload.txt

# Using custom domain
curl https://cdn.example.com/test/upload.txt
```

### 7.3 Test CORS

```bash
curl -H "Origin: https://app.example.com" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     https://cdn.example.com/test/upload.txt \
     -v
```

Expected headers:
```
< access-control-allow-origin: https://app.example.com
< access-control-allow-methods: GET, HEAD
< access-control-max-age: 3600
```

## Step 8: Migrate Existing Data (If Applicable)

### 8.1 Sync Local Cache to R2

Create `scripts/sync-to-r2.sh`:

```bash
#!/bin/bash

# Configuration
ACCOUNT_ID="your_account_id"
BUCKET_NAME="panoconfig360-tiles"
LOCAL_CACHE="panoconfig360_cache"

# Sync using AWS CLI
aws s3 sync "$LOCAL_CACHE" "s3://$BUCKET_NAME" \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2 \
  --exclude "*.ndjson" \
  --cache-control "public, max-age=31536000, immutable" \
  --content-type "image/jpeg" \
  --include "*.jpg"

# Sync JSON files
aws s3 sync "$LOCAL_CACHE" "s3://$BUCKET_NAME" \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2 \
  --exclude "*" \
  --include "*.json" \
  --cache-control "public, max-age=300" \
  --content-type "application/json"

echo "Sync complete!"
```

### 8.2 Verify Sync

```bash
aws s3 ls s3://panoconfig360-tiles/clients/ \
  --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
  --profile r2 \
  --recursive
```

## Troubleshooting

### Access Denied Errors

**Issue**: 403 Forbidden when accessing objects
**Solution**: 
- Verify bucket public access is enabled
- Check bucket policy allows public reads
- Verify custom domain is proxied through Cloudflare

### CORS Errors

**Issue**: `No 'Access-Control-Allow-Origin' header`
**Solution**:
- Verify CORS configuration is applied
- Check custom domain proxy status
- Ensure origin is in allowed list

### Slow Upload Performance

**Issue**: Uploads take too long
**Solution**:
- Use multipart uploads for large files
- Implement parallel uploads
- Check network latency to R2 endpoint

### High Costs

**Issue**: Unexpected charges
**Solution**:
- R2 has no egress fees (verify you're using R2, not S3)
- Class A operations (writes) cost $4.50/million
- Class B operations (reads) cost $0.36/million
- Storage is $0.015/GB/month

## Cost Estimation

### Storage Costs

**Example: 1000 panoramas, 5 scenes each, 6 faces, 3 LOD levels**

```
Total tiles: 1000 × 5 × 6 × (1 + 4 + 16) = 630,000 tiles
Average tile size: 50KB
Total storage: 630,000 × 50KB ≈ 31.5 GB

Monthly cost: 31.5 GB × $0.015 = $0.47/month
```

### Operation Costs

**Example: 10,000 panorama views/month**

```
Reads per view: ~100 tiles (progressive loading)
Total reads: 10,000 × 100 = 1,000,000 reads

Monthly cost: 1,000,000 / 1,000,000 × $0.36 = $0.36/month
```

**Total monthly cost: ~$0.83/month for 10,000 views**

Compare to AWS S3:
- Storage: $0.69/month (31.5 GB × $0.023)
- Egress: $450/month (5TB × $0.09/GB) 
- **Total: $450.69/month** 😱

**R2 savings: 99.8%** 🎉

## Next Steps

- [Deploy frontend to Cloudflare Pages](./DEPLOYMENT_CLOUDFLARE_PAGES.md)
- [Configure CORS](./DEPLOYMENT_CORS.md)
- [Performance validation](./DEPLOYMENT_PERFORMANCE.md)
