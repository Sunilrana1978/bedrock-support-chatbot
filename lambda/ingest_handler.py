"""
Lambda handler — triggered by EventBridge on S3 uploads and weekly cron.
Starts a Bedrock KB ingestion job with debounce logic.
"""
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-agent")
KB_ID   = os.environ["KNOWLEDGE_BASE_ID"]
DS_ID   = os.environ["DATA_SOURCE_ID"]


def lambda_handler(event, context):
    # Debounce: skip if a job is already running
    running = bedrock.list_ingestion_jobs(
        knowledgeBaseId=KB_ID,
        dataSourceId=DS_ID,
        filters=[{
            "attribute": "STATUS",
            "operator": "EQ",
            "values": ["IN_PROGRESS", "STARTING"]
        }]
    )["ingestionJobSummaries"]

    if running:
        logger.info("Ingestion already running — skipping.")
        return {"status": "skipped"}

    job    = bedrock.start_ingestion_job(knowledgeBaseId=KB_ID, dataSourceId=DS_ID)
    job_id = job["ingestionJob"]["ingestionJobId"]
    logger.info(f"Started ingestion job: {job_id}")
    return {"status": "started", "jobId": job_id}
