"""Migrate existing audio digests from instagram-digest bucket to dedicated tubelm bucket."""
import sys
import logging
from pathlib import Path

# Add desktop to path
desktop_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(desktop_dir))

import audio_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def migrate():
    s3 = audio_storage._client()
    if not s3:
        logger.error("R2 client could not be initialized from environment.")
        return False

    src_bucket = "instagram-digest"
    dst_bucket = "tubelm"
    prefix = "tubelm/audio/"

    logger.info("Scanning %s for prefix '%s'...", src_bucket, prefix)
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=src_bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            objects.append(item)

    logger.info("Found %d audio files (%0.2f MB) in %s", len(objects), sum(o['Size'] for o in objects)/(1024*1024), src_bucket)

    copied = 0
    skipped = 0
    errors = 0

    for i, obj in enumerate(objects, 1):
        key = obj["Key"]
        size = obj["Size"]
        try:
            # Check if destination already has this file
            try:
                head = s3.head_object(Bucket=dst_bucket, Key=key)
                if head.get("ContentLength") == size:
                    skipped += 1
                    continue
            except Exception:
                pass

            logger.info("[%d/%d] Copying %s (%d bytes)...", i, len(objects), key, size)
            s3.copy_object(
                Bucket=dst_bucket,
                Key=key,
                CopySource={"Bucket": src_bucket, "Key": key},
                ContentType="audio/mpeg",
                MetadataDirective="COPY",
            )
            copied += 1
        except Exception as e:
            logger.error("Failed to copy %s: %s", key, e)
            errors += 1

    logger.info("Migration complete: %d copied, %d already existed, %d errors.", copied, skipped, errors)
    return errors == 0

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
