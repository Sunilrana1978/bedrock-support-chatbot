"""
Phase 2 — Step 7
Creates an EventBridge cron rule that triggers a full KB re-sync
every Sunday at 02:00 UTC.
"""
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION     = config.REGION
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
FUNC_ARN   = (f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}"
              f":function:{config.INGEST_LAMBDA}")

events = boto3.client("events", region_name=REGION)
lmb    = boto3.client("lambda", region_name=REGION)


def main():
    rule = events.put_rule(
        Name="bedrock-kb-weekly-sync",
        ScheduleExpression="cron(0 2 ? * SUN *)",
        State="ENABLED",
        Description="Weekly full re-ingestion for Bedrock KB"
    )
    events.put_targets(
        Rule="bedrock-kb-weekly-sync",
        Targets=[{"Id": "weekly-ingest", "Arn": FUNC_ARN}]
    )
    try:
        lmb.add_permission(
            FunctionName=config.INGEST_LAMBDA,
            StatementId="WeeklyScheduleInvoke",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule["RuleArn"]
        )
    except lmb.exceptions.ResourceConflictException:
        pass
    print("Weekly sync rule created: every Sunday 02:00 UTC")


if __name__ == "__main__":
    main()
