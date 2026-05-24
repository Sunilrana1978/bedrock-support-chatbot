"""
Phase 2 — Step 10
Utility script — upload a resolved incident report to S3.
EventBridge fires automatically, triggering KB re-ingestion.

Usage:
  python scripts/phase2/10_upload_incident.py \
    --file ./docs/knowledge-base/incident-history/my-incident.md \
    --service checkout \
    --severity P2
"""
import argparse
import sys
from datetime import date
from pathlib import Path
import boto3
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

s3 = boto3.client("s3", region_name=config.REGION)


def upload_incident(filepath: str, service: str, severity: str):
    today  = date.today().isoformat()
    fname  = Path(filepath).stem
    s3_key = f"incident-history/{today}-{service}-{severity}-{fname}.md"

    s3.upload_file(
        filepath,
        config.S3_BUCKET_NAME,
        s3_key,
        ExtraArgs={
            "ContentType": "text/markdown",
            "Metadata": {
                "service": service,
                "severity": severity,
                "date": today
            }
        }
    )
    print(f"Uploaded: s3://{config.S3_BUCKET_NAME}/{s3_key}")
    print("EventBridge will trigger KB re-ingestion automatically.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a resolved incident report")
    parser.add_argument("--file",     required=True, help="Path to the .md incident file")
    parser.add_argument("--service",  required=True, help="Service name, e.g. checkout")
    parser.add_argument("--severity", required=True, choices=["P1", "P2", "P3"])
    args = parser.parse_args()
    upload_incident(args.file, args.service, args.severity)
