"""Zero-cost audio hosting on Cloudflare R2 (shared bucket with Instagram Digest)."""
from __future__ import annotations
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
PREFIX = "tubelm/audio"

try:
    from dotenv import load_dotenv
    import paths
    load_dotenv(paths.get_env_file())
except Exception:
    pass


def _client():
    acct, key, secret = (os.getenv(k, "").strip() for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))
    if not (acct and key and secret):
        return None
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
                        aws_access_key_id=key, aws_secret_access_key=secret, region_name="auto",
                        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}))


def bucket() -> str:
    return os.getenv("R2_BUCKET_NAME", "instagram-digest").strip()


def public_domain() -> str:
    return os.getenv("R2_PUBLIC_DOMAIN", "").strip().rstrip("/")


def is_configured() -> bool:
    return _client() is not None and bool(public_domain())


def upload_audio(local: Path, run_date: str, force: bool = False) -> str:
    """Upload (idempotent unless force=True) and return the public URL, or '' when R2 is not configured/available."""
    s3 = _client()
    if not s3 or not public_domain():
        return ""
    key = f"{PREFIX}/{run_date}/{local.name}"
    url = f"{public_domain()}/{key}"
    if not force:
        try:
            s3.head_object(Bucket=bucket(), Key=key)
            return url
        except Exception:
            pass
    try:
        s3.upload_file(str(local), bucket(), key, ExtraArgs={
            "ContentType": "audio/mpeg",
            "CacheControl": "public, max-age=1209600, immutable"})
        logger.info("Uploaded audio to R2: %s", url)
        return url
    except Exception:
        logger.exception("R2 audio upload failed for %s", local.name)
        return ""


def purge_audio(max_age_days: int = 14) -> int:
    s3 = _client()
    if not s3:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).date()
    stale = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=PREFIX + "/"):
        for obj in page.get("Contents") or []:
            m = re.search(r"/(\d{4}-\d{2}-\d{2})/", obj["Key"])
            if m and datetime.strptime(m.group(1), "%Y-%m-%d").date() < cutoff:
                stale.append({"Key": obj["Key"]})
    for i in range(0, len(stale), 1000):
        s3.delete_objects(Bucket=bucket(), Delete={"Objects": stale[i:i + 1000], "Quiet": True})
    return len(stale)
