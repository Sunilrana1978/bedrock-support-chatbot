"""
scripts/deploy.py

Deploys the full Bedrock Support Chatbot CloudFormation stack.
Replaces Phase 1 scripts (01–05) and Phase 2 setup scripts (06, 07, 09).

Usage:
  python scripts/deploy.py            # create or update stack
  python scripts/deploy.py --delete   # tear down everything
"""
import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
TEMPLATE   = ROOT / "infra" / "cloudformation" / "template.yml"
IDS_FILE   = ROOT / "bedrock_ids.json"
STACK_NAME = "bedrock-support-chatbot"
REGION     = os.getenv("AWS_REGION", "us-east-1")


def _session():
    return boto3.session.Session(region_name=REGION)


def _load_ids():
    return json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}


def _save_ids(data: dict):
    merged = _load_ids()
    merged.update(data)
    IDS_FILE.write_text(json.dumps(merged, indent=2))
    print(f"IDs saved → {IDS_FILE}")


def _read_instruction() -> str:
    path = ROOT / "bedrock" / "instruction.txt"
    return path.read_text().strip()


def deploy():
    sess    = _session()
    cf      = sess.client("cloudformation")
    s3      = sess.client("s3")
    bedrock = sess.client("bedrock-agent")

    template_body = TEMPLATE.read_text()
    params = [
        {"ParameterKey": "S3BucketName",     "ParameterValue": os.getenv("S3_BUCKET_NAME", "prod-support-kb-docs")},
        {"ParameterKey": "AgentInstruction",  "ParameterValue": _read_instruction()},
        {"ParameterKey": "SNSAlertsArn",      "ParameterValue": os.getenv("SNS_ALERTS_ARN", "")},
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
            print("Updating stack…")
            waiter = cf.get_waiter("stack_update_complete")
        except ClientError as e:
            if "No updates are to be performed" in str(e):
                print("Stack is already up to date.")
                _post_deploy(cf, s3, bedrock)
                return
            raise
    else:
        cf.create_stack(**common, OnFailure="ROLLBACK")
        print("Creating stack…")
        waiter = cf.get_waiter("stack_create_complete")

    print("Waiting for stack to stabilise (this can take 10–20 min for first deploy)…")
    waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 120})
    print("Stack deployed successfully.")
    _post_deploy(cf, s3, bedrock)


def _post_deploy(cf, s3, bedrock):
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

    bucket = outputs.get("BucketName", os.getenv("S3_BUCKET_NAME", "prod-support-kb-docs"))
    _upload_docs(s3, bucket)

    kb_id = outputs.get("KnowledgeBaseId")
    ds_id = outputs.get("DataSourceId")
    if kb_id and ds_id:
        _trigger_ingestion(bedrock, kb_id, ds_id)

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
        print(f"Uploaded {count} document(s) to s3://{bucket}/")


def _trigger_ingestion(bedrock, kb_id: str, ds_id: str):
    running = bedrock.list_ingestion_jobs(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
        filters=[{"attribute": "STATUS", "operator": "EQ", "values": ["IN_PROGRESS", "STARTING"]}],
    )["ingestionJobSummaries"]
    if running:
        print("Ingestion already running.")
        return
    job    = bedrock.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    job_id = job["ingestionJob"]["ingestionJobId"]
    print(f"Started initial ingestion job: {job_id}")
    print("Ingestion runs in the background (~5–15 min). Monitor in the Bedrock console.")


def delete():
    cf = _session().client("cloudformation")
    cf.delete_stack(StackName=STACK_NAME)
    print("Deleting stack… (this may take several minutes)")
    cf.get_waiter("stack_delete_complete").wait(
        StackName=STACK_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 60}
    )
    print("Stack deleted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy the Bedrock Support Chatbot stack")
    parser.add_argument("--delete", action="store_true", help="Tear down the CloudFormation stack")
    args = parser.parse_args()

    if args.delete:
        delete()
    else:
        deploy()
