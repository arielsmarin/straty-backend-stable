#!/bin/bash
set -e

#############################################################################
# Cloudflare R2 CORS Configuration Script
#
# This script configures CORS settings for the R2 bucket to allow
# frontend access from the browser.
#
# Prerequisites:
# - AWS CLI installed (for S3-compatible API)
# - R2 credentials configured in ~/.aws/credentials
#
# Usage:
#   ./configure-r2-cors.sh
#############################################################################

# Configuration
ACCOUNT_ID="${R2_ACCOUNT_ID:-your_account_id}"
BUCKET_NAME="${R2_BUCKET_NAME:-panoconfig360-tiles}"
FRONTEND_DOMAIN="${FRONTEND_DOMAIN:-https://app.example.com}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================="
echo "R2 CORS Configuration Script"
echo "================================="
echo ""
echo "Bucket: $BUCKET_NAME"
echo "Account ID: $ACCOUNT_ID"
echo "Frontend Domain: $FRONTEND_DOMAIN"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    echo "Install it with: pip install awscli"
    exit 1
fi

# Create CORS configuration
cat > /tmp/r2-cors-config.json <<EOF
{
  "CORSRules": [
    {
      "ID": "AllowFrontendAccess",
      "AllowedOrigins": [
        "$FRONTEND_DOMAIN",
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
EOF

echo "CORS configuration created:"
cat /tmp/r2-cors-config.json
echo ""

# Apply CORS configuration
echo "Applying CORS configuration..."
if aws s3api put-bucket-cors \
  --bucket "$BUCKET_NAME" \
  --cors-configuration file:///tmp/r2-cors-config.json \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2; then
  
  echo -e "${GREEN}✅ CORS configuration applied successfully${NC}"
else
  echo -e "${RED}❌ Failed to apply CORS configuration${NC}"
  exit 1
fi

# Verify CORS configuration
echo ""
echo "Verifying CORS configuration..."
if aws s3api get-bucket-cors \
  --bucket "$BUCKET_NAME" \
  --endpoint-url "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --profile r2; then
  
  echo -e "${GREEN}✅ CORS configuration verified${NC}"
else
  echo -e "${YELLOW}⚠️ Could not verify CORS configuration${NC}"
fi

# Cleanup
rm /tmp/r2-cors-config.json

echo ""
echo "================================="
echo "✅ CORS configuration complete!"
echo "================================="
