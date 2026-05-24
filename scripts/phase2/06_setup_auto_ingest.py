"""
Phase 2 — Step 6
Deploys the ingestion Lambda and wires an EventBridge rule
that fires on every S3 Object Created event in the KB bucket.
"""
import io
import json
import zipfile
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION     = config.REGION
ids        = config.load_ids()
LAMBDA_ROLE = ids.get("lambda_role_arn") or __import__("os").environ["LAMBDA_ROLE_ARN"]
KB_ID       = ids.get("kb_id")           or __import__("os").environ["BEDROCK_KB_ID"]
DS_ID       = ids.get("ds_id")           or __import__("os").environ["BEDROCK_DS_ID"]
ACCOUNT_ID  = boto3.client("sts").get_caller_identity()["Account"]

lmb    = boto3.client("lambda", region_name=REGION)
events = boto3.client("events", region_name=REGION)

INGEST_HANDLER_PATH = Path(__file__).parents[2] / "lambda" / "ingest_handler.py"


def deploy_ingest_lambda() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(str(INGEST_HANDLER_PATH), "ingest_handler.py")
    buf.seek(0)

    try:
        func = lmb.create_function(
            FunctionName=config.INGEST_LAMBDA,
            Runtime="python3.12",
            Role=LAMBDA_ROLE,
            Handler="ingest_handler.lambda_handler",
            Code={"ZipFile": buf.read()},
            Timeout=60,
            Environment={
                "Variables": {
                    "KNOWLEDGE_BASE_ID": KB_ID,
                    "DATA_SOURCE_ID":    DS_ID
                }
            }
        )
        func_arn = func["FunctionArn"]
        print(f"Ingest Lambda created: {func_arn}")
    except lmb.exceptions.ResourceConflictException:
        func_arn = lmb.get_function(
            FunctionName=config.INGEST_LAMBDA
        )["Configuration"]["FunctionArn"]
        print(f"Ingest Lambda already exists: {func_arn}")
    return func_arn


def create_eventbridge_rule(func_arn: str):
    rule = events.put_rule(
        Name="bedrock-kb-s3-trigger",
        EventPattern=json.dumps({
            "source": ["aws.s3"],
            "detail-type": ["Object Created"],
            "detail": {
                "bucket": {"name": [config.S3_BUCKET_NAME]},
                "object": {
                    "key": [
                        {"prefix": "incident-history/"},
                        {"prefix": "app-features/"},
                        {"prefix": "runbooks/"}
                    ]
                }
            }
        }),
        State="ENABLED",
        Description="Trigger Bedrock KB ingestion on new S3 uploads"
    )
    events.put_targets(
        Rule="bedrock-kb-s3-trigger",
        Targets=[{"Id": "ingest-lambda", "Arn": func_arn}]
    )
    try:
        lmb.add_permission(
            FunctionName=config.INGEST_LAMBDA,
            StatementId="EventBridgeInvoke",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule["RuleArn"]
        )
    except lmb.exceptions.ResourceConflictException:
        pass
    print("EventBridge rule active — uploads trigger ingestion automatically.")


def main():
    func_arn = deploy_ingest_lambda()
    create_eventbridge_rule(func_arn)


if __name__ == "__main__":
    main()
