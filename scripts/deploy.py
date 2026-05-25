"""
scripts/deploy.py

Packages Lambda functions, uploads artifacts to S3, and deploys the
CloudFormation stack. Equivalent to running scripts/deploy.sh.

Usage:
  python scripts/deploy.py            # create or update stack
  python scripts/deploy.py --delete   # tear down everything
"""
import argparse
import io
import json
import os
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

ROOT             = Path(__file__).parent.parent
TEMPLATE         = ROOT / "infra" / "cloudformation" / "template.yml"
LAMBDA_DIR       = ROOT / "lambda"
IDS_FILE         = ROOT / "bedrock_ids.json"
STACK_NAME       = "bedrock-support-chatbot"
REGION           = os.getenv("AWS_REGION", "us-east-1")


def _session():
    return boto3.session.Session(region_name=REGION)


def _account_id(sess) -> str:
    return sess.client("sts").get_caller_identity()["Account"]


def _artifacts_bucket(account_id: str) -> str:
    return os.getenv("ARTIFACTS_BUCKET", f"cf-artifacts-{account_id}-{REGION}")


def _load_ids() -> dict:
    return json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}


def _save_ids(data: dict):
    merged = _load_ids()
    merged.update(data)
    IDS_FILE.write_text(json.dumps(merged, indent=2))
    print(f"IDs saved → {IDS_FILE}")


def _read_instruction() -> str:
    return (ROOT / "bedrock" / "instruction.txt").read_text().strip()


# ── Lambda packaging ──────────────────────────────────────────────────────────

def _zip_file(py_path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(py_path, py_path.name)
    return buf.getvalue()


def _ensure_bucket(s3, bucket: str):
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        kwargs = {"Bucket": bucket}
        if REGION != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(**kwargs)
        print(f"Created artifacts bucket: {bucket}")


def _upload_lambdas(s3, bucket: str):
    handlers = [
        (LAMBDA_DIR / "chatbot_handler.py",    "lambda/chatbot.zip"),
        (LAMBDA_DIR / "ingest_handler.py",     "lambda/ingest.zip"),
        (LAMBDA_DIR / "aoss_index_creator.py", "lambda/aoss_index_creator.zip"),
    ]
    for src, key in handlers:
        s3.put_object(Bucket=bucket, Key=key, Body=_zip_file(src))
        print(f"  Uploaded {src.name} → s3://{bucket}/{key}")


# ── CloudFormation deploy ─────────────────────────────────────────────────────

def deploy():
    sess    = _session()
    s3      = sess.client("s3")
    cf      = sess.client("cloudformation")
    bedrock = sess.client("bedrock-agent")

    account_id      = _account_id(sess)
    artifacts_bucket = _artifacts_bucket(account_id)

    # Step 1 — artifacts bucket
    print("[1/5] Ensuring artifacts bucket…")
    _ensure_bucket(s3, artifacts_bucket)

    # Step 2 — package and upload Lambda zips
    print("[2/5] Packaging and uploading Lambda functions…")
    _upload_lambdas(s3, artifacts_bucket)

    # Step 3 — deploy CF stack
    print("[3/5] Deploying CloudFormation stack…")
    template_body = TEMPLATE.read_text()
    params = [
        {"ParameterKey": "S3BucketName",    "ParameterValue": os.getenv("S3_BUCKET_NAME", "prod-support-kb-docs")},
        {"ParameterKey": "ArtifactsBucket", "ParameterValue": artifacts_bucket},
        {"ParameterKey": "AgentInstruction","ParameterValue": _read_instruction()},
        {"ParameterKey": "SNSAlertsArn",    "ParameterValue": os.getenv("SNS_ALERTS_ARN", "")},
    ]
    common = dict(
        StackName=STACK_NAME,
        TemplateBody=template_body,
        Parameters=params,
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )

    stack_exists = False
    try:
        cf.describe_stacks(StackName=STACK_NAME)
        stack_exists = True
    except ClientError:
        pass

    if stack_exists:
        try:
            cf.update_stack(**common)
            print("  Updating stack…")
            waiter = cf.get_waiter("stack_update_complete")
        except ClientError as exc:
            if "No updates are to be performed" in str(exc):
                print("  Stack is already up to date.")
                _post_deploy(cf, s3, bedrock)
                return
            raise
    else:
        cf.create_stack(**common, OnFailure="ROLLBACK")
        print("  Creating stack (10–20 min first time)…")
        waiter = cf.get_waiter("stack_create_complete")

    waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 120})
    print("  Stack deployed successfully.")
    _post_deploy(cf, s3, bedrock)


def _post_deploy(cf, s3, bedrock):
    # Step 4 — save outputs
    print("[4/5] Saving stack outputs…")
    stack   = cf.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    _save_ids({
        "api_endpoint": outputs.get("ApiEndpoint"),
        "kb_id":        outputs.get("KnowledgeBaseId"),
        "ds_id":        outputs.get("DataSourceId"),
        "agent_id":     outputs.get("AgentId"),
        "alias_id":     outputs.get("AgentAliasId"),
        "bucket":       outputs.get("BucketName"),
    })

    # Step 5 — upload docs + trigger ingestion
    print("[5/5] Uploading knowledge-base documents…")
    bucket = outputs.get("BucketName", os.getenv("S3_BUCKET_NAME", "prod-support-kb-docs"))
    _upload_docs(s3, bucket)
    _trigger_ingestion(bedrock, outputs.get("KnowledgeBaseId"), outputs.get("DataSourceId"))

    print(f"\nChatbot endpoint: {outputs.get('ApiEndpoint')}")
    print("Test it:")
    print(f'  curl -X POST {outputs.get("ApiEndpoint")} \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"message": "How do I resolve a DB connection timeout?"}\'')


def _upload_docs(s3, bucket: str):
    docs_root = ROOT / "docs" / "knowledge-base"
    skip      = {".DS_Store", ".tmp", ".gitkeep"}
    count     = 0
    for path in docs_root.rglob("*"):
        if path.is_file() and path.name not in skip:
            key = path.relative_to(docs_root).as_posix()
            s3.upload_file(str(path), bucket, key)
            count += 1
    if count:
        print(f"  Uploaded {count} document(s) to s3://{bucket}/")


def _trigger_ingestion(bedrock, kb_id: str, ds_id: str):
    if not kb_id or not ds_id:
        return
    running = bedrock.list_ingestion_jobs(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
        filters=[{"attribute": "STATUS", "operator": "EQ", "values": ["IN_PROGRESS", "STARTING"]}],
    )["ingestionJobSummaries"]
    if running:
        print("  Ingestion already running.")
        return
    job    = bedrock.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    job_id = job["ingestionJob"]["ingestionJobId"]
    print(f"  Started ingestion job {job_id} (runs ~5–15 min in background).")


def delete():
    cf = _session().client("cloudformation")
    cf.delete_stack(StackName=STACK_NAME)
    print("Deleting stack…")
    cf.get_waiter("stack_delete_complete").wait(
        StackName=STACK_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 60}
    )
    print("Stack deleted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy the Bedrock Support Chatbot stack")
    parser.add_argument("--delete", action="store_true", help="Delete the CloudFormation stack")
    args = parser.parse_args()

    if args.delete:
        delete()
    else:
        deploy()
