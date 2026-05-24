"""
Phase 1 — Step 2
Creates the S3 bucket, enables versioning and EventBridge notifications,
then uploads all documents from docs/knowledge-base/.
"""
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION = config.REGION
BUCKET = config.S3_BUCKET_NAME
LOCAL_DOCS = Path(__file__).parents[2] / "docs" / "knowledge-base"
SKIP_SUFFIXES = {".DS_Store", ".tmp", ".gitkeep"}

s3 = boto3.client("s3", region_name=REGION)


def create_bucket():
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET)
        else:
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION}
            )
        print(f"Bucket '{BUCKET}' created.")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"Bucket '{BUCKET}' already exists — continuing.")


def configure_bucket():
    s3.put_bucket_versioning(
        Bucket=BUCKET,
        VersioningConfiguration={"Status": "Enabled"}
    )
    s3.put_bucket_notification_configuration(
        Bucket=BUCKET,
        NotificationConfiguration={"EventBridgeConfiguration": {}}
    )
    print("Versioning and EventBridge notifications enabled.")


def upload_documents():
    if not LOCAL_DOCS.exists():
        print(f"No local docs found at {LOCAL_DOCS} — skipping upload.")
        return
    uploaded = 0
    for filepath in LOCAL_DOCS.rglob("*"):
        if filepath.is_file() and filepath.suffix not in SKIP_SUFFIXES:
            s3_key = str(filepath.relative_to(LOCAL_DOCS))
            s3.upload_file(str(filepath), BUCKET, s3_key)
            print(f"  Uploaded: {s3_key}")
            uploaded += 1
    print(f"Upload complete — {uploaded} file(s).")


def main():
    create_bucket()
    configure_bucket()
    upload_documents()


if __name__ == "__main__":
    main()
