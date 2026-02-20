"""
R2 storage backend using boto3 (S3-compatible).
Provides cloud storage for panorama tiles and metadata using Cloudflare R2.
"""
import os
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# Configuration from environment
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "panoconfig360-tiles")
R2_ENDPOINT_URL = os.getenv(
    "R2_ENDPOINT_URL",
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else None
)
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://cdn.example.com")

logging.info(f"📦 Using R2 bucket: {R2_BUCKET_NAME}")
logging.info(f"🌐 R2 public URL: {R2_PUBLIC_URL}")

# Initialize S3 client for R2
s3_client = None
if R2_ENDPOINT_URL and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
    config = Config(max_pool_connections=50)
    s3_client = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=config,
    )
    logging.info("✅ R2 client initialized successfully")
else:
    logging.error("❌ R2 credentials not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")

_append_lock = threading.Lock()


def exists(key: str) -> bool:
    """Check if object exists in R2."""
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
    try:
        s3_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise


def upload_file(file_path: str, key: str, content_type: str = "application/octet-stream"):
    """Upload file to R2."""
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
    try:
        extra_args = {
            "ContentType": content_type,
        }
        
        # Set cache headers for tiles
        if key.endswith(".jpg") or key.endswith(".jpeg"):
            extra_args["CacheControl"] = "public, max-age=31536000, immutable"
        elif key.endswith(".json"):
            extra_args["CacheControl"] = "public, max-age=300"
        elif key.endswith(".ndjson"):
            extra_args["CacheControl"] = "no-cache"
        
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
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        s3_client.download_file(R2_BUCKET_NAME, key, dest_path)
        logging.info(f"📥 Downloaded from R2: {key}")
    except Exception as e:
        logging.error(f"❌ Failed to download from R2 {key}: {e}")
        raise


def upload_tiles_parallel(
    tiles: list[tuple[str, bytes]],
    content_type: str = "image/jpeg",
    max_workers: int = 25,
    on_tile_uploaded=None,
):
    """Upload tiles in parallel using boto3 put_object in a thread pool."""
    if not s3_client:
        raise RuntimeError("R2 client not initialized")

    max_workers = max(1, max_workers)
    active_uploads = 0
    max_active_uploads = 0
    active_lock = threading.Lock()

    def _put(tile_key: str, tile_bytes: bytes):
        nonlocal active_uploads, max_active_uploads
        with active_lock:
            active_uploads += 1
            max_active_uploads = max(max_active_uploads, active_uploads)
        try:
            s3_client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=tile_key,
                Body=tile_bytes,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
            if on_tile_uploaded is not None:
                on_tile_uploaded(tile_key)
        finally:
            with active_lock:
                active_uploads -= 1

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for tile_key, tile_bytes in tiles:
            futures.append(executor.submit(_put, tile_key, tile_bytes))

        for future in as_completed(futures):
            future.result()

    logging.info(
        "☁️ Upload paralelo concluído: %s tiles (workers=%s, max ativos=%s)",
        len(tiles),
        max_workers,
        max_active_uploads,
    )


def get_json(key: str) -> dict:
    """Get JSON object from R2."""
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
    try:
        response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise FileNotFoundError(f"JSON not found in R2: {key}")
        logging.error(f"❌ Failed to read JSON from R2 {key}: {e}")
        raise
    except Exception as e:
        logging.error(f"❌ Failed to read JSON from R2 {key}: {e}")
        raise


def put_json(key: str, data: dict):
    """Put JSON object to R2."""
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
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
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
    with _append_lock:
        # Download existing file
        try:
            response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            existing_content = response["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                existing_content = ""
            else:
                raise
        
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
    if not s3_client:
        raise RuntimeError("R2 client not initialized")
    
    try:
        response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        content = response["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return [], cursor
        raise
    
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
