"""
Custom CloudFormation resource — creates the OpenSearch Serverless vector index
required by Bedrock Knowledge Base before the KB itself can be provisioned.

CloudFormation has no native AWS::OpenSearchServerless::Index resource, so this
Lambda-backed custom resource fills that gap. It sends SigV4-signed REST PUT
requests to the collection endpoint and retries for up to 5 minutes while the
collection warms up.
"""
import json
import time
import urllib3

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

http = urllib3.PoolManager()


def _cfn_respond(event: dict, status: str, data: dict):
    """Send result to the pre-signed CloudFormation response URL."""
    body = json.dumps({
        "Status": status,
        "Reason": data.get("Error", ""),
        "PhysicalResourceId": event.get("PhysicalResourceId", "aoss-index"),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": data,
    })
    http.request(
        "PUT",
        event["ResponseURL"],
        body=body,
        headers={"Content-Type": ""},
    )


def _create_index(endpoint: str, index: str, region: str):
    mapping = json.dumps({
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "bedrock-knowledge-base-default-vector": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {"name": "hnsw", "engine": "faiss", "space_type": "l2"},
                },
                "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
                "AMAZON_BEDROCK_METADATA": {"type": "text", "index": False},
            }
        },
    })

    creds = boto3.session.Session().get_credentials().get_frozen_credentials()
    url = f"https://{endpoint}/{index}"

    for attempt in range(10):
        req = AWSRequest(
            method="PUT",
            url=url,
            data=mapping,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(creds, "aoss", region).add_auth(req)
        resp = http.request("PUT", url, body=mapping, headers=dict(req.headers))

        if resp.status in (200, 201):
            print(f"Index '{index}' created (attempt {attempt + 1}).")
            return

        err_type = json.loads(resp.data).get("error", {}).get("type", "")
        if err_type == "resource_already_exists_exception":
            print(f"Index '{index}' already exists — skipping.")
            return

        print(f"Attempt {attempt + 1} failed (HTTP {resp.status}): {resp.data}. Retrying in 30 s…")
        if attempt < 9:
            time.sleep(30)

    raise RuntimeError(f"Could not create index after 10 attempts. Last response: {resp.data}")


def handler(event, context):
    status, data = "SUCCESS", {}
    try:
        req_type = event["RequestType"]
        print(f"RequestType={req_type}")

        if req_type in ("Create", "Update"):
            _create_index(
                endpoint=event["ResourceProperties"]["CollectionEndpoint"],
                index=event["ResourceProperties"]["IndexName"],
                region=event["ResourceProperties"]["Region"],
            )
    except Exception as exc:
        print(exc)
        status = "FAILED"
        data["Error"] = str(exc)
    finally:
        _cfn_respond(event, status, data)
