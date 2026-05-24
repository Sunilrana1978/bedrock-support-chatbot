"""
Phase 1 — Step 3
Provisions OpenSearch Serverless collection, creates the Bedrock Knowledge Base,
registers the S3 data source, and runs the first ingestion job.
"""
import json
import time
import sys
import boto3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))
import config

REGION = config.REGION
ids = config.load_ids()
ROLE_ARN = ids.get("role_arn") or __import__("os").environ["BEDROCK_ROLE_ARN"]
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]

aoss         = boto3.client("opensearchserverless", region_name=REGION)
bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)


def create_opensearch_collection():
    print("Creating OpenSearch Serverless collection...")

    # Encryption policy
    enc = {"Rules": [{"Resource": [f"collection/{config.COLLECTION_NAME}"],
                      "ResourceType": "collection"}],
           "AWSOwnedKey": True}
    try:
        aoss.create_security_policy(
            name=f"{config.COLLECTION_NAME}-enc",
            type="encryption",
            policy=json.dumps(enc)
        )
    except aoss.exceptions.ConflictException:
        pass

    # Network policy
    net = [{"Rules": [{"Resource": [f"collection/{config.COLLECTION_NAME}",
                                    "dashboards/default"],
                       "ResourceType": "collection"}],
            "AllowFromPublic": True}]
    try:
        aoss.create_security_policy(
            name=f"{config.COLLECTION_NAME}-net",
            type="network",
            policy=json.dumps(net)
        )
    except aoss.exceptions.ConflictException:
        pass

    # Create collection
    try:
        col = aoss.create_collection(
            name=config.COLLECTION_NAME,
            type="VECTORSEARCH",
            description="Vector store for production support KB"
        )
        col_id  = col["createCollectionDetail"]["id"]
        col_arn = col["createCollectionDetail"]["arn"]
    except aoss.exceptions.ConflictException:
        existing = aoss.list_collections(
            collectionFilters={"name": config.COLLECTION_NAME}
        )["collectionSummaries"][0]
        col_id  = existing["id"]
        col_arn = existing["arn"]
        print(f"Collection already exists: {col_id}")

    # Wait until ACTIVE
    print("Waiting for collection to become ACTIVE...")
    while True:
        status = aoss.batch_get_collection(ids=[col_id])[
            "collectionDetails"][0]["status"]
        print(f"  Status: {status}")
        if status == "ACTIVE":
            break
        time.sleep(15)

    # Data access policy
    data_policy = [{
        "Rules": [
            {"Resource": [f"collection/{config.COLLECTION_NAME}"],
             "Permission": ["aoss:CreateCollectionItems",
                            "aoss:UpdateCollectionItems",
                            "aoss:DescribeCollectionItems"],
             "ResourceType": "collection"},
            {"Resource": [f"index/{config.COLLECTION_NAME}/*"],
             "Permission": ["aoss:CreateIndex", "aoss:UpdateIndex",
                            "aoss:DescribeIndex", "aoss:ReadDocument",
                            "aoss:WriteDocument"],
             "ResourceType": "index"}
        ],
        "Principal": [ROLE_ARN, f"arn:aws:iam::{ACCOUNT_ID}:root"]
    }]
    try:
        aoss.create_access_policy(
            name=f"{config.COLLECTION_NAME}-access",
            type="data",
            policy=json.dumps(data_policy)
        )
    except aoss.exceptions.ConflictException:
        pass

    print(f"Collection ARN: {col_arn}")
    return col_arn


def create_knowledge_base(collection_arn: str):
    print("Creating Knowledge Base...")
    kb = bedrock_agent.create_knowledge_base(
        name=config.KB_NAME,
        description="Production support docs and incident history",
        roleArn=ROLE_ARN,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": config.EMBEDDING_MODEL_ARN
            }
        },
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": collection_arn,
                "vectorIndexName": config.VECTOR_INDEX_NAME,
                "fieldMapping": {
                    "vectorField": "embedding",
                    "textField": "text",
                    "metadataField": "metadata"
                }
            }
        }
    )
    kb_id = kb["knowledgeBase"]["knowledgeBaseId"]
    print(f"Knowledge Base ID: {kb_id}")
    return kb_id


def add_data_source(kb_id: str):
    print("Adding S3 data source...")
    ds = bedrock_agent.create_data_source(
        knowledgeBaseId=kb_id,
        name=config.DS_NAME,
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{config.S3_BUCKET_NAME}"
            }
        },
        vectorIngestionConfiguration={
            "chunkingConfiguration": {
                "chunkingStrategy": "SEMANTIC",
                "semanticChunkingConfiguration": {
                    "maxTokens": 512,
                    "bufferSize": 1,
                    "breakpointPercentileThreshold": 95
                }
            }
        }
    )
    ds_id = ds["dataSource"]["dataSourceId"]
    print(f"Data Source ID: {ds_id}")
    return ds_id


def run_ingestion(kb_id: str, ds_id: str):
    print("Starting first ingestion job...")
    job = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id
    )
    job_id = job["ingestionJob"]["ingestionJobId"]

    while True:
        result = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id
        )["ingestionJob"]
        status = result["status"]
        print(f"  Ingestion status: {status}")
        if status in ("COMPLETE", "FAILED"):
            break
        time.sleep(20)

    if status == "FAILED":
        raise RuntimeError(f"Ingestion failed: {result.get('failureReasons')}")
    print("Ingestion complete.")


def main():
    col_arn = create_opensearch_collection()
    kb_id   = create_knowledge_base(col_arn)
    ds_id   = add_data_source(kb_id)
    run_ingestion(kb_id, ds_id)
    config.save_ids({"kb_id": kb_id, "ds_id": ds_id})


if __name__ == "__main__":
    main()
