"""
Phase 2 — Step 9
Creates CloudWatch alarms and a dashboard for the chatbot and ingestion Lambda.
"""
import json
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION    = config.REGION
SNS_TOPIC = config.SNS_ALERTS_ARN

cw = boto3.client("cloudwatch", region_name=REGION)


def create_alarms():
    # Alarm 1: ingestion Lambda errors
    cw.put_metric_alarm(
        AlarmName="BedrockKBIngestionFailure",
        MetricName="Errors",
        Namespace="AWS/Lambda",
        Dimensions=[{"Name": "FunctionName", "Value": config.INGEST_LAMBDA}],
        Period=300,
        EvaluationPeriods=1,
        Threshold=1,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        Statistic="Sum",
        AlarmActions=[SNS_TOPIC] if SNS_TOPIC else [],
        TreatMissingData="notBreaching"
    )
    print("Alarm created: BedrockKBIngestionFailure")

    # Alarm 2: chatbot P99 latency > 10 s
    cw.put_metric_alarm(
        AlarmName="BedrockChatbotHighLatency",
        MetricName="Duration",
        Namespace="AWS/Lambda",
        Dimensions=[{"Name": "FunctionName", "Value": config.CHATBOT_LAMBDA}],
        Period=60,
        EvaluationPeriods=3,
        Threshold=10000,
        ComparisonOperator="GreaterThanThreshold",
        ExtendedStatistic="p99",
        AlarmActions=[SNS_TOPIC] if SNS_TOPIC else [],
        TreatMissingData="notBreaching"
    )
    print("Alarm created: BedrockChatbotHighLatency")


def create_dashboard():
    body = {
        "widgets": [
            {
                "type": "metric", "x": 0, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "Chatbot invocations & errors",
                    "metrics": [
                        ["AWS/Lambda", "Invocations", "FunctionName",
                         config.CHATBOT_LAMBDA],
                        ["AWS/Lambda", "Errors", "FunctionName",
                         config.CHATBOT_LAMBDA, {"color": "#d62728"}]
                    ],
                    "period": 60, "stat": "Sum", "view": "timeSeries"
                }
            },
            {
                "type": "metric", "x": 12, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "Chatbot p99 latency (ms)",
                    "metrics": [
                        ["AWS/Lambda", "Duration", "FunctionName",
                         config.CHATBOT_LAMBDA,
                         {"stat": "p99", "color": "#ff7f0e"}]
                    ],
                    "period": 60, "view": "timeSeries"
                }
            },
            {
                "type": "metric", "x": 0, "y": 6, "width": 12, "height": 6,
                "properties": {
                    "title": "KB ingestion jobs",
                    "metrics": [
                        ["AWS/Lambda", "Invocations", "FunctionName",
                         config.INGEST_LAMBDA],
                        ["AWS/Lambda", "Errors", "FunctionName",
                         config.INGEST_LAMBDA, {"color": "#d62728"}]
                    ],
                    "period": 300, "stat": "Sum", "view": "timeSeries"
                }
            }
        ]
    }
    cw.put_dashboard(
        DashboardName=config.DASHBOARD_NAME,
        DashboardBody=json.dumps(body)
    )
    print(f"Dashboard created: {config.DASHBOARD_NAME}")


def main():
    create_alarms()
    create_dashboard()


if __name__ == "__main__":
    main()
